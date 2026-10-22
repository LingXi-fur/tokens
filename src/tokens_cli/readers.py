"""读取 Claude / Gemini / Codex 本地日志，归一成统一 record。

统一 record 字段：
  source    : claude | gemini | codex
  ts        : 原始 ISO 时间戳（字符串）
  date      : 本地时区日期 YYYY-MM-DD
  model     : 模型名（Claude 经 router 已是真实后端名）
  input     : 输入 token（Gemini/Codex 含 cached 的语义见下）
  output    : 输出 token
  cache_read: 缓存命中读 token（信息项）
  cache_write: 缓存写 token（仅 Claude 有）
  total     : 该轮总 token（按各源报告值，口径见 DEVLOG）
  session   : 会话 id
  billing   : 计费证据（schema 1）：源头分量、presence、口径异常原因；
              独立字段，绝不改变上述既有统计口径（详见 BILLING_SCHEMA 注释）

total 口径说明：
  claude : input + output + cache_read + cache_write
  gemini : tokens.total（= input + output + cached + thoughts + tool）
  codex  : total_tokens（input_tokens 已含 cached_input_tokens，故不重复加）
"""
import glob
import json
import math
import os
import re
import stat
import tempfile
from datetime import datetime

from . import _claude_json, config

# 缓存结构版本：解析口径变更后旧 cache.json 作废、强制重读。
#   v1 = 初版（含 Claude 重复 message.id 导致总量夸大）
#   v2 = Claude 按 message.id 去重
#   v3 = record 增 cwd 字段（项目维度 Top 榜需要）
#   v4 = Claude request aliases may resolve through the user's current CCR router
#   v5 = record 新增 billing 计费证据（schema 1，独立于既有用量统计）
#   v6 = Claude 有界大日志读取、保留预算及安全缓存契约
#   v7 = Claude 小/大行统一流式 JSON 投影，工程限额失败不再静默漏计
CACHE_VERSION = 7

# ---------- Billing evidence (schema 1) ----------
# 独立计费证据：只读源头分量、字段是否实际存在及口径异常原因，绝不改写既有
# input/output/cache_read/cache_write/total 统计口径。分量顺序与 dashboard cost
# contract 一致，不得重排。缺失值与显式 0 区分（present 记录），日志遗漏不当免费。

BILLING_SCHEMA = 1
BILLING_COMPONENTS = ("input", "output", "cache_read", "cache_write", "thoughts")
# JS 安全整数上限；超出视为异常值，不进入计费分量。
_SAFE_INT_MAX = 2 ** 53 - 1


def _safe_tokens(value):
    """非负安全整数返回原值；bool/浮点/字符串/越界返回 None（异常降级，不炸）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > _SAFE_INT_MAX:
        return None
    return value


def _field_evidence(container, spec):
    """按 {分量: 源字段名} 读取 presence 与安全整数值（缺失记 None）。"""
    present = {}
    values = {}
    for name, key in spec.items():
        present[name] = key in container
        values[name] = _safe_tokens(container.get(key)) if present[name] else None
    return present, values


def _billing_result(present, values, parts, reasons):
    """组装 billing 证据。不可信记录 parts 一律全 0，不得部分收费。"""
    uncertain = bool(reasons)
    return {
        "v": BILLING_SCHEMA,
        "present": present,
        "raw": values,
        "parts": list(parts) if parts is not None else [0] * len(BILLING_COMPONENTS),
        "uncertain": uncertain,
        "reasons": reasons,
    }


def _missing_or_invalid(present, values, names, reasons):
    """必填分量缺失/异常记原因，返回是否存在阻断问题。"""
    blocked = False
    for name in names:
        if not present[name]:
            reasons.append("missing_" + name)
            blocked = True
        elif values[name] is None:
            reasons.append("invalid_" + name)
            blocked = True
    return blocked


# Claude usage：input/output 必填；cache_read/cache_write 为 Messages API 可选字段，
# 其缺失契约明确为「未使用缓存」＝0（presence 另行记录，不与日志遗漏混淆）。
# Claude 无独立 thoughts 分量（thinking 已含于 output_tokens），thoughts 恒 0。
# cache_write 为 5m/1h 合并值，只能配用户确认的统一有效单价，不能冒充分档账单。
_CLAUDE_BILLING_KEYS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_write": "cache_creation_input_tokens",
}


def _claude_billing(usage):
    present, values = _field_evidence(usage, _CLAUDE_BILLING_KEYS)
    reasons = []
    _missing_or_invalid(present, values, ("input", "output"), reasons)
    for name in ("cache_read", "cache_write"):
        if present[name] and values[name] is None:
            reasons.append("invalid_" + name)
    parts = None
    if not reasons:
        cache_read = values["cache_read"] if present["cache_read"] else 0
        cache_write = values["cache_write"] if present["cache_write"] else 0
        parts = [values["input"], values["output"], cache_read, cache_write, 0]
    return _billing_result(present, values, parts, reasons)


# Codex last_token_usage：五个字段全部必填（cached/reasoning/total 缺失时口径
# 无法确认，保守 unknown）。契约按 OpenAI Responses 语义：cached ⊆ input、
# reasoning ⊆ output、total = input + output；计费输入扣 cached，计费输出仅取
# 原始 output_tokens，不额外加 reasoning。
_CODEX_BILLING_KEYS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cached_input_tokens",
    "reasoning": "reasoning_output_tokens",
    "total": "total_tokens",
}


def _codex_billing(usage):
    present, values = _field_evidence(usage, _CODEX_BILLING_KEYS)
    reasons = []
    blocked = _missing_or_invalid(
        present, values, ("input", "output", "cache_read", "reasoning", "total"), reasons)
    parts = None
    if not blocked:
        inp = values["input"]
        outp = values["output"]
        cached = values["cache_read"]
        reason = values["reasoning"]
        total = values["total"]
        if cached > inp:
            reasons.append("cache_exceeds_input")
        if reason > outp:
            reasons.append("reasoning_exceeds_output")
        if total != inp + outp:
            reasons.append("total_mismatch")
        if not reasons:
            parts = [inp - cached, outp, cached, 0, 0]
    return _billing_result(present, values, parts, reasons)


# Gemini tokens：六个字段全部必填；thoughts 单列计费分量，tool 无法归属到任何
# 可定价分量（tool>0 整条 unknown，不硬摊给输出）；分量与 total 不一致整条
# unknown。input 不含 cached；无 cache write 概念（schema 级 0）。
_GEMINI_BILLING_KEYS = {
    "input": "input",
    "output": "output",
    "cache_read": "cached",
    "thoughts": "thoughts",
    "tool": "tool",
    "total": "total",
}


def _gemini_billing(tokens):
    present, values = _field_evidence(tokens, _GEMINI_BILLING_KEYS)
    reasons = []
    blocked = _missing_or_invalid(
        present, values, ("input", "output", "cache_read", "thoughts", "tool", "total"),
        reasons)
    parts = None
    if not blocked:
        inp = values["input"]
        outp = values["output"]
        cached = values["cache_read"]
        thoughts = values["thoughts"]
        tool = values["tool"]
        total = values["total"]
        if tool > 0:
            reasons.append("unattributed_tool")
        if total != inp + outp + cached + thoughts + tool:
            reasons.append("total_mismatch")
        if not reasons:
            parts = [inp, outp, cached, 0, thoughts]
    return _billing_result(present, values, parts, reasons)


def billing_view(record):
    """返回 (parts, uncertain)：payload 侧防御性读取计费证据。

    旧记录缺 billing、schema 不符（含 v 为 bool，True 不得当 1）、uncertain
    非 bool、分量异常、不可信却带非零分量、或可信分量与记录级 reported total
    不守恒（sum(parts) != record total）时，一律降级为全 0 分量 + uncertain，
    不炸 payload；缓存中的坏 billing 不会伪装成可信全价。
    """
    zero = [0] * len(BILLING_COMPONENTS)
    billing = record.get("billing") if isinstance(record, dict) else None
    if not isinstance(billing, dict):
        return zero, True
    version = billing.get("v")
    if isinstance(version, bool) or version != BILLING_SCHEMA:
        return zero, True
    uncertain = billing.get("uncertain", True)
    if not isinstance(uncertain, bool):
        return zero, True
    parts = billing.get("parts")
    if not isinstance(parts, list) or len(parts) != len(BILLING_COMPONENTS):
        return zero, True
    checked = []
    for value in parts:
        safe = _safe_tokens(value)
        if safe is None:
            return zero, True
        checked.append(safe)
    if uncertain and any(checked):
        return zero, True
    reported = _safe_tokens(record.get("total"))
    if reported is None or sum(checked) != reported:
        # 可信分量必须与记录级 reported total 守恒，防止伪 v/错配 billing 免费。
        return zero, True
    return checked, uncertain

# Gemini/Codex 及未指定来源沿用整文件上限；Claude 限制读取块与保留状态。
MAX_FILE_BYTES = 64 * 1024 * 1024
# Claude 的小行缓冲阈值，不是物理行长度上限；标题/Codex 原行长策略不变。
MAX_LINE_BYTES = 4 * 1024 * 1024
CLAUDE_READ_CHUNK_BYTES = 64 * 1024
MAX_CLAUDE_RECORDS = 100000
MAX_CLAUDE_RETAINED_BYTES = 64 * 1024 * 1024
MAX_TOTAL_RECORDS = 500000
MAX_TOTAL_RETAINED_BYTES = 256 * 1024 * 1024
MAX_CACHE_BYTES = 64 * 1024 * 1024


class CollectionIncompleteError(Exception):
    """受控失败码；不得把路径、日志内容或底层异常插入公开错误文本。"""

    SOURCES = frozenset(("claude", "gemini", "codex", "all"))
    REASONS = frozenset((
        "discovery_failed", "stat_failed", "unsafe_file", "open_failed",
        "read_failed", "file_changed", "line_too_long", "record_limit",
        "retained_bytes_limit", "total_record_limit", "total_retained_bytes_limit",
        "json_depth_limit", "json_token_limit", "json_projection_limit",
        "json_number_limit",
    ))

    def __init__(self, source, reason):
        if source not in self.SOURCES or reason not in self.REASONS:
            raise ValueError("invalid collection error code")
        self.source = source
        self.reason = reason
        super().__init__(f"Collection incomplete ({source}: {reason})")


def _encoded_retained_bytes(value):
    """逐项计费，不序列化 records 列表；这是工程额度，不是 RSS 上界。"""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))
               .encode("utf-8"))


def _record_retained_bytes(record):
    return _encoded_retained_bytes(record) + 512


def _dedup_retained_bytes(key):
    return _encoded_retained_bytes(key) + 256


def _stat_identity(st):
    return st.st_dev, st.st_ino


def _stat_version(st):
    return (*_stat_identity(st), st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _safe_open_flags():
    # 非阻塞防止检查/打开竞态把普通文件换成 FIFO 后挂起。
    return (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))


class _SafeReader:
    """安全打开普通文件，并只读打开时的长度；不保证祖先目录无软链。"""

    def __init__(self, path):
        self.path = path
        self.fh = None
        self.initial = None
        self.remaining = 0

    def __enter__(self):
        try:
            before = os.lstat(self.path)
        except OSError:
            raise CollectionIncompleteError("claude", "stat_failed") from None
        if not stat.S_ISREG(before.st_mode):
            raise CollectionIncompleteError("claude", "unsafe_file")
        try:
            fd = os.open(self.path, _safe_open_flags())
        except OSError:
            raise CollectionIncompleteError("claude", "open_failed") from None
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise CollectionIncompleteError("claude", "unsafe_file")
            if _stat_identity(before) != _stat_identity(opened):
                raise CollectionIncompleteError("claude", "file_changed")
            if (opened.st_size < before.st_size
                    or (opened.st_size == before.st_size
                        and _stat_version(opened) != _stat_version(before))):
                raise CollectionIncompleteError("claude", "file_changed")
            self.initial = opened
            self.remaining = opened.st_size
            self.fh = os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        self.fh.close()
        return False

    def read_chunk(self):
        if not self.remaining:
            return b""
        raw = self.fh.read(min(CLAUDE_READ_CHUNK_BYTES, self.remaining))
        if not raw:
            raise CollectionIncompleteError("claude", "file_changed")
        self.remaining -= len(raw)
        return raw

    def finish(self):
        current = os.fstat(self.fh.fileno())
        try:
            named = os.lstat(self.path)
        except OSError:
            raise CollectionIncompleteError("claude", "file_changed") from None
        for st in (current, named):
            if (not stat.S_ISREG(st.st_mode)
                    or _stat_identity(st) != _stat_identity(self.initial)
                    or st.st_size < self.initial.st_size
                    or (st.st_size == self.initial.st_size
                        and _stat_version(st) != _stat_version(self.initial))):
                raise CollectionIncompleteError("claude", "file_changed")
        # 正常 append 不失败；下轮再读增量，不能缓存为新的完整版本。
        return (_stat_version(current) == _stat_version(self.initial)
                and _stat_version(named) == _stat_version(self.initial))

# 标题解析：可读标题上限；无标题日志的有界扫描（先到者为准，避免无限扫描）。
TITLE_MAX_LEN = 60
TITLE_SCAN_MAX_LINES = 2000
TITLE_SCAN_MAX_BYTES = 4 * 1024 * 1024
# 续接/压缩摘要标记：这类文本是上一段对话的机器生成摘要，不是用户的真实提问。
_TITLE_CONTINUATION_MARKERS = (
    "this session is being continued",
    "session is being continued from a previous",
    "continue from where the conversation",
    "continue the conversation from where it left off",
    "previous conversation that ran out of context",
    "the summary below covers the earlier portion",
    "以下是对话的摘要",
    "这是对话的摘要",
    "我们上次停在这里",
    "上次对话中断",
    "会话摘要如下",
    "以上是之前对话的摘要",
)
# 无任务信息的短确认/寒暄：单条不足以表达会话用途。
_TITLE_FILLERS = frozenset({
    "continue", "go on", "go ahead", "keep going", "proceed", "resume",
    "yes", "y", "ok", "okay", "sure", "thanks", "thank you", "done", "next",
    "继续", "好的", "好", "嗯", "嗯嗯", "是的", "是", "对", "可以", "行",
    "谢谢", "多谢", "辛苦了", "收到", "明白", "了解", "然后呢", "下一步",
    "继续吧", "请继续", "往下", "下一个",
})
# 纯路径 / 纯 ID / 纯 hex：不是可读任务标题。
_TITLE_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_TITLE_HEX_ID_RE = re.compile(r"^[0-9a-fA-F]{8,}$")
# 系统包络/环境元信息前缀：整段以这些开头即视为非用户提问。
_TITLE_ENVELOPE_PREFIXES = (
    "[system notification",
    "[system-reminder",
    "[task-notification",
    "today's date is",
    "current date is",
    "environment:",
)
# 绝对路径（POSIX / Windows）或纯文件名式路径。
_TITLE_ABS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/|~[\\/]|\\\\)")
# 至少含一个 CJK 字符视为中文标题（用于长度放宽与短指令判定）。
_TITLE_CJK_RE = re.compile(r"[㐀-䶿一-鿿]")
# 标题首尾需要剥离的包裹字符（标点 / 引号 / 空白）。
_TITLE_TRIM_CHARS = " \t\r\n\"'`“”‘’。，、！？!?,.;:；：-—…([{（【<《"


def _user_text_blocks(content):
    """从一个 user 消息的 content 抽取所有 text 块（按出现顺序）。"""
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    out.append(text)
        return out
    return []


def _looks_like_path_or_id(text):
    """纯路径 / 纯 ID / 纯 hex 判定（清洗时丢弃）。

    绝对路径只在整行是「单个无空白 token」时才判为纯路径；带任务描述的
    行（如 "/Users/x/app.py 这个函数为什么报错"）保留。
    """
    if not text:
        return True
    if _TITLE_UUID_RE.match(text) or _TITLE_HEX_ID_RE.match(text):
        return True
    if _TITLE_ABS_PATH_RE.match(text) and not re.search(r"\s", text):
        return True
    return False


def sanitize_session_title(raw, max_len=TITLE_MAX_LEN):
    """纯函数：保守清洗候选标题，混入续接/系统/包络的来源一律拒绝。

    返回清洗后的可读标题或空串（无可靠标题）。不读日志、不落盘。
    """
    if not isinstance(raw, str):
        # 真值非字符串（如 sidecar/注入 {sid: 42}）一律视为无标题，不崩溃。
        return ""
    text = raw.strip()
    if not text:
        return ""
    # 系统/任务通知/命令包络：整段以尖括号或已知前缀开头，不从中猜任务。
    if text.startswith("<") or text.startswith("{{"):
        return ""
    lowered = text.lower()
    if lowered.startswith("caveat:"):
        return ""
    if any(lowered.startswith(prefix) for prefix in _TITLE_ENVELOPE_PREFIXES):
        return ""
    # 整段命中续接摘要标记 → 机器生成摘要，不是用户提问。
    if any(marker in lowered for marker in _TITLE_CONTINUATION_MARKERS):
        return ""
    # 取首个非空行；代码围栏 / 纯命令块在裁剪前判定（裁剪会吃掉前导反引号）。
    first_line = re.split(r"[\r\n]+", text, 1)[0].lstrip()
    if first_line.startswith("```") or first_line.startswith("$ ") or first_line.startswith("> "):
        return ""
    first = re.sub(r"\s+", " ", re.split(r"[\r\n]+", text, 1)[0]).strip()
    first = first.strip(_TITLE_TRIM_CHARS)
    if not first:
        return ""
    # 纯路径 / 纯 ID。
    if _looks_like_path_or_id(first):
        return ""
    # 无任务信息的短指令/寒暄（中文单字或纯英文填充词）。
    if first.lower() in _TITLE_FILLERS:
        return ""
    # 过短且非 CJK（<3 个字符的英文串基本无意义）；中文放宽到 2 字。
    if len(first) < 3 and not _TITLE_CJK_RE.search(first):
        return ""
    if len(first) < 2:
        return ""
    return first[:max_len]


def _to_local_date(iso_ts):
    """ISO 字符串 → 本地时区 YYYY-MM-DD。非字符串/格式错返回 None（调用方跳过）。"""
    if not isinstance(iso_ts, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(config.TZ).date().isoformat()


def local_hour(iso_ts):
    """ISO 字符串 → 本地时区小时(0-23)。无效返回 None。用于小时聚合。"""
    if not isinstance(iso_ts, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(config.TZ).hour


def parse_local_dt(iso_ts):
    """ISO 字符串 → 本地时区 aware datetime。无效返回 None。"""
    if not isinstance(iso_ts, str):
        return None
    try:
        return datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).astimezone(config.TZ)
    except ValueError:
        return None


# ---------- Optional CCR model resolution ----------
# Claude logs may contain request aliases (for example a Claude tier name) or
# an actual backend name. A local CCR router can resolve aliases for its owner.
# Public/default behavior is conservative: without a matching local rule, keep
# the logged model unchanged.

_NEEDLE_RE = re.compile(r"model\.includes\(\s*['\"]([^'\"]+)['\"]\s*\)")
_RETURN_RE = re.compile(r"return\s+['\"][^,'\"]+,([^,'\"]+)['\"]")
_ANY_RETURN_RE = re.compile(r"\breturn\b")

_ccr_rules_cache = ("", [])


def _parse_ccr_rules(text):
    """Return conservative ordered rules parsed from router source.

    Every return ends the pending condition. Unsupported return expressions are
    ignored rather than allowed to attach their aliases to a later branch.
    """
    rules, needles = [], []
    for line in text.splitlines():
        needles.extend(_NEEDLE_RE.findall(line))
        if not _ANY_RETURN_RE.search(line):
            continue
        match = _RETURN_RE.search(line)
        if match and needles:
            backend = match.group(1)
            rules.extend((needle, backend) for needle in needles)
        needles = []
    return rules


def _ccr_signature():
    """Return the local router mtime/size signature, or an empty string."""
    try:
        st = os.stat(config.CCR_ROUTER_FILE)
        return f"{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return ""


def _ccr_rules():
    """Read ordered rules from this user's router, cached by file signature."""
    global _ccr_rules_cache
    signature = _ccr_signature()
    if _ccr_rules_cache[0] == signature:
        return _ccr_rules_cache[1]
    rules = []
    if signature:
        try:
            with open(config.CCR_ROUTER_FILE, "r", encoding="utf-8", errors="replace") as fh:
                rules = _parse_ccr_rules(fh.read())
        except OSError:
            rules = []
    _ccr_rules_cache = (signature, rules)
    return rules


_TIER_MODEL_RE = re.compile(
    r"^(?:claude-)?(opus|sonnet|haiku)(?:-\d[\w.-]*)?$",
    re.IGNORECASE,
)


def _tier_of(model):
    """Return a tier only for a plain tier or Claude-style request model."""
    match = _TIER_MODEL_RE.fullmatch(model)
    return match.group(1).lower() if match else None


def _resolve_model(model):
    """Resolve a Claude request alias through the current user's router.

    Backend names are historical facts and remain unchanged. Without a local
    router or matching rule, public users see the model name stored in the log;
    no maintainer-specific fallback is applied.
    """
    rules = _ccr_rules()
    if model in {backend for _, backend in rules}:
        return model
    if not _tier_of(model):
        return model
    for needle, backend in rules:
        if needle in model:
            return backend
    return model


# ---------- Claude ----------

def claude_files():
    try:
        root = os.stat(config.CLAUDE_PROJECTS)
    except FileNotFoundError:
        return []
    except OSError:
        raise CollectionIncompleteError("claude", "discovery_failed") from None
    if not stat.S_ISDIR(root.st_mode):
        raise CollectionIncompleteError("claude", "discovery_failed")

    files = []
    # 原 glob 会跟随目录软链；不因无关目录软链扩大拒绝范围。
    # 每条分支保留祖先身份，检测实际递归环后明确失败，而非悄悄漏扫。
    # 根目录/祖先软链可被跟随；安全 open 只保证匹配文件本身的身份与类型。
    pending = [(config.CLAUDE_PROJECTS, ())]
    try:
        while pending:
            directory, ancestors = pending.pop()
            directory_stat = os.stat(directory)
            identity = _stat_identity(directory_stat)
            if not stat.S_ISDIR(directory_stat.st_mode) or identity in ancestors:
                raise CollectionIncompleteError("claude", "discovery_failed")
            descendants = []
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name.startswith("."):
                        continue
                    if entry.name.endswith(".jsonl"):
                        # 也保留匹配名称的非普通对象，由来源资格检查明确拒绝。
                        files.append(entry.path)
                    if entry.is_dir(follow_symlinks=True):
                        descendants.append((entry.path, (*ancestors, identity)))
            pending.extend(reversed(descendants))
    except OSError:
        raise CollectionIncompleteError("claude", "discovery_failed") from None
    return files


def _claude_event_record(o):
    """一个 usage 事件归一化；坏 JSON/无效事件仍按既有口径跳过。"""
    if not isinstance(o, dict) or o.get("type") != "assistant":
        return None
    msg = o.get("message")
    if not isinstance(msg, dict):
        return None
    model = msg.get("model")
    if not isinstance(model, str) or not model or model == "<synthetic>":
        return None
    usage = msg.get("usage") or {}
    if not isinstance(usage, dict):
        return None
    ts = o.get("timestamp")
    date = _to_local_date(ts)
    if not date:
        return None
    model = _resolve_model(model)
    inp = usage.get("input_tokens", 0)
    outp = usage.get("output_tokens", 0)
    cread = usage.get("cache_read_input_tokens", 0)
    cwrite = usage.get("cache_creation_input_tokens", 0)
    # first wins，不跨文件去重；保留完整 ID，缺失则退化为完整 usage tuple。
    mid = msg.get("id")
    dkey = mid if mid else (ts, model, inp, outp, cread, cwrite)
    hash(dkey)  # 非法非 hashable ID/分量只是坏事件，不能导致整文件空成功。
    record = {
        "source": "claude", "ts": ts, "date": date, "model": model,
        "input": inp, "output": outp, "cache_read": cread, "cache_write": cwrite,
        "total": inp + outp + cread + cwrite,
        "session": o.get("sessionId"), "cwd": o.get("cwd"),
        "billing": _claude_billing(usage),
    }
    return record, dkey, ["id", mid] if mid else ["fallback", list(dkey)]


def _claude_line_chunks(reader):
    """按原始 LF 分隔，最多保留一个固定读取块；末行无 LF 也只结束一次。"""
    unfinished = False
    while reader.remaining:
        chunk = reader.read_chunk()
        start = 0
        while True:
            end = chunk.find(b"\n", start)
            if end < 0:
                if start < len(chunk):
                    yield chunk[start:], False
                    unfinished = True
                break
            yield chunk[start:end], True
            unfinished = False
            start = end + 1
    if unfinished:
        yield b"", True


def _claude_projected_lines(reader):
    """大小行同一投影器；坏语法只 drain 当前行，工程限额立即整轮失败。"""
    prefix = bytearray()
    parser = None
    bad = False

    def start_parser():
        candidate = _claude_json.ProjectionParser()
        # 不复制/重读完整前缀，decoder 的临时文本也保持在一个固定块内。
        for start in range(0, len(prefix), CLAUDE_READ_CHUNK_BYTES):
            with memoryview(prefix)[start:start + CLAUDE_READ_CHUNK_BYTES] as part:
                candidate.feed(part)
        prefix.clear()
        return candidate

    for piece, finished in _claude_line_chunks(reader):
        if not bad:
            try:
                if parser is None and len(prefix) + len(piece) <= MAX_LINE_BYTES:
                    prefix.extend(piece)
                else:
                    if parser is None:
                        parser = start_parser()
                    parser.feed(piece)
                if finished:
                    if parser is None:
                        parser = start_parser()
                    projected = parser.finish_line()
            except _claude_json.ProjectionLimit as exc:
                prefix.clear()
                raise CollectionIncompleteError("claude", exc.reason) from None
            except _claude_json.BadJSON:
                # 已知语法错误后不再调用此行 parser，但仍有界消费到原始 LF。
                bad = True
                parser = None
                prefix.clear()
            else:
                if finished:
                    yield projected
        if finished:
            parser = None
            prefix.clear()
            bad = False


def _claude_parse_state(path):
    out, keys, seen_ids = [], [], set()
    retained = 0
    try:
        with _SafeReader(path) as reader:
            for o in _claude_projected_lines(reader):
                try:
                    result = _claude_event_record(o)
                    if result is None:
                        continue
                    record, dkey, saved_key = result
                    if dkey in seen_ids:
                        continue
                    record_bytes = _record_retained_bytes(record)
                    key_bytes = _dedup_retained_bytes(dkey)
                except (TypeError, ValueError, RecursionError, OverflowError):
                    # 局部坏事件不会抹掉此前/此后合法 usage。
                    continue
                if len(out) >= MAX_CLAUDE_RECORDS:
                    raise CollectionIncompleteError("claude", "record_limit")
                if retained + record_bytes + key_bytes > MAX_CLAUDE_RETAINED_BYTES:
                    raise CollectionIncompleteError("claude", "retained_bytes_limit")
                retained += record_bytes + key_bytes
                seen_ids.add(dkey)
                keys.append(saved_key)
                out.append(record)
            stable = reader.finish()
            return out, keys, reader.initial, stable
    except CollectionIncompleteError:
        raise
    except OSError:
        raise CollectionIncompleteError("claude", "read_failed") from None


def claude_parse(path):
    """返回 records list；安全/I/O/容量故障专用异常穿透，不返回 partial。"""
    return _claude_parse_state(path)[0]


# 保留 SOURCES 的可替换 parser 接口；仅内置实现有可验证的 cache dedup 状态。
_BUILTIN_CLAUDE_PARSE = claude_parse


def build_session_index():
    """一次扫描 Claude 日志目录，返回 session id → 文件路径。"""
    if not os.path.isdir(config.CLAUDE_PROJECTS):
        return {}
    try:
        return {
            os.path.splitext(os.path.basename(path))[0]: path
            for path in claude_files()
        }
    except CollectionIncompleteError:
        # 标题是可选增强；采集入口 read_all 仍严格传播同一发现故障。
        return {}


def session_file(session_id, session_index=None):
    """sessionId → Claude JSONL 路径（找不到返回 None）。"""
    if not session_id:
        return None
    if session_index is not None:
        return session_index.get(str(session_id))
    if not os.path.isdir(config.CLAUDE_PROJECTS):
        return None
    hits = glob.glob(os.path.join(config.CLAUDE_PROJECTS, "**", str(session_id) + ".jsonl"), recursive=True)
    return hits[0] if hits else None


def session_title(session_id, max_len=60, session_index=None):
    """从会话用户提问里挑一条可读标题（离线、隐私安全）。

    Claude 日志里 sessionId 即文件名。逐条用户消息检查其全部 text 块（不只首个
    块）；每条文本经 sanitize_session_title 保守清洗，跳过继续/系统/路径/ID 等
    污染，返回首条可靠标题。扫描有明确行数/字节上限，避免无标题日志无限读。
    没有可靠标题返回空串，由调用方回退到未命名/短 id。
    """
    path = session_file(session_id, session_index=session_index)
    if not path:
        return ""
    lines_seen = 0
    bytes_seen = 0
    try:
        # 二进制有界读取：readline 带上限，避免为计字节读入巨型行；
        # 计数为真实 UTF-8 字节数（非字符数）。MAX_LINE_BYTES ==
        # TITLE_SCAN_MAX_BYTES，故首个超长分块即耗尽总预算并停止扫描——
        # 预算耗尽返回「未命名」是预期，不为此恢复无界读取。
        with open(path, "rb") as fh:
            while True:
                raw = fh.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    break
                lines_seen += 1
                bytes_seen += len(raw)
                if lines_seen > TITLE_SCAN_MAX_LINES or bytes_seen > TITLE_SCAN_MAX_BYTES:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(o, dict) or o.get("type") != "user":
                    continue
                msg = o.get("message")
                if not isinstance(msg, dict):
                    continue
                for block_text in _user_text_blocks(msg.get("content")):
                    cleaned = sanitize_session_title(block_text, max_len=max_len)
                    if cleaned:
                        return cleaned
    except OSError:
        return ""
    return ""


def load_session_summaries():
    """读 out/session_summaries.json（LLM 生成的自然语言摘要 sidecar）。无则空 dict。"""
    try:
        with open(config.SESSION_SUMMARY_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# ---------- Gemini ----------

def gemini_files():
    if not os.path.isdir(config.GEMINI_TMP):
        return []
    return glob.glob(os.path.join(config.GEMINI_TMP, "*", "chats", "session-*.json"))


def gemini_parse(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return out
    if not isinstance(data, dict):
        return out
    session = data.get("sessionId")
    for m in data.get("messages") or []:
        if not isinstance(m, dict) or m.get("type") != "gemini":
            continue
        tk = m.get("tokens") or {}
        ts = m.get("timestamp")
        date = _to_local_date(ts)
        if not date:
            continue
        inp = tk.get("input", 0)
        cached = tk.get("cached", 0)
        outp = tk.get("output", 0)
        thoughts = tk.get("thoughts", 0)
        tool = tk.get("tool", 0)
        out.append({
            "source": "gemini",
            "ts": ts,
            "date": date,
            "model": m.get("model") or "gemini-unknown",
            "input": inp,           # input 不含 cached
            "output": outp + thoughts,
            "cache_read": cached,
            "cache_write": 0,
            "total": tk.get("total") or (inp + outp + cached + thoughts + tool),
            "session": session,
            "billing": _gemini_billing(tk),
        })
    return out


# ---------- Codex ----------

def codex_files():
    if not os.path.isdir(config.CODEX_SESSIONS):
        return []
    return glob.glob(os.path.join(config.CODEX_SESSIONS, "**", "rollout-*.jsonl"), recursive=True)


def codex_parse(path):
    out = []
    cur_model = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or len(line) > MAX_LINE_BYTES:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(o, dict) or o.get("type") != "event_msg":
                    continue
                payload = o.get("payload")
                if not isinstance(payload, dict):
                    continue
                ptype = payload.get("type")
                if ptype == "turn_context":
                    cur_model = payload.get("model") or cur_model
                elif ptype == "token_count":
                    info = payload.get("info") or {}
                    usage = info.get("last_token_usage") or {}
                    if not usage:
                        continue
                    ts = o.get("timestamp")
                    date = _to_local_date(ts)
                    if not date:
                        continue
                    inp = usage.get("input_tokens", 0)
                    cached = usage.get("cached_input_tokens", 0)
                    outp = usage.get("output_tokens", 0)
                    reason = usage.get("reasoning_output_tokens", 0)
                    out.append({
                        "source": "codex",
                        "ts": ts,
                        "date": date,
                        "model": cur_model or "codex-unknown",
                        "input": inp,          # input_tokens 已含 cached
                        "output": outp + reason,
                        "cache_read": cached,  # 信息项，已计入 input，勿重复加
                        "cache_write": 0,
                        "total": usage.get("total_tokens", 0) or (inp + outp),
                        "session": None,
                        "billing": _codex_billing(usage),
                    })
    except OSError:
        pass
    return out


# ---------- 调度 + 缓存 ----------

SOURCES = {
    "claude": (claude_files, claude_parse),
    "gemini": (gemini_files, gemini_parse),
    "codex": (codex_files, codex_parse),
}


def _file_key(path):
    st = os.stat(path)
    return f"{st.st_mtime_ns}|{st.st_size}"


def _safe_to_parse(path, st, source=None):
    """默认沿用旧资格规则；只有明确 Claude 来源免整文件大小上限。"""
    if os.path.islink(path) or not stat.S_ISREG(st.st_mode):
        return False
    if source != "claude" and st.st_size > MAX_FILE_BYTES:
        return False
    return True


def _load_cache():
    """不先 json.load 无界读；不安全/过大/损坏 cache 均只意味着 miss。"""
    fd = None
    try:
        before = os.lstat(config.CACHE_FILE)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_CACHE_BYTES:
            return {}
        fd = os.open(config.CACHE_FILE, _safe_open_flags())
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_CACHE_BYTES
                or _stat_version(opened) != _stat_version(before)):
            return {}
        with os.fdopen(fd, "rb") as fh:
            fd = None
            raw = fh.read(MAX_CACHE_BYTES + 1)
            if (len(raw) > MAX_CACHE_BYTES
                    or _stat_version(os.fstat(fh.fileno())) != _stat_version(opened)
                    or _stat_version(os.lstat(config.CACHE_FILE)) != _stat_version(opened)):
                return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}
    finally:
        if fd is not None:
            os.close(fd)


def _save_cache(cache):
    """逐块编码，超预算放弃新 temp、保留旧 cache；合法 records 不受影响。"""
    fd, tmp = None, None
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        cache["_v"] = CACHE_VERSION
        fd, tmp = tempfile.mkstemp(prefix=".records-", dir=config.CACHE_DIR)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fd = None
            written = 0
            encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"),
                                       allow_nan=False)
            for chunk in encoder.iterencode(cache):
                raw = chunk.encode("utf-8")
                if written + len(raw) > MAX_CACHE_BYTES:
                    return False
                fh.write(raw)
                written += len(raw)
        os.replace(tmp, config.CACHE_FILE)
        return True
    except (OSError, ValueError, RecursionError):
        return False
    finally:
        if fd is not None:
            os.close(fd)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


_RECORD_FIELDS = frozenset((
    "source", "ts", "date", "model", "input", "output", "cache_read",
    "cache_write", "total", "session", "billing",
))

# billing helper 产出的 schema 1 顶层键；来源规范复用同一 helper，不另造口径。
_BILLING_DICT_KEYS = frozenset(
    ("v", "present", "raw", "parts", "uncertain", "reasons"))
_BILLING_VALIDATORS = {
    "claude": (_CLAUDE_BILLING_KEYS, _claude_billing),
    "gemini": (_GEMINI_BILLING_KEYS, _gemini_billing),
    "codex": (_CODEX_BILLING_KEYS, _codex_billing),
}


def _cached_tokens_valid(record, source):
    """只验冷解析保留的数值类型，不改既有 token 口径。

    bool/有限 float/负数会被冷解析透传；Gemini/Codex 的 input/cache_read 还可能
    为 None（显式 total 可短路求和，Codex 的 cached 本就不参与求和）。
    容器/字符串/非有限 float 不作为有效 token cache；Claude 的五字段不接受 None。
    """
    for key in ("input", "output", "cache_read", "cache_write", "total"):
        value = record[key]
        if value is None and source in ("gemini", "codex") \
                and key in ("input", "cache_read"):
            continue
        if not isinstance(value, (int, float)):
            return False
        if isinstance(value, float) and not math.isfinite(value):
            return False
    return True


def _cached_billing_valid(billing, source):
    """精确校验 helper 可生成的 v1 证据；不验证源日志真实性或推断账单。"""
    validator = _BILLING_VALIDATORS.get(source)
    if validator is None or not isinstance(billing, dict):
        return False
    if set(billing) != _BILLING_DICT_KEYS:
        return False
    if type(billing["v"]) is not int or billing["v"] != BILLING_SCHEMA:
        return False
    spec, build_billing = validator
    present = billing["present"]
    raw = billing["raw"]
    if (not isinstance(present, dict) or set(present) != set(spec)
            or not all(isinstance(flag, bool) for flag in present.values())
            or not isinstance(raw, dict) or set(raw) != set(spec)):
        return False
    evidence = {}
    for name, key in spec.items():
        value = raw[name]
        if value is not None and _safe_tokens(value) is None:
            return False
        if present[name]:
            # None 既可表示显式 null，也可表示被 _safe_tokens 拒绝的值。
            evidence[key] = value
        elif value is not None:
            return False
    parts = billing["parts"]
    reasons = billing["reasons"]
    if (not isinstance(parts, list) or len(parts) != len(BILLING_COMPONENTS)
            or any(_safe_tokens(part) is None for part in parts)
            or not isinstance(billing["uncertain"], bool)
            or not isinstance(reasons, list)
            or not all(isinstance(reason, str) for reason in reasons)):
        return False
    # presence/raw 已保留 helper 的全部输入语义；重建校验 parts/reasons 等，
    # 也保留合法 uncertain/raw=None，不能拿 billing_view 的降级值冒充有效。
    return billing == build_billing(evidence)


def _cached_records_valid(records, source):
    if not isinstance(records, list):
        return False
    fields = _RECORD_FIELDS | {"cwd"} if source == "claude" else _RECORD_FIELDS
    for record in records:
        if (not isinstance(record, dict) or set(record) != fields
                or record.get("source") != source
                or not all(isinstance(record.get(k), str) for k in ("ts", "date", "model"))
                or not isinstance(record.get("billing"), dict)):
            return False
        # token/billing 形态坏 cache 一律 miss 重析，不吞采集失败、不改口径。
        if not _cached_tokens_valid(record, source) or not _cached_billing_valid(
                record["billing"], source):
            return False
        # 类型/编码坏 cache 重新解析，不把畸形 cache 当作源头采集失败。
        try:
            _record_retained_bytes(record)
        except (TypeError, ValueError, RecursionError, OverflowError):
            return False
    return True


def _cached_claude_keys_valid(records, keys):
    """验证实际完整 key，而非相信缓存自报预算。fallback 必须对应 record。"""
    if not isinstance(keys, list) or len(keys) != len(records):
        return False
    seen = set()
    for record, entry in zip(records, keys):
        if not isinstance(entry, list) or len(entry) != 2:
            return False
        kind, value = entry
        if kind == "id":
            if not isinstance(value, (str, int, float)) or not value:
                return False
            dkey = value
        elif kind == "fallback":
            if not isinstance(value, list) or len(value) != 6:
                return False
            if value != [record[k] for k in (
                    "ts", "model", "input", "output", "cache_read", "cache_write")]:
                return False
            dkey = tuple(value)
        else:
            return False
        try:
            if dkey in seen:
                return False
            _dedup_retained_bytes(dkey)
            seen.add(dkey)
        except (TypeError, ValueError, RecursionError, OverflowError):
            return False
    return True


def _check_claude_budget(records, keys=None):
    retained = 0
    for index, record in enumerate(records):
        if index >= MAX_CLAUDE_RECORDS:
            raise CollectionIncompleteError("claude", "record_limit")
        retained += _record_retained_bytes(record)
        if keys is not None:
            kind, value = keys[index]
            retained += _dedup_retained_bytes(tuple(value) if kind == "fallback" else value)
        if retained > MAX_CLAUDE_RETAINED_BYTES:
            raise CollectionIncompleteError("claude", "retained_bytes_limit")


def _extend_records(out, records, retained):
    """cold / warm 同一路径逐项检查，在保留下一条之前阻止超预算。"""
    for record in records:
        if len(out) >= MAX_TOTAL_RECORDS:
            raise CollectionIncompleteError("all", "total_record_limit")
        cost = _record_retained_bytes(record)
        if retained + cost > MAX_TOTAL_RETAINED_BYTES:
            raise CollectionIncompleteError("all", "total_retained_bytes_limit")
        out.append(record)
        retained += cost
    return retained


def read_all(sources=None, use_cache=True):
    """所有来源成功才返回/存缓存；Claude 不完整异常不可降级为空成功。"""
    sources = sources or list(SOURCES)
    cache = _load_cache() if use_cache else {}
    seen_keys = set()
    out = []
    retained = 0
    changed = False

    if use_cache and cache.get("_v") != CACHE_VERSION:
        cache = {}
        changed = True
    timezone_key = config.timezone_name()
    if use_cache and (timezone_key == "system local time" or cache.get("_timezone") != timezone_key):
        cache = {}
        changed = True
    router_sig = _ccr_signature()
    if use_cache and cache.get("_router") != router_sig:
        cache = {}
        changed = True

    for src in sources:
        if src not in SOURCES:
            continue
        files_fn, parse_fn = SOURCES[src]
        try:
            files = files_fn()
        except CollectionIncompleteError:
            raise
        except OSError:
            if src == "claude":
                raise CollectionIncompleteError(src, "discovery_failed") from None
            files = []
        try:
            for path in files:
                try:
                    st = os.stat(path)
                except OSError:
                    if src == "claude":
                        raise CollectionIncompleteError(src, "stat_failed") from None
                    continue
                if not _safe_to_parse(path, st, source=src):
                    if src == "claude":
                        raise CollectionIncompleteError(src, "unsafe_file")
                    continue
                key = f"{st.st_mtime_ns}|{st.st_size}"
                ckey = src + "::" + path
                seen_keys.add(ckey)
                cached = cache.get(ckey)
                warm = (use_cache and isinstance(cached, dict) and cached.get("key") == key
                        and _cached_records_valid(cached.get("records"), src))
                if warm and src == "claude":
                    warm = (cached.get("identity") == list(_stat_identity(st))
                            and cached.get("version") == list(_stat_version(st))
                            and _cached_claude_keys_valid(cached["records"], cached.get("dedup")))
                if warm:
                    recs = cached["records"]
                    if src == "claude":
                        _check_claude_budget(recs, cached["dedup"])
                        try:
                            # Warm path 仍安全 open/fstat/identity，不能只信 path.stat。
                            with _SafeReader(path) as reader:
                                if _stat_version(reader.initial) != _stat_version(st):
                                    warm = False
                                else:
                                    warm = reader.finish()
                        except CollectionIncompleteError:
                            raise
                        except OSError:
                            raise CollectionIncompleteError(src, "read_failed") from None
                if not warm:
                    stable, dedup = True, None
                    try:
                        if src == "claude" and parse_fn is _BUILTIN_CLAUDE_PARSE:
                            recs, dedup, opened, stable = _claude_parse_state(path)
                            # pre-stat 到 open 的追加也不能缓存为 pre-stat 版本。
                            stable = stable and _stat_version(opened) == _stat_version(st)
                        else:
                            recs = parse_fn(path)
                            if src == "claude":
                                _check_claude_budget(recs)
                                stable = False  # 可替换 parser 没有可验证 key，不写 warm 项。
                    except CollectionIncompleteError:
                        raise
                    except OSError:
                        if src == "claude":
                            raise CollectionIncompleteError(src, "read_failed") from None
                        recs = []
                    except Exception:
                        if src == "claude":
                            raise CollectionIncompleteError(src, "read_failed") from None
                        recs = []
                    if stable:
                        entry = {"key": key, "records": recs}
                        if src == "claude":
                            entry.update(identity=list(_stat_identity(st)),
                                         version=list(_stat_version(st)), dedup=dedup)
                        cache[ckey] = entry
                    else:
                        cache.pop(ckey, None)
                    changed = True
                retained = _extend_records(out, recs, retained)
        except CollectionIncompleteError:
            raise
        except OSError:
            if src == "claude":
                raise CollectionIncompleteError(src, "discovery_failed") from None
            raise

    stale = [k for k in cache if k.split("::", 1)[0] in sources and k not in seen_keys]
    for k in stale:
        cache.pop(k, None)
        changed = True
    if changed and use_cache:
        cache["_router"] = router_sig
        cache["_timezone"] = timezone_key
        _save_cache(cache)
    return out
