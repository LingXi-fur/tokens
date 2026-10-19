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
import os
import re
import stat
import tempfile
from datetime import datetime

from . import config

# 缓存结构版本：解析口径变更后旧 cache.json 作废、强制重读。
#   v1 = 初版（含 Claude 重复 message.id 导致总量夸大）
#   v2 = Claude 按 message.id 去重
#   v3 = record 增 cwd 字段（项目维度 Top 榜需要）
#   v4 = Claude request aliases may resolve through the user's current CCR router
#   v5 = record 新增 billing 计费证据（schema 1，独立于既有用量统计）
CACHE_VERSION = 5

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

# 单文件大小上限：防恶意/失控日志吃光内存（OOM）。超出直接跳过。
MAX_FILE_BYTES = 64 * 1024 * 1024  # 64 MB
# 单行长度上限（jsonl）：防无换行的巨型行。
MAX_LINE_BYTES = 4 * 1024 * 1024   # 4 MB

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
    if not os.path.isdir(config.CLAUDE_PROJECTS):
        return []
    return glob.glob(os.path.join(config.CLAUDE_PROJECTS, "**", "*.jsonl"), recursive=True)


def claude_parse(path):
    out = []
    # 同一 assistant turn（message.id）会被 jsonl 重复写入数十次（router/重试产物）。
    # 按 message.id 去重，否则单日总量被夸大数倍。
    seen_ids = set()
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
                if not isinstance(o, dict) or o.get("type") != "assistant":
                    continue
                msg = o.get("message")
                if not isinstance(msg, dict):
                    continue
                model = msg.get("model")
                if not model or model == "<synthetic>":
                    continue
                usage = msg.get("usage") or {}
                ts = o.get("timestamp")
                date = _to_local_date(ts)
                if not date:
                    continue
                # Resolve only Claude request aliases matched by this user's router.
                model = _resolve_model(model)
                inp = usage.get("input_tokens", 0)
                outp = usage.get("output_tokens", 0)
                cread = usage.get("cache_read_input_tokens", 0)
                cwrite = usage.get("cache_creation_input_tokens", 0)
                # 去重键：优先 message.id；缺失则退化为 (ts, model, 用量) 元组。
                mid = msg.get("id")
                dkey = mid if mid else (ts, model, inp, outp, cread, cwrite)
                if dkey in seen_ids:
                    continue
                seen_ids.add(dkey)
                out.append({
                    "source": "claude",
                    "ts": ts,
                    "date": date,
                    "model": model,
                    "input": inp,
                    "output": outp,
                    "cache_read": cread,
                    "cache_write": cwrite,
                    "total": inp + outp + cread + cwrite,
                    "session": o.get("sessionId"),
                    "cwd": o.get("cwd"),
                    "billing": _claude_billing(usage),
                })
    except OSError:
        pass
    return out


def build_session_index():
    """一次扫描 Claude 日志目录，返回 session id → 文件路径。"""
    if not os.path.isdir(config.CLAUDE_PROJECTS):
        return {}
    return {
        os.path.splitext(os.path.basename(path))[0]: path
        for path in claude_files()
    }


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


def _safe_to_parse(path, st):
    """只解析真实普通文件：拒软链 / FIFO / 设备文件 / 超大文件。"""
    if os.path.islink(path):
        return False
    if not stat.S_ISREG(st.st_mode):
        return False
    if st.st_size > MAX_FILE_BYTES:
        return False
    return True


def _load_cache():
    try:
        with open(config.CACHE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    cache["_v"] = CACHE_VERSION
    fd, tmp = tempfile.mkstemp(prefix=".records-", dir=config.CACHE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, separators=(",", ":"))
        os.chmod(tmp, 0o600)
        os.replace(tmp, config.CACHE_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_all(sources=None, use_cache=True):
    """读所有源，返回 record 列表。按统计时区及文件 mtime+size 缓存。"""
    sources = sources or list(SOURCES)
    cache = _load_cache() if use_cache else {}
    seen_keys = set()
    out = []
    changed = False

    # 缓存结构版本：解析口径变更（如 Claude 按 message.id 去重）后旧缓存作废。
    if use_cache and cache.get("_v") != CACHE_VERSION:
        cache = {}
        changed = True

    # Cached dates depend on the reporting timezone, not just file contents.
    timezone_key = config.timezone_name()
    if use_cache and (timezone_key == "system local time" or cache.get("_timezone") != timezone_key):
        cache = {}
        changed = True

    # A local CCR router change can alter alias resolution, so rebuild records.
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
        except OSError:
            files = []
        for path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue
            if not _safe_to_parse(path, st):
                continue
            key = f"{st.st_mtime_ns}|{st.st_size}"
            ckey = src + "::" + path
            seen_keys.add(ckey)
            cached = cache.get(ckey)
            if use_cache and cached and cached.get("key") == key:
                out.extend(cached["records"])
            else:
                # 单文件解析异常（恶意/畸形）不拖垮整次运行。
                try:
                    recs = parse_fn(path)
                except Exception:
                    recs = []
                cache[ckey] = {"key": key, "records": recs}
                changed = True
                out.extend(recs)

    # 清理已消失文件的缓存条目
    stale = [k for k in cache if k.split("::", 1)[0] in sources and k not in seen_keys]
    for k in stale:
        cache.pop(k, None)
        changed = True

    if changed and use_cache:
        cache["_router"] = router_sig
        cache["_timezone"] = timezone_key
        _save_cache(cache)
    return out
