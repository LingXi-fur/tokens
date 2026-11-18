"""Read-only Antigravity conversation SQLite usage reader.

Only usage metadata (token counts, model name, step timestamp, and opaque IDs)
is extracted. Conversation payloads and summaries are never queried or retained.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import sqlite3
from urllib.parse import quote

from . import readers

ROOT = os.environ.get("TOKENS_ANTIGRAVITY_DIR") or os.path.expanduser(
    "~/.gemini/antigravity/conversations"
)

# Module-level counter for records skipped due to missing/unmatched step timestamps
# (exposed for future `doctor` diagnostics).
MISSING_TIME_COUNT = 0

_WIRE_VARINT = 0
_WIRE_FIXED64 = 1
_WIRE_BYTES = 2
_WIRE_FIXED32 = 5


class _BadProtobuf(Exception):
    """Raised when a protobuf payload is truncated, malformed, or uses an unknown wire type."""


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    end = len(buf)
    while True:
        if pos >= end or shift >= 70:
            raise _BadProtobuf("truncated or oversized varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, pos
        shift += 7


def _iter_fields(buf: bytes):
    """Yield (field_number, wire_type, value) from a protobuf message."""
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = _read_varint(buf, pos)
        field_num = key >> 3
        wire_type = key & 7
        if field_num == 0:
            raise _BadProtobuf("invalid field number 0")
        if wire_type == _WIRE_VARINT:
            val, pos = _read_varint(buf, pos)
            yield field_num, wire_type, val
        elif wire_type == _WIRE_FIXED64:
            if pos + 8 > end:
                raise _BadProtobuf("truncated fixed64")
            yield field_num, wire_type, buf[pos : pos + 8]
            pos += 8
        elif wire_type == _WIRE_FIXED32:
            if pos + 4 > end:
                raise _BadProtobuf("truncated fixed32")
            yield field_num, wire_type, buf[pos : pos + 4]
            pos += 4
        elif wire_type == _WIRE_BYTES:
            length, pos = _read_varint(buf, pos)
            if length < 0 or pos + length > end:
                raise _BadProtobuf("truncated length-delimited field")
            yield field_num, wire_type, buf[pos : pos + length]
            pos += length
        else:
            raise _BadProtobuf(f"unknown wire type {wire_type}")


def _connect_ro(path: str) -> sqlite3.Connection:
    uri = "file:" + quote(os.path.abspath(path)) + "?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True, timeout=2)
    except sqlite3.Error:
        return sqlite3.connect(uri + "&immutable=1", uri=True, timeout=2)


def _decode_utf8(raw: bytes) -> str | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if text else None


def _extract_step_timestamps(con: sqlite3.Connection) -> dict[int, int]:
    """Read only (idx, metadata) from steps and map idx -> Unix seconds (metadata.1.1)."""
    step_ts: dict[int, int] = {}
    for idx, meta in con.execute("SELECT idx, metadata FROM steps"):
        if type(idx) is not int or not isinstance(meta, (bytes, bytearray)):
            continue
        meta_bytes = bytes(meta)
        try:
            for f1, wt1, val1 in _iter_fields(meta_bytes):
                if f1 == 1 and wt1 == _WIRE_BYTES:
                    for f2, wt2, val2 in _iter_fields(val1):
                        if f2 == 1 and wt2 == _WIRE_VARINT and val2 > 0:
                            step_ts[idx] = val2
                            break
        except _BadProtobuf:
            continue
    return step_ts


def _parse_usage(raw_usage: bytes) -> tuple[int, int, int] | None:
    """Decode field 1.4: (input=1.4.2, output=1.4.3, cache_read=1.4.5).

    1.4.9 and 1.4.10 are output sub-breakdowns and are intentionally ignored
    so they are never double-counted.
    """
    inp = 0
    outp = 0
    cache_read = 0
    for f, wt, val in _iter_fields(raw_usage):
        if wt != _WIRE_VARINT:
            continue
        if f == 2:
            inp = val
        elif f == 3:
            outp = val
        elif f == 5:
            cache_read = val
    return inp, outp, cache_read


def _parse_kv_entry(raw_kv: bytes) -> tuple[str | None, bytes | None]:
    key = None
    val = None
    for f, wt, v in _iter_fields(raw_kv):
        if f == 1 and wt == _WIRE_BYTES:
            key = _decode_utf8(v)
        elif f == 2 and wt == _WIRE_BYTES:
            val = v
    return key, val


def _parse_gen_row(raw_data: bytes) -> dict | None:
    """Parse one gen_metadata.data blob. Returns None if malformed or lacking 1.4."""
    outer_1: bytes | None = None
    for f, wt, val in _iter_fields(raw_data):
        if f == 1 and wt == _WIRE_BYTES:
            outer_1 = val
            break
    if outer_1 is None:
        return None

    usage_bytes: bytes | None = None
    model: str | None = None
    kv: dict[str, bytes] = {}

    for f, wt, val in _iter_fields(outer_1):
        if f == 4 and wt == _WIRE_BYTES:
            usage_bytes = val
        elif f == 19 and wt == _WIRE_BYTES:
            model = _decode_utf8(val)
        elif f == 20 and wt == _WIRE_BYTES:
            k, v = _parse_kv_entry(val)
            if k is not None and v is not None:
                kv[k] = v

    if usage_bytes is None:
        return None

    usage = _parse_usage(usage_bytes)
    if usage is None:
        return None

    inp, outp, cache_read = usage
    request_id = _decode_utf8(kv["request_id"]) if "request_id" in kv else None
    cascade_id = _decode_utf8(kv["cascade_id"]) if "cascade_id" in kv else None

    step_index: int | None = None
    if "last_step_index" in kv:
        raw_idx = kv["last_step_index"]
        try:
            step_index = int(raw_idx.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            step_index = None

    return {
        "usage": (inp, outp, cache_read),
        "model": model or "antigravity-unknown",
        "request_id": request_id,
        "cascade_id": cascade_id,
        "step_index": step_index,
    }


def _get_root() -> str:
    return os.environ.get("TOKENS_ANTIGRAVITY_DIR") or ROOT


def discover() -> list[str]:
    """List *.db files under the Antigravity conversations directory without opening them."""
    root = _get_root()
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    paths: list[str] = []
    for name in names:
        if not name.endswith(".db") or name == "conversation_summaries.db":
            continue
        full = os.path.join(root, name)
        if os.path.isfile(full):
            paths.append(full)
    return paths


def parse(path: str) -> list[dict]:
    """Parse usage records from a single Antigravity conversation SQLite database."""
    global MISSING_TIME_COUNT

    if os.path.basename(path) == "conversation_summaries.db":
        return []

    out: list[dict] = []
    seen_requests: set[str] = set()

    try:
        con = _connect_ro(path)
    except sqlite3.Error:
        return out

    try:
        step_ts = _extract_step_timestamps(con)
        rows = con.execute("SELECT data FROM gen_metadata").fetchall()
    except sqlite3.Error:
        return out
    finally:
        con.close()

    for (raw_data,) in rows:
        if not isinstance(raw_data, (bytes, bytearray)):
            continue
        try:
            parsed = _parse_gen_row(bytes(raw_data))
        except _BadProtobuf:
            continue
        if parsed is None:
            continue

        inp, outp, cache_read = parsed["usage"]
        if inp + outp + cache_read == 0:
            continue

        req_id = parsed["request_id"]
        if req_id is not None:
            if req_id in seen_requests:
                continue
            seen_requests.add(req_id)

        step_idx = parsed["step_index"]
        unix_sec = step_ts.get(step_idx) if step_idx is not None else None
        if unix_sec is None or unix_sec <= 0:
            MISSING_TIME_COUNT += 1
            continue

        try:
            ts = datetime.fromtimestamp(unix_sec, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except (OverflowError, OSError, ValueError):
            MISSING_TIME_COUNT += 1
            continue

        date = readers._to_local_date(ts)
        if not date:
            MISSING_TIME_COUNT += 1
            continue

        billing = readers._antigravity_billing({
            "input": inp,
            "output": outp,
            "cache_read": cache_read,
        })
        out.append({
            "source": "antigravity",
            "ts": ts,
            "date": date,
            "model": parsed["model"],
            "input": inp,
            "output": outp,
            "cache_read": cache_read,
            "cache_write": 0,
            "total": inp + outp + cache_read,
            "session": parsed["cascade_id"],
            "billing": billing,
        })

    return out
