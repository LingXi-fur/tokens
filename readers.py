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

total 口径说明：
  claude : input + output + cache_read + cache_write
  gemini : tokens.total（= input + output + cached + thoughts + tool）
  codex  : total_tokens（input_tokens 已含 cached_input_tokens，故不重复加）
"""
import json
import os
import re
import glob
import stat
import tempfile
from datetime import datetime

import config

# 缓存结构版本：解析口径变更后旧 cache.json 作废、强制重读。
#   v1 = 初版（含 Claude 重复 message.id 导致总量夸大）
#   v2 = Claude 按 message.id 去重
#   v3 = record 增 cwd 字段（项目维度 Top 榜需要）
CACHE_VERSION = 3

# 单文件大小上限：防恶意/失控日志吃光内存（OOM）。超出直接跳过。
MAX_FILE_BYTES = 64 * 1024 * 1024  # 64 MB
# 单行长度上限（jsonl）：防无换行的巨型行。
MAX_LINE_BYTES = 4 * 1024 * 1024   # 4 MB


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
    """ISO 字符串 → 本地时区小时(0-23)。无效返回 None。用于「作息时钟」。"""
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
                })
    except OSError:
        pass
    return out


def session_file(session_id):
    """sessionId → ~/.claude/projects/**/<sessionId>.jsonl（找不到返回 None）。"""
    if not session_id or not os.path.isdir(config.CLAUDE_PROJECTS):
        return None
    hits = glob.glob(os.path.join(config.CLAUDE_PROJECTS, "**", str(session_id) + ".jsonl"), recursive=True)
    return hits[0] if hits else None


def session_title(session_id, max_len=60):
    """从会话首条有效用户提问提取标题（离线、隐私安全）。

    Claude 日志里 sessionId 即文件名；取第一条非空、非命令/系统包络的用户文本。
    没有则返回空串，由调用方回退到短 id。
    """
    path = session_file(session_id)
    if not path:
        return ""
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
                if not isinstance(o, dict) or o.get("type") != "user":
                    continue
                msg = o.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "text":
                            text = b.get("text", "")
                            break
                text = (text or "").strip()
                if not text or text.startswith("<") or text.lower().startswith("caveat"):
                    continue
                first = re.split(r"[\r\n]+", text, 1)[0].strip()
                first = re.sub(r"\s+", " ", first)
                if len(first) < 3:
                    continue
                return first[:max_len]
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
    os.makedirs(config.OUT_DIR, exist_ok=True)
    cache["_v"] = CACHE_VERSION
    # mkstemp：随机名 + 不跟软链 + 默认 0600，杜绝可预测临时名竞争与世界可读泄漏。
    fd, tmp = tempfile.mkstemp(prefix=".cache-", dir=config.OUT_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, config.CACHE_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_all(sources=None, use_cache=True):
    """读所有源，返回 record 列表。按文件 mtime+size 缓存，未变则秒出。"""
    sources = sources or list(SOURCES)
    cache = _load_cache() if use_cache else {}
    seen_keys = set()
    out = []
    changed = False

    # 缓存结构版本：解析口径变更（如 Claude 按 message.id 去重）后旧缓存作废。
    if use_cache and cache.get("_v") != CACHE_VERSION:
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
        _save_cache(cache)
    return out
