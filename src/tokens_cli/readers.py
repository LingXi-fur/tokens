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
import sys
import tempfile
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import _claude_json, config

# 缓存结构版本：解析口径变更后旧 cache.json 作废、强制重读。
#   v1 = 初版（含 Claude 重复 message.id 导致总量夸大）
#   v2 = Claude 按 message.id 去重
#   v3 = record 增 cwd 字段（项目维度 Top 榜需要）
#   v4 = Claude request aliases may resolve through the user's current CCR router
#   v5 = record 新增 billing 计费证据（schema 1，独立于既有用量统计）
#   v6 = Claude 有界大日志读取、保留预算及安全缓存契约
#   v7 = Claude 小/大行统一流式 JSON 投影，工程限额失败不再静默漏计
#   v8 = Codex 投影/归档、响应去重及 output 不重复加 reasoning
#   v9 = Codex 完整相邻证据下的显式零新增用量更新
#   v10 = Codex 不变累计下有界下降的上下文估算更新
#   v11 = Codex 完整对齐的现代镜像保留旧估算验证链
#   v12 = Codex 无序镜像多重集相等；现代记录不再打断旧格式相邻性
#   v13 = Codex 旧格式为完整账本，现代记录按值子集校验
#   v14 = Codex 并集计数：旧格式全部计入，现代记录同值吸收、余量独立计入
#   v15 = Codex 累计下降为新账本基线（生产者会中途重算累计值），不再视为冲突
#   v16 = Codex 同累计锚点证据分歧保留首见（生产者 resume 会重写同快照），
#         仅模型边界仍失败
#   v17 = Codex 同累计锚点重复一律保留首见，跨模型边界也如此（resume 换模型
#         会重写同快照）；legacy_anchor_mismatch 同文件不再触发
#   v18 = Claude 记录新增 request_model（路由前的原始请求名，与解析后 backend
#         并存）；计数/去重/费用口径零改动
#   v19 = CCR hex 别名（settings.json 写入的 anthropic/claude-ccr-h<hex>）解码
#         为内嵌后端名（如 zhipu/glm-5.3-flash），不再溢出 other；request_model
#         仍保留编码原名
#   v20 = hex 解码值剥除 provider 前缀（zhipu/glm-5.3-flash → glm-5.3-flash），
#         与历史 router 裸名合一身份，避免身份容量折叠溢出 other
CACHE_VERSION = 20

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
    "cache_write": "cache_write_input_tokens",
}


def _codex_billing(usage):
    present, values = _field_evidence(usage, _CODEX_BILLING_KEYS)
    reasons = []
    blocked = _missing_or_invalid(
        present, values, ("input", "output", "cache_read", "reasoning", "total"), reasons)
    parts = None
    if present["cache_write"] and values["cache_write"] != 0:
        reasons.append("cache_write_unconfirmed")
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
MAX_TOTAL_RECORDS = 1000000
MAX_TOTAL_RETAINED_BYTES = 1024 * 1024 * 1024
MAX_CACHE_BYTES = 512 * 1024 * 1024


class CollectionIncompleteError(Exception):
    """受控失败码；不得把路径、日志内容或底层异常插入公开错误文本。"""

    SOURCES = frozenset(("claude", "gemini", "codex", "all"))
    REASONS = frozenset((
        "discovery_failed", "stat_failed", "unsafe_file", "open_failed",
        "read_failed", "file_changed", "line_too_long", "record_limit",
        "retained_bytes_limit", "total_record_limit", "total_retained_bytes_limit",
        "json_depth_limit", "json_token_limit", "json_projection_limit",
        "decompressor_unavailable", "decompression_failed", "decompression_limit",
        "usage_invalid", "usage_identity_missing", "usage_conflict", "usage_mirror_mismatch",
        "json_number_limit",
    ))

    CONFLICT_KINDS = frozenset((
        "modern_response_mismatch", "legacy_cumulative_rollback",
        "legacy_anchor_mismatch", "cross_file_identity_mismatch",
    ))

    MISMATCH_KINDS = frozenset((
        "usage", "model", "billing", "usage_model", "usage_billing",
        "model_billing", "usage_model_billing",
    ))

    def __init__(self, source, reason, *, conflict_kind=None, mismatch_kind=None):
        if (not isinstance(source, str) or not isinstance(reason, str)
                or source not in self.SOURCES or reason not in self.REASONS):
            raise ValueError("invalid collection error code")
        self.source = source
        self.reason = reason
        self.conflict_kind = (conflict_kind if source == "codex" and reason == "usage_conflict"
                              and type(conflict_kind) is str
                              and conflict_kind in self.CONFLICT_KINDS else None)
        self.mismatch_kind = (mismatch_kind if self.conflict_kind == "legacy_anchor_mismatch"
                              and type(mismatch_kind) is str
                              and mismatch_kind in self.MISMATCH_KINDS else None)
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

    def __init__(self, path, source="claude"):
        self.source = source
        self.path = path
        self.fh = None
        self.initial = None
        self.remaining = 0

    def __enter__(self):
        try:
            before = os.lstat(self.path)
        except OSError:
            raise CollectionIncompleteError(self.source, "stat_failed") from None
        if not stat.S_ISREG(before.st_mode):
            raise CollectionIncompleteError(self.source, "unsafe_file")
        try:
            fd = os.open(self.path, _safe_open_flags())
        except OSError:
            raise CollectionIncompleteError(self.source, "open_failed") from None
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise CollectionIncompleteError(self.source, "unsafe_file")
            if _stat_identity(before) != _stat_identity(opened):
                raise CollectionIncompleteError(self.source, "file_changed")
            if (opened.st_size < before.st_size
                    or (opened.st_size == before.st_size
                        and _stat_version(opened) != _stat_version(before))):
                raise CollectionIncompleteError(self.source, "file_changed")
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
            raise CollectionIncompleteError(self.source, "file_changed")
        self.remaining -= len(raw)
        return raw

    def finish(self):
        current = os.fstat(self.fh.fileno())
        try:
            named = os.lstat(self.path)
        except OSError:
            raise CollectionIncompleteError(self.source, "file_changed") from None
        for st in (current, named):
            if (not stat.S_ISREG(st.st_mode)
                    or _stat_identity(st) != _stat_identity(self.initial)
                    or st.st_size < self.initial.st_size
                    or (st.st_size == self.initial.st_size
                        and _stat_version(st) != _stat_version(self.initial))):
                raise CollectionIncompleteError(self.source, "file_changed")
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
    行（如 "/synthetic/project/app.py 这个函数为什么报错"）保留。
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


def _to_local_date(iso_ts, *, _memo_proof=None):
    """ISO 字符串 → 本地时区 YYYY-MM-DD。非字符串/格式错返回 None（调用方跳过）。"""
    if not isinstance(iso_ts, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if _memo_proof is not None:
        # Record the dependency before astimezone: Claude can skip this
        # candidate if local-time conversion overflows (including empty output).
        if dt.utcoffset() is None:
            _memo_proof[0] = False
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

# settings.json 部署写入的 "anthropic/claude-ccr-h<hex>" 请求名：hex 后缀编码
# 真实后端 "provider/model"。hex 是稳定传输格式，解码属于解析而非改写历史。
# 解码值剥除 provider 前缀：hex 内嵌 "zhipu/glm-5.3-flash" 与历史 router 记录
# 的裸名 "glm-5.3-flash" 是同一物理后端，合一身份避免容量溢出折叠进 other。
_CCR_HEX_ALIAS_RE = re.compile(r"^anthropic/claude-ccr-h([0-9a-f]+)$")


def _ccr_hex_backend(model):
    """Decode a CCR hex alias into its bare backend name, else None."""
    match = _CCR_HEX_ALIAS_RE.fullmatch(model)
    if not match:
        return None
    blob = match.group(1)
    if len(blob) % 2 or len(blob) < 2:
        return None
    try:
        decoded = bytes.fromhex(blob).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    bare = decoded.rsplit("/", 1)[-1] if "/" in decoded else decoded
    return bare or None


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
    hex_backend = _ccr_hex_backend(model)
    if hex_backend:
        return hex_backend
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


def _claude_event_record(o, *, _memo_proof=None):
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
    date = (_to_local_date(ts) if _memo_proof is None
            else _to_local_date(ts, _memo_proof=_memo_proof))
    if not date:
        return None
    request_model = model
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
        # 请求名仅信息性：计数/去重/费用全部按解析后的 model 归账。
        "request_model": request_model,
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


def _claude_parse_state(path, *, _memo_proof=None):
    out, keys, seen_ids = [], [], set()
    retained = 0
    try:
        with _SafeReader(path) as reader:
            for o in _claude_projected_lines(reader):
                try:
                    result = (_claude_event_record(o) if _memo_proof is None else
                              _claude_event_record(o, _memo_proof=_memo_proof))
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
    from . import codex_usage
    return codex_usage.discover()


def codex_parse(path):
    from . import codex_usage
    return codex_usage.parse_state(path)[0]


_BUILTIN_CODEX_PARSE = codex_parse


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
    if source not in ("claude", "codex") and st.st_size > MAX_FILE_BYTES:
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
        fchmod = getattr(os, "fchmod", None)
        if callable(fchmod):
            fchmod(fd, 0o600)
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
    if source == "claude":
        fields = fields | {"request_model"}
    for record in records:
        if (not isinstance(record, dict) or set(record) != fields
                or record.get("source") != source
                or not all(isinstance(record.get(k), str) for k in ("ts", "date", "model"))
                or not isinstance(record.get("billing"), dict)):
            return False
        if source == "claude" and not isinstance(record.get("request_model"), str):
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


def _cached_codex_keys_valid(records, keys):
    if not isinstance(keys, list) or len(keys) != len(records):
        return False
    return all(key is None or isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key) for key in keys)


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


# Explicit parsing contracts, not a scan of module globals.  Retain the original
# callable/code/defaults so a substituted parser or helper is never "trusted"
# merely because a new round sees the same replacement twice.
def _memo_callable_state(fn):
    return (fn, getattr(fn, "__code__", None), getattr(fn, "__defaults__", None),
            tuple(sorted((getattr(fn, "__kwdefaults__", None) or {}).items())))


def _memo_contracts():
    from . import codex_usage
    common = (
        (config, ("timezone_name",)),
        (sys.modules[__name__], (
            "_to_local_date", "_safe_tokens", "_field_evidence", "_billing_result",
            "_missing_or_invalid", "_encoded_retained_bytes", "_record_retained_bytes",
            "_dedup_retained_bytes", "_cached_records_valid", "_cached_tokens_valid",
            "_cached_billing_valid", "_stat_identity", "_stat_version", "_safe_open_flags",
            "_extend_records")),
        (_SafeReader, ("__init__", "__enter__", "__exit__", "read_chunk", "finish")),
        (_claude_json, ("_utf8_size",)),
        (_claude_json.ProjectionParser, (
            "__init__", "feed", "finish_line", "_check_active", "_discard_after_error",
            "_charge", "_release", "_token", "_new_value", "_value_mode", "_accept_value",
            "_start_value", "_start_key", "_finish_key", "_string_piece", "_flush_high",
            "_unicode_unit", "_consume_string", "_number_piece", "_finish_number",
            "_consume_number", "_literal_piece", "_consume_literal", "_close", "_consume")),
        (_claude_json._Value, ("__init__",)),
        (_claude_json._Member, ("__init__",)),
        (_claude_json._Frame, ("__init__",)),
        (_claude_json._String, ("__init__",)),
        (_claude_json._Number, ("__init__",)),
        (_claude_json._Literal, ("__init__",)),
    )
    own = common[1][0]
    return {
        "claude": common + ((own, (
            "claude_parse", "_claude_parse_state", "_claude_event_record",
            "_claude_line_chunks", "_claude_projected_lines", "_claude_billing",
            "_cached_claude_keys_valid", "_check_claude_budget", "_resolve_model",
            "_tier_of", "_ccr_rules", "_ccr_signature", "_parse_ccr_rules")),),
        "codex": common + ((own, ("codex_parse", "_codex_billing", "_cached_codex_keys_valid")),
                             (codex_usage, ("parse_state", "_events", "_chunks", "_fail",
                                            "_text", "_signature", "_complete_usage", "identity"))),
    }


_MEMO_CONTRACTS = _memo_contracts()
_MEMO_ORIGINALS = {
    source: tuple((owner, name, _memo_callable_state(getattr(owner, name)))
                  for owner, names in groups for name in names)
    for source, groups in _MEMO_CONTRACTS.items()
}
# Binding class objects also detects replacement of a whole projection class.
_MEMO_PROJECTION_TYPES = tuple(getattr(_claude_json, name) for name in (
    "ProjectionParser", "_Value", "_Member", "_Frame", "_String", "_Number", "_Literal"))
_MEMO_SAFE_READER = _SafeReader
_MEMO_DATETIME = datetime


def _memo_namespace_unchecked(source, files_fn, parse_fn):
    """Explicit dependencies of the accepted built-in parse contract only."""
    if SOURCES.get(source) != (files_fn, parse_fn):
        return None
    if source not in _MEMO_ORIGINALS or parse_fn is not {
            "claude": _BUILTIN_CLAUDE_PARSE, "codex": _BUILTIN_CODEX_PARSE}[source]:
        return None
    if (datetime is not _MEMO_DATETIME or _SafeReader is not _MEMO_SAFE_READER
            or tuple(getattr(_claude_json, name) for name in (
            "ProjectionParser", "_Value", "_Member", "_Frame", "_String", "_Number", "_Literal"
    )) != _MEMO_PROJECTION_TYPES):
        return None
    if any(_memo_callable_state(getattr(owner, name)) != original
           for owner, name, original in _MEMO_ORIGINALS[source]):
        return None
    tz = config.TZ
    # No str(tz)-based trust for arbitrary tzinfo, nor mutable system-local TZ.
    if type(tz) is ZoneInfo:
        zone = ("zoneinfo", tz, tz.key)
    elif type(tz) is timezone:
        zone = ("fixed", tz.utcoffset(None), tz.tzname(None))
    else:
        return None
    from . import codex_usage
    projection = (
        tuple((key, tuple(value)) for key, value in sorted(_claude_json._FIELDS.items())),
        _claude_json._SPACE, _claude_json._STRING_SPECIAL, _claude_json._DIGITS,
        _claude_json._HEX, tuple(sorted(_claude_json._ESCAPES.items())),
        _claude_json._CHUNK_BYTES,
        (_claude_json._DROP, _claude_json._FULL, _claude_json._ROOT,
         _claude_json._MESSAGE, _claude_json._USAGE, _claude_json._CODEX_ROOT,
         _claude_json._CODEX_PAYLOAD, _claude_json._CODEX_INFO, _claude_json._CODEX_USAGE),
    )
    common = (
        CACHE_VERSION, config.timezone_name(), zone, files_fn, parse_fn,
        BILLING_SCHEMA, tuple(BILLING_COMPONENTS), _SAFE_INT_MAX,
        tuple(sorted(_RECORD_FIELDS)), tuple(sorted(_BILLING_DICT_KEYS)),
        tuple(sorted(_BILLING_VALIDATORS[source][0].items())),
        _BILLING_VALIDATORS[source][1], MAX_FILE_BYTES, MAX_LINE_BYTES,
        CLAUDE_READ_CHUNK_BYTES, MAX_TOTAL_RECORDS, MAX_TOTAL_RETAINED_BYTES,
        MAX_CACHE_BYTES, projection,
    )
    if source == "claude":
        specific = (config.CLAUDE_PROJECTS, MAX_CLAUDE_RECORDS, MAX_CLAUDE_RETAINED_BYTES,
                    tuple(sorted(_CLAUDE_BILLING_KEYS.items())), _TIER_MODEL_RE,
                    _NEEDLE_RE, _RETURN_RE, _ANY_RETURN_RE)
    else:
        specific = (config.CODEX_SESSIONS, config.CODEX_ARCHIVED_SESSIONS,
                    codex_usage.MAX_RECORDS, codex_usage.MAX_RETAINED_BYTES,
                    codex_usage.MAX_DECOMPRESSED_BYTES, codex_usage.ARCHIVE_TIMEOUT,
                    codex_usage.CHUNK_BYTES, tuple(codex_usage.USAGE_FIELDS),
                    tuple(codex_usage.ANCHOR_FIELDS),
                    tuple(sorted(_CODEX_BILLING_KEYS.items())))
    return common, specific


def _memo_namespace(source, files_fn, parse_fn):
    try:
        return _memo_namespace_unchecked(source, files_fn, parse_fn)
    except (AttributeError, TypeError, ValueError, RecursionError, OverflowError):
        return None  # An unprovable optional contract is a miss, not a new error.


def _memo_router_state():
    """Stat only: use the existing ordered rules, never load router text here.

    Own and target versions matter (a router may itself be a symlink).  This
    does not repair the existing rule cache's mtime/size ABA limitations and is
    not protection from an adversarial same-UID writer.
    """
    path = config.CCR_ROUTER_FILE
    try:
        own = os.lstat(path)
    except FileNotFoundError:
        identity, signature = (path, None, None), ""
    except OSError:
        return None, None
    else:
        try:
            target = os.stat(path)
        except OSError:
            return None, None
        if not stat.S_ISREG(target.st_mode):
            return None, None
        identity = (path, (own.st_mode, _stat_version(own)),
                    (target.st_mode, _stat_version(target)))
        signature = f"{target.st_mtime_ns}|{target.st_size}"
    saved_signature, rules = _ccr_rules_cache
    if saved_signature != signature or not isinstance(rules, list):
        return identity, None
    if any(not isinstance(rule, (tuple, list)) or len(rule) != 2
           or any(type(part) is not str for part in rule) for rule in rules):
        return identity, None
    return identity, tuple(tuple(rule) for rule in rules)


class _ParseMemo:
    """Instance-private LRU; estimates are not an RSS cap (copies are temporary).

    Sequential scans larger than capacity can thrash, including zero warm hits.
    Oversized admission never evicts useful entries just to reject a new item.
    No I/O, raw messages, failures, or whole-collection conclusions are retained.
    """

    def __init__(self, *, max_entries=4096, max_records=100000,
                 max_bytes=64 * 1024 * 1024, max_entry_bytes=8 * 1024 * 1024,
                 max_entry_records=20000):
        self.max_entries = max_entries
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.max_entry_bytes = max_entry_bytes
        self.max_entry_records = max_entry_records
        self._entries = OrderedDict()
        self._namespaces = {}
        self._records = self._bytes = 0

    def discard(self, key):
        entry = self._entries.pop(key, None)
        if entry is not None:
            self._records -= len(entry[1])
            self._bytes -= entry[3]

    def activate(self, source, namespace):
        if namespace is None or self._namespaces.get(source) != namespace:
            for key in list(self._entries):
                if key[0] == source:
                    self.discard(key)
            self._namespaces[source] = namespace

    def get(self, key, version):
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry[0] != version:
            self.discard(key)
            return None
        self._entries.move_to_end(key)
        return deepcopy((entry[1], entry[2]))

    def put(self, key, version, records, dedup):
        # Both trusted parsers preserve the exact timestamp used by
        # _to_local_date in every raw preselection record.  Naive timestamps
        # additionally depend on mutable process-local TZ, even for config.TZ
        # = UTC.  Refuse the whole file instead of changing accepted parsing or
        # claiming a system-timezone identity.  Empty results have no dates.
        try:
            if datetime is not _MEMO_DATETIME or any(
                    type(record.get("ts")) is not str
                    or datetime.fromisoformat(record["ts"].replace("Z", "+00:00")).utcoffset() is None
                    for record in records):
                self.discard(key)
                return
        except (AttributeError, TypeError, ValueError, OverflowError):
            self.discard(key)
            return
        if (self.max_entries <= 0 or len(records) > min(self.max_entry_records, self.max_records)
                or not isinstance(dedup, list) or len(dedup) != len(records)):
            return
        ceiling = min(self.max_entry_bytes, self.max_bytes)
        try:
            # Include path/container bookkeeping and stop before the deep copy.
            cost = 1024 + _encoded_retained_bytes(key)
            if cost > ceiling:
                return
            for record, token in zip(records, dedup):
                cost += _record_retained_bytes(record) + _dedup_retained_bytes(token)
                if cost > ceiling:
                    return
            if (not _cached_records_valid(records, key[0])
                    or not (_cached_claude_keys_valid(records, dedup) if key[0] == "claude"
                            else _cached_codex_keys_valid(records, dedup))):
                return
            saved_records, saved_keys = deepcopy((records, dedup))
        except (TypeError, ValueError, RecursionError, OverflowError):
            return  # Capacity/shape refusal cannot become a new collection failure.
        self.discard(key)
        while self._entries and (len(self._entries) >= self.max_entries
                                 or self._records + len(records) > self.max_records
                                 or self._bytes + cost > self.max_bytes):
            self.discard(next(iter(self._entries)))
        self._entries[key] = version, saved_records, saved_keys, cost
        self._records += len(records)
        self._bytes += cost


class _MemoRound:
    """Per-source round context; at most one explicit context check per file edge."""

    def __init__(self, memo, source, files_fn, parse_fn):
        self.memo, self.source = memo, source
        self.files_fn, self.parse_fn = files_fn, parse_fn
        self.base = _memo_namespace(source, files_fn, parse_fn)
        self.router, rules = _memo_router_state() if source == "claude" else ((), ())
        self.rules = rules
        self.namespace = (self.base, self.router, rules) if (
            self.base is not None and self.router is not None and rules is not None) else None
        memo.activate(source, self.namespace)

    def current(self):
        if self.base is None or _memo_namespace(self.source, self.files_fn, self.parse_fn) != self.base:
            self.memo.activate(self.source, None)
            return False
        router, rules = _memo_router_state() if self.source == "claude" else ((), ())
        if router != self.router or router is None or rules is None or (
                self.rules is not None and self.rules != rules):
            self.memo.activate(self.source, None)
            return False
        # A cold existing router may first populate _ccr_rules_cache during this
        # file's parse.  Its unchanged own/target identity permits admission now.
        self.rules = rules
        self.namespace = (self.base, router, rules)
        self.memo.activate(self.source, self.namespace)
        return True

    def get(self, key, st):
        return self.memo.get(key, _stat_version(st)) if self.current() else None

    def put(self, key, st, records, dedup, stable):
        if stable and self.current():
            self.memo.put(key, _stat_version(st), records, dedup)
        else:
            self.memo.discard(key)


def read_all(sources=None, use_cache=True, observer=None, *, parse_memo=None):
    """所有来源成功才返回/存缓存；Claude 不完整异常不可降级为空成功。"""
    def notify(event, source):
        if observer is not None:
            try:
                observer(event, source)
            except Exception:
                pass  # 旁路观测失败不能改变采集结果或完整性。

    sources = sources or list(SOURCES)
    cache = _load_cache() if use_cache else {}
    seen_keys = set()
    out = []
    retained = 0
    codex_seen = {}
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
        memo_round = (_MemoRound(parse_memo, src, files_fn, parse_fn)
                      if use_cache and parse_memo is not None and src in ("claude", "codex")
                      else None)
        active_memo_key = None
        try:
            files = files_fn()
        except CollectionIncompleteError:
            raise
        except OSError:
            if src in ("claude", "codex"):
                raise CollectionIncompleteError(src, "discovery_failed") from None
            files = []
        try:
            for path in files:
                active_memo_key = (src, path)
                notify("discovered", src)
                skipped = False
                try:
                    st = os.stat(path)
                except OSError:
                    if src in ("claude", "codex"):
                        raise CollectionIncompleteError(src, "stat_failed") from None
                    notify("skipped", src)
                    continue
                if not _safe_to_parse(path, st, source=src):
                    if src in ("claude", "codex"):
                        raise CollectionIncompleteError(src, "unsafe_file")
                    notify("skipped", src)
                    continue
                key = f"{st.st_mtime_ns}|{st.st_size}"
                ckey = src + "::" + path
                seen_keys.add(ckey)
                cached = cache.get(ckey)
                memo_hit = None
                stable = True
                disk_warm = False
                # Disk keeps its existing priority and full validation chain.
                # A controlled safety/budget exception propagates immediately;
                # only a normal miss may try the optional RAM fallback.
                for cache_kind in ("disk", "memo"):
                    if cache_kind == "memo":
                        memo_hit = memo_round.get(active_memo_key, st) if memo_round else None
                        if memo_hit is None:
                            break
                        memo_records, memo_dedup = memo_hit
                        cached = {"key": key, "records": memo_records, "dedup": memo_dedup,
                                  "identity": list(_stat_identity(st)),
                                  "version": list(_stat_version(st))}
                    warm = (use_cache and isinstance(cached, dict) and cached.get("key") == key
                            and _cached_records_valid(cached.get("records"), src))
                    if warm and src == "claude":
                        warm = (cached.get("identity") == list(_stat_identity(st))
                                and cached.get("version") == list(_stat_version(st))
                                and _cached_claude_keys_valid(cached["records"], cached.get("dedup")))
                    if warm and src == "codex":
                        warm = (cached.get("identity") == list(_stat_identity(st))
                                and cached.get("version") == list(_stat_version(st))
                                and _cached_codex_keys_valid(cached["records"], cached.get("dedup")))
                    if warm:
                        recs = cached["records"]
                        dedup = cached.get("dedup")
                        if src == "codex":
                            try:
                                with _SafeReader(path, source=src) as reader:
                                    warm = (_stat_version(reader.initial) == _stat_version(st) and reader.finish())
                            except OSError:
                                raise CollectionIncompleteError(src, "read_failed") from None
                        if src == "claude":
                            _check_claude_budget(recs, cached["dedup"])
                            try:
                                # Warm path still safely opens/fstats/finishes.
                                with _SafeReader(path) as reader:
                                    if _stat_version(reader.initial) != _stat_version(st):
                                        warm = False
                                    else:
                                        warm = reader.finish()
                            except CollectionIncompleteError:
                                raise
                            except OSError:
                                raise CollectionIncompleteError(src, "read_failed") from None
                    if warm and memo_hit is not None and not memo_round.current():
                        warm = False
                    if warm:
                        disk_warm = cache_kind == "disk"
                        break
                memo_proof = None
                if not warm:
                    stable, dedup = True, None
                    try:
                        if src == "claude" and parse_fn is _BUILTIN_CLAUDE_PARSE:
                            if memo_round is not None and memo_round.base is not None:
                                memo_proof = [True]  # This file/call only; never stored.
                                recs, dedup, opened, stable = _claude_parse_state(
                                    path, _memo_proof=memo_proof)
                            else:
                                recs, dedup, opened, stable = _claude_parse_state(path)
                            # pre-stat 到 open 的追加也不能缓存为 pre-stat 版本。
                            stable = stable and _stat_version(opened) == _stat_version(st)
                        elif src == "codex" and parse_fn is _BUILTIN_CODEX_PARSE:
                            from . import codex_usage
                            recs, dedup, opened, stable = codex_usage.parse_state(path)
                            stable = stable and _stat_version(opened) == _stat_version(st)
                        else:
                            recs = parse_fn(path)
                            if src == "claude":
                                _check_claude_budget(recs)
                                stable = False  # 可替换 parser 没有可验证 key，不写 warm 项。
                    except CollectionIncompleteError:
                        raise
                    except OSError:
                        if src in ("claude", "codex"):
                            raise CollectionIncompleteError(src, "read_failed") from None
                        recs = []
                        skipped = True
                    except Exception:
                        if src in ("claude", "codex"):
                            raise CollectionIncompleteError(src, "read_failed") from None
                        recs = []
                        skipped = True
                    if stable:
                        entry = {"key": key, "records": recs}
                        if src in ("claude", "codex"):
                            entry.update(identity=list(_stat_identity(st)),
                                         version=list(_stat_version(st)), dedup=dedup)
                        cache[ckey] = entry
                    else:
                        cache.pop(ckey, None)
                    changed = True
                raw_records = recs
                if src == "codex" and dedup is not None:
                    selected = []
                    for record, token in zip(recs, dedup):
                        if token is not None:
                            if token in codex_seen:
                                previous = codex_seen[token]
                                if any(previous[k] != record[k] for k in ("model", "input", "output", "cache_read", "total", "billing")):
                                    raise CollectionIncompleteError(
                                        src, "usage_conflict", conflict_kind="cross_file_identity_mismatch")
                                continue
                            codex_seen[token] = record
                        selected.append(record)
                    recs = selected
                retained = _extend_records(out, recs, retained)
                if memo_round is not None and not disk_warm:
                    if src == "claude" and not warm and memo_proof != [True]:
                        parse_memo.discard(active_memo_key)
                    else:
                        memo_round.put(active_memo_key, st, raw_records, dedup, stable)
                if memo_hit is not None and warm:
                    # The disk schema/timing stays unchanged; no mutable memo
                    # containers escape into the local disk-cache transaction.
                    cache[ckey] = cached
                    changed = True
                notify("skipped" if skipped else
                       "processed_cached" if warm else "processed_parsed", src)
                active_memo_key = None
        except CollectionIncompleteError:
            if memo_round is not None and active_memo_key is not None:
                parse_memo.discard(active_memo_key)
            raise
        except OSError:
            if memo_round is not None and active_memo_key is not None:
                parse_memo.discard(active_memo_key)
            if src in ("claude", "codex"):
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
