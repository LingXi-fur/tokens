"""Bounded Codex usage projection, archive streaming and event identity.

Only usage metadata leaves this module. Conversation content is never retained.
"""
import collections
import hashlib
import json
import math
import os
import selectors
import shutil
import subprocess
import time

from . import _claude_json, config

MAX_RECORDS = 100_000
MAX_RETAINED_BYTES = 64 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
ARCHIVE_TIMEOUT = 120
CHUNK_BYTES = 64 * 1024
USAGE_FIELDS = (
    "input_tokens", "output_tokens", "cached_input_tokens",
    "cache_write_input_tokens", "reasoning_output_tokens", "total_tokens",
)
# Standard producer fields; cache_write_input_tokens is optional in older logs.
ANCHOR_FIELDS = tuple(name for name in USAGE_FIELDS if name != "cache_write_input_tokens")


def _fail(reason, *, conflict_kind=None, mismatch_kind=None):
    from .readers import CollectionIncompleteError
    raise CollectionIncompleteError("codex", reason, conflict_kind=conflict_kind,
                                    mismatch_kind=mismatch_kind)


def _text(value):
    return value if isinstance(value, str) and value else None


def _signature(value):
    return tuple(value.get(k, 0) for k in USAGE_FIELDS)


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def discover():
    paths, seen = [], set()
    for root in (config.CODEX_SESSIONS, config.CODEX_ARCHIVED_SESSIONS):
        try:
            os.stat(root)
        except FileNotFoundError:
            continue
        except OSError:
            _fail("discovery_failed")
        def onerror(error):
            _fail("discovery_failed")
        for base, directories, names in os.walk(root, followlinks=False, onerror=onerror):
            directories[:] = sorted(d for d in directories if not d.startswith("."))
            for name in sorted(names):
                if not name.startswith("rollout-") or not name.endswith((".jsonl", ".jsonl.zst")):
                    continue
                path = os.path.join(base, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    _fail("stat_failed")
                # Reject unsafe aliases at collection time rather than following them.
                key = (st.st_dev, st.st_ino)
                if key not in seen:
                    seen.add(key)
                    paths.append(path)
    return paths


def _chunks(reader, compressed):
    if not compressed:
        while reader.remaining:
            yield reader.read_chunk()
        return
    executable = shutil.which("zstd")
    if not executable:
        _fail("decompressor_unavailable")
    process = None
    try:
        # Feed only bytes from the verified initial-length reader, never a path.
        process = subprocess.Popen(
            [executable, "-q", "-d", "-c"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stdin.fileno(), False)
        total, pending = 0, b""
        deadline = time.monotonic() + ARCHIVE_TIMEOUT
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            output_done = False
            while not output_done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _fail("decompression_limit")
                ready = selector.select(remaining)
                if not ready:
                    _fail("decompression_limit")
                for key, _ in ready:
                    if key.fileobj is process.stdin:
                        if not pending and reader.remaining:
                            pending = reader.read_chunk()
                        if pending:
                            written = os.write(process.stdin.fileno(), pending)
                            pending = pending[written:]
                        if not pending and not reader.remaining:
                            selector.unregister(process.stdin)
                            process.stdin.close()
                    else:
                        chunk = os.read(process.stdout.fileno(), CHUNK_BYTES)
                        if not chunk:
                            output_done = True
                            break
                        total += len(chunk)
                        if total > MAX_DECOMPRESSED_BYTES:
                            _fail("decompression_limit")
                        yield chunk
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            _fail("decompression_failed")
    except (OSError, ValueError, NotImplementedError, subprocess.TimeoutExpired):
        _fail("decompression_failed")
    finally:
        if process is not None:
            process.stdout.close()
            process.stdin.close()
            if process.poll() is None:
                process.kill()
            process.wait()


def _events(chunks):
    parser = None
    bad = False
    for chunk in chunks:
        start = 0
        while start < len(chunk):
            end = chunk.find(b"\n", start)
            finished = end >= 0
            stop = end if finished else len(chunk)
            if not bad:
                try:
                    if parser is None:
                        parser = _claude_json.ProjectionParser(profile="codex")
                    parser.feed(memoryview(chunk)[start:stop])
                    if finished:
                        yield parser.finish_line()
                except _claude_json.BadJSON:
                    bad = True
                except _claude_json.ProjectionLimit as exc:
                    _fail(exc.reason)
            if finished:
                parser, bad = None, False
            start = stop + 1 if finished else stop
    if parser is not None and not bad:
        try:
            yield parser.finish_line()
        except _claude_json.BadJSON:
            pass  # An append-in-progress tail is retried on the next scan.
        except _claude_json.ProjectionLimit as exc:
            _fail(exc.reason)


def _complete_usage(usage):
    """Require explicit standard counters, with no bools, floats or nulls."""
    return (isinstance(usage, dict) and all(name in usage for name in ANCHOR_FIELDS)
            and all(type(value) is int and value >= 0 for value in usage.values()))


def parse_state(path):
    from . import readers
    modern, old = [], []
    new_seen, old_seen = {}, {}
    session, model = None, None
    retained = 0
    # Only the last legacy anchor and its complete cumulative-evidence flag.
    prior = None

    def append(target, item):
        nonlocal retained
        retained += readers._encoded_retained_bytes(item)
        if len(modern) + len(old) >= MAX_RECORDS:
            _fail("record_limit")
        if retained > MAX_RETAINED_BYTES:
            _fail("retained_bytes_limit")
        target.append(item)

    try:
        with readers._SafeReader(path, source="codex") as reader:
            for obj in _events(_chunks(reader, str(path).endswith(".zst"))):
                if not isinstance(obj, dict) or not isinstance(obj.get("payload"), dict):
                    continue
                payload = obj["payload"]
                kind = obj.get("type")
                if kind == "session_meta":
                    next_session = _text(payload.get("id")) or _text(payload.get("session_id")) or session
                    next_model = _text(payload.get("model")) or model
                    if (next_session, next_model) != (session, model):
                        prior = None
                    session, model = next_session, next_model
                    continue
                if kind == "turn_context" or (kind == "event_msg" and payload.get("type") == "turn_context"):
                    next_model = _text(payload.get("model")) or model
                    if next_model != model:
                        prior = None
                    model = next_model
                    continue
                is_new = kind == "token_usage_record"
                if is_new:
                    # Modern persist is unordered against legacy accounting;
                    # it must not reset legacy adjacency evidence.
                    usage = payload.get("usage")
                elif kind == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        prior = None
                        continue
                    usage = info.get("last_token_usage")
                else:
                    continue
                if not isinstance(usage, dict) or not usage:
                    if is_new:
                        _fail("usage_invalid")
                    prior = None
                    continue
                ts = obj.get("timestamp")
                date = readers._to_local_date(ts)
                if not date:
                    _fail("usage_invalid")
                # New events require integer evidence. Legacy display values stay
                # compatible; billing independently marks their evidence uncertain.
                for name, value in usage.items():
                    if is_new:
                        valid = type(value) is int and 0 <= value <= 9007199254740991
                    else:
                        valid = (isinstance(value, (int, float)) and
                                 (not isinstance(value, float) or math.isfinite(value)))
                        valid = valid or (value is None and name in (
                            "input_tokens", "cached_input_tokens"))
                    if not valid:
                        _fail("usage_invalid")
                inp, outp, cached = (usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cached_input_tokens"))
                total = usage.get("total_tokens")
                if total is None or (not is_new and not total):
                    if inp is None:
                        _fail("usage_invalid")
                    total = inp + outp
                record = {
                    "source": "codex", "ts": ts, "date": date,
                    "model": model or "codex-unknown", "input": inp,
                    "output": outp, "cache_read": cached, "cache_write": 0,
                    "total": total,
                    "session": None, "billing": readers._codex_billing(usage),
                }
                signature = _signature(usage)
                if is_new:
                    sid = _text(payload.get("thread_id")) or _text(payload.get("session_id")) or session
                    response = _text(payload.get("response_id"))
                    if not sid or not response:
                        _fail("usage_identity_missing")
                    key = identity("response", sid, response)
                    if key in new_seen:
                        if new_seen[key] != (signature, record["model"], record["billing"]):
                            _fail("usage_conflict", conflict_kind="modern_response_mismatch")
                        continue
                    append(modern, (record, key, signature))
                    new_seen[key] = (signature, record["model"], record["billing"])
                else:
                    cumulative = info.get("total_token_usage")
                    key = None
                    adjacent, prior = prior, None
                    if isinstance(cumulative, dict) and cumulative:
                        if any(type(v) is not int or v < 0 for v in cumulative.values()):
                            _fail("usage_invalid")
                        # Real producers recompute cumulative counters downward
                        # mid-session; a lower total is a new ledger baseline,
                        # not a conflict. Per-anchor dedup and anchor-mismatch
                        # checks still guard against double counting within
                        # either baseline.
                        # Session-less legacy logs retain their own file identity only.
                        anchor = identity("legacy", session or os.path.realpath(path), _signature(cumulative))
                        prior = (anchor, _complete_usage(cumulative))
                        current = (signature, record["model"], record["billing"])
                        if anchor in old_seen:
                            # v17 first-sight accounting: real producers
                            # rewrite the same cumulative snapshot after a
                            # resume — including across a model change — so a
                            # repeated anchor keeps the first record's usage,
                            # model and billing and ignores every later one.
                            # Zero/estimate state updates stay recognized for
                            # adjacency bookkeeping; dedup still guarantees the
                            # anchor counts exactly once.
                            continue
                        key = anchor
                        old_seen[anchor] = current
                    append(old, (record, key, signature))
            stable = reader.finish()
            opened = reader.initial
    except readers.CollectionIncompleteError:
        raise
    except OSError:
        _fail("read_failed")
    if modern and old:
        # Union accounting: modern entries whose (usage, model, billing) value
        # matches a legacy entry mirror it and are absorbed; the surplus has
        # no legacy evidence and joins the ledger as an independent
        # consumption (real producers persist incomplete responses in the
        # modern format only).
        def mirror_key(item):
            record = item[0]
            return (item[2], record["model"],
                    json.dumps(record["billing"], sort_keys=True))
        surplus = collections.Counter(map(mirror_key, modern))
        surplus -= collections.Counter(map(mirror_key, old))
        buckets = {}
        for item in modern:
            buckets.setdefault(mirror_key(item), []).append(item)
        for key, count in surplus.items():
            for source in buckets[key][:count]:
                append(old, source)
    # After absorption the legacy list holds the whole union; modern-only
    # files have no legacy evidence, so their records remain the record.
    chosen = old or modern
    return [r for r, _, _ in chosen], [k for _, k, _ in chosen], opened, stable
