"""Fail-closed, single-file storage for a successful local Dashboard wire.

Construction is configuration-only. No log, title-sidecar body, router body, or
records cache is read. POSIX descriptors pin every directory and the target;
unsafe existing objects are cache misses, never repaired or removed.
"""
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from . import config, dashboard_payload, dashboard_wire, readers


STORAGE_SCHEMA = 1
MAX_BYTES = 32 * 1024 * 1024
MAX_DECODED_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 500_000
_DIRFD_CAPABLE = (os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
                  and os.mkdir in os.supports_dir_fd and os.rename in os.supports_dir_fd)
_CODE_MAX_BYTES = 8 * 1024 * 1024
_CODE_FILES = tuple(os.path.join(os.path.dirname(__file__), name) for name in (
    "config.py", "readers.py", "_claude_json.py", "codex_usage.py",
    "aggregate.py", "dashboard_payload.py", "dashboard_wire.py", "live_snapshot.py",
))
_PAYLOAD_KEYS = frozenset((
    "generated", "calendar_day", "snapshot", "anonymized", "source", "range",
    "models", "other_models", "pretty", "colors", "cache_read", "hourly",
    "day_details", "block", "top_cwds", "session_series", "session_context",
    "n_cwds", "n_sessions", "max_turns", "provenance", "achievement_stats",
    "achievement_daily", "reuse", "day", "week", "month", "cost",
    "request_models",
))
_REF = re.compile(r"(?:0|[1-9a-z][0-9a-z]*)\Z")
_TOP_SESSION_CONTEXT = frozenset(("p", "pm", "s", "d0", "d1"))
_PROVENANCE = frozenset((
    "records", "total", "valid_ts", "with_cwd", "with_session", "replay_eligible",
    "replay_retained", "with_input", "with_output", "with_cache_read",
    "with_cache_write", "with_components", "first_day", "last_day", "sources",
))
_SOURCE_COUNTS = _PROVENANCE - {"sources", "replay_eligible", "replay_retained"}
_ACHIEVEMENT_STATS = frozenset((
    "input", "output", "cache_write", "session_totals", "cwd_totals",
    "source_totals", "model_stats", "first_day", "last_day",
))
_MODEL_STATS = frozenset(("input", "output", "cache_read", "cache_write", "calls"))
_DAY_DETAIL = frozenset((
    "hourly", "hourly_models", "cache_read", "cache_read_models", "cwds",
    "sessions", "top_cwds", "top_sessions", "flow",
))
_FLOW = frozenset(("project_model", "model_session"))
_PERIOD = frozenset(("period", "total", "calls", "models", "model_calls"))
# day 行独有：请求名 → 后端 → 别名 token 累积（信息性；week/month 不带）。
_DAY_PERIOD = _PERIOD | {"request_models"}
_REQUEST_MODEL_ENTRY = frozenset(("request", "model", "source", "total"))
_BUCKET = frozenset(("h", "total"))
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX24 = re.compile(r"[0-9a-f]{24}\Z")


def _require(condition):
    if not condition:
        raise ValueError("invalid snapshot")


def _date(value, optional=False):
    if optional and value is None:
        return
    _require(type(value) is str and len(value) == 10)
    _require(date.fromisoformat(value).isoformat() == value)


def _checked_at(value):
    _require(type(value) is str and 1 <= len(value) <= 64 and "T" in value)
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None)


def _timezone():
    tz = config.TZ
    if isinstance(tz, ZoneInfo) and tz.key:
        return {"name": tz.key, "kind": "zoneinfo"}
    if isinstance(tz, timezone):
        return {"name": str(tz), "kind": "fixed", "offset": tz.utcoffset(None).total_seconds()}
    return None


def _supported():
    return (os.name == "posix" and sys.platform != "win32"
            and hasattr(os, "getuid") and hasattr(os, "O_NOFOLLOW")
            and hasattr(os, "O_DIRECTORY") and _DIRFD_CAPABLE)


def _quoted(value):
    """Escape bounded pieces, rather than allocating a whole escaped string."""
    yield b'"'
    for start in range(0, len(value), 4096):
        yield json.encoder.encode_basestring(value[start:start + 4096])[1:-1].encode("utf-8")
    yield b'"'


def _json_chunks(value, limit=None):
    """Iterative canonical JSON, with depth, node, cycle and byte budgets."""
    limit = MAX_BYTES if limit is None else limit
    stack = [("value", value, 0)]
    active = set()
    nodes = 0
    total = 0
    while stack:
        kind, item, depth = stack.pop()
        if kind == "literal":
            chunks = (item,)
        elif kind == "container":
            iterator, first, identity, closing = item
            try:
                key, child = next(iterator)
            except StopIteration:
                active.remove(identity)
                chunks = (closing,)
            else:
                stack.append(("container", (iterator, False, identity, closing), depth))
                stack.append(("value", child, depth + 1))
                if key is not None:
                    stack.append(("literal", b":", depth))
                    stack.append(("value", key, depth + 1))
                chunks = () if first else (b",",)
        else:
            nodes += 1
            _require(nodes <= MAX_NODES and depth <= MAX_DEPTH)
            value_type = type(item)
            if value_type is str:
                _require(len(item) <= limit)
                chunks = _quoted(item)
            elif value_type is dict or value_type is list:
                identity = id(item)
                _require(identity not in active)
                active.add(identity)
                if value_type is dict:
                    _require(len(item) <= MAX_NODES)
                    _require(all(type(key) is str for key in item))
                    iterator = iter(sorted(item.items()))
                    opening, closing = b"{", b"}"
                else:
                    iterator = ((None, child) for child in item)
                    opening, closing = b"[", b"]"
                stack.append(("container", (iterator, True, identity, closing), depth))
                chunks = (opening,)
            elif item is None:
                chunks = (b"null",)
            elif value_type is bool:
                chunks = (b"true" if item else b"false",)
            elif value_type is int:
                _require(item.bit_length() <= 256)
                chunks = (str(item).encode("ascii"),)
            elif value_type is float:
                _require(math.isfinite(item))
                chunks = (repr(item).encode("ascii"),)
            else:
                raise ValueError("invalid snapshot")
        for chunk in chunks:
            total += len(chunk)
            _require(total <= limit)
            yield chunk


def _encoded(value, limit=None):
    result = bytearray()
    for chunk in _json_chunks(value, limit):
        result.extend(chunk)
    return bytes(result)


def _digest(value, limit=None):
    digest = hashlib.sha256()
    for chunk in _json_chunks(value, limit):
        digest.update(chunk)
    return digest.hexdigest()


def _scan_json(raw):
    """Count tokens/depth before the stdlib decoder allocates any containers."""
    _require(len(raw) <= MAX_BYTES)
    depth = nodes = 0
    in_string = escaped = primitive = False
    for char in raw:
        if in_string:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                in_string = False
            continue
        if char in (123, 91):
            depth += 1
            nodes += 1
            primitive = False
            _require(depth <= MAX_DEPTH)
        elif char in (125, 93):
            depth -= 1
            primitive = False
            _require(depth >= 0)
        elif char == 34:
            nodes += 1
            in_string = True
            primitive = False
        elif char in (32, 9, 10, 13, 44, 58):
            primitive = False
        elif not primitive:
            nodes += 1
            primitive = True
        _require(nodes <= MAX_NODES)
    _require(depth == 0 and not in_string)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _number(value):
    _require(len(value) <= 80)
    result = float(value)
    _require(math.isfinite(result))
    return result


def _integer(value):
    _require(len(value) <= 80)
    result = int(value)
    _require(result.bit_length() <= 256)
    return result


def _constant(_value):
    raise ValueError("invalid snapshot")


def _parsed(raw):
    _require(len(raw) <= MAX_BYTES and b"\x00" not in raw)
    text = raw.decode("utf-8", errors="strict")
    _scan_json(raw)
    result = json.loads(text, object_pairs_hook=_pairs, parse_int=_integer,
                        parse_float=_number, parse_constant=_constant)
    # Reject lone surrogates, unsupported scalars and excess decoded structure.
    _digest(result)
    return result


def _decode_wire(wire):
    _require(type(wire) is dict and set(wire) == {"v", "s", "d"})
    _require(type(wire["v"]) is int and wire["v"] == dashboard_wire.WIRE_VERSION)
    table = wire["s"]
    _require(type(table) is list and len(table) <= MAX_NODES)
    _require(all(type(text) is str and not text.startswith("§") for text in table))
    _require(len(set(table)) == len(table))
    nodes = size = 0
    referenced = set()

    def charge(value):
        nonlocal nodes, size
        nodes += 1
        _require(nodes <= MAX_NODES)
        if type(value) is str:
            _require(len(value) <= MAX_DECODED_BYTES)
            size += len(value.encode("utf-8")) + 2
        else:
            size += 8
        _require(size <= MAX_DECODED_BYTES)

    def text(value):
        if value.startswith("§§"):
            value = value[1:]
        elif value.startswith("§"):
            ref = value[1:]
            _require(len(ref) <= 12 and _REF.fullmatch(ref) is not None)
            index = int(ref, 36)
            _require(index < len(table))
            referenced.add(index)
            value = table[index]
        charge(value)
        return value

    holder = {}
    stack = [(wire["d"], holder, "root", 0)]
    while stack:
        value, parent, key, depth = stack.pop()
        _require(depth <= MAX_DEPTH)
        value_type = type(value)
        if value_type is str:
            parent[key] = text(value)
        elif value_type is dict:
            charge(value)
            decoded = {}
            parent[key] = decoded
            for raw_key, child in value.items():
                decoded_key = text(raw_key)
                _require(decoded_key not in decoded)
                decoded[decoded_key] = None
                stack.append((child, decoded, decoded_key, depth + 1))
        elif value_type is list:
            charge(value)
            decoded = [None] * len(value)
            parent[key] = decoded
            for index, child in enumerate(value):
                stack.append((child, decoded, index, depth + 1))
        else:
            charge(value)
            parent[key] = value
    _require(len(referenced) == len(table))
    _digest(holder["root"], MAX_DECODED_BYTES)
    return holder["root"]


def _nonnegative(value):
    return type(value) is int and value >= 0


def _shape(value, keys):
    _require(type(value) is dict and set(value) == keys)


def _numeric_tree(value):
    """Dynamic entity/model IDs may be keys, but never additional text values."""
    stack = [value]
    while stack:
        item = stack.pop()
        if type(item) is dict:
            stack.extend(item.values())
        elif type(item) is list:
            stack.extend(item)
        else:
            _require(type(item) in (int, float) and math.isfinite(item))


def _entity_rows(rows):
    _require(type(rows) is list)
    for row in rows:
        _require(type(row) is list and len(row) == 4)
        _require(type(row[0]) is str and type(row[2]) is str)
        _require(type(row[1]) in (int, float) and type(row[3]) is dict)
        _numeric_tree(row[1])
        _numeric_tree(row[3])


def _aggregate_shapes(payload, sources):
    """Allowlist the builder's nested structures; no auxiliary raw mappings."""
    _shape(payload["provenance"], _PROVENANCE)
    provenance = payload["provenance"]
    for key, value in provenance.items():
        if key not in {"first_day", "last_day", "sources"}:
            _numeric_tree(value)
    for value in provenance["sources"].values():
        _shape(value, _SOURCE_COUNTS)
        _date(value["first_day"], optional=True)
        _date(value["last_day"], optional=True)
        _numeric_tree({key: count for key, count in value.items()
                       if key not in {"first_day", "last_day"}})
    _shape(payload["achievement_stats"], _ACHIEVEMENT_STATS)
    achievements = payload["achievement_stats"]
    for key in ("input", "output", "cache_write", "session_totals", "cwd_totals", "source_totals"):
        _numeric_tree(achievements[key])
    _require(type(achievements["model_stats"]) is dict)
    for value in achievements["model_stats"].values():
        _shape(value, _MODEL_STATS)
        _numeric_tree(value)
    for section in (provenance, achievements):
        for key in ("first_day", "last_day"):
            _date(section[key], optional=True)
    for context in payload["session_context"].values():
        _shape(context, _TOP_SESSION_CONTEXT)
        _require(type(context["p"]) is str and type(context["pm"]) is bool)
        _require(type(context["s"]) is list and set(context["s"]) <= set(sources))
        _date(context["d0"])
        _date(context["d1"])
    for values in payload["session_series"].values():
        _require(type(values) is list)
        _numeric_tree(values)
    for key, pretty in payload["pretty"].items():
        _require(key in payload["models"] and type(pretty) is str)
    for colors in payload["colors"].values():
        _require(type(colors) is dict)
        _require(set(colors) == set(payload["models"]))
        _require(all(type(value) is str and re.fullmatch(r"#[0-9a-fA-F]{6}", value)
                     for value in colors.values()))
    for bucket in payload["block"]["buckets"]:
        _shape(bucket, _BUCKET)
        _numeric_tree(bucket)
    _entity_rows(payload["top_cwds"])
    for day, detail in payload["day_details"].items():
        _date(day)
        _shape(detail, _DAY_DETAIL)
        for key in ("hourly", "hourly_models", "cache_read", "cache_read_models"):
            _numeric_tree(detail[key])
        for key in ("cwds", "sessions", "top_cwds", "top_sessions"):
            _entity_rows(detail[key])
        _shape(detail["flow"], _FLOW)
        for rows in detail["flow"].values():
            _require(type(rows) is list)
            for row in rows:
                _require(type(row) is list and len(row) == 4)
                _require(all(type(value) is str for value in row[:3]))
                _numeric_tree(row[3])
    for row in payload["other_models"]:
        _shape(row, {"day", "models"})
        _date(row["day"])
        _require(type(row["models"]) is dict)
        _numeric_tree(row["models"])
    for row in payload["achievement_daily"]:
        _shape(row, {"day", "input", "output", "cache_write", "sources", "max_turns"})
        _date(row["day"])
        _require(type(row["sources"]) is dict and set(row["sources"]) <= set(sources))
        _numeric_tree({key: value for key, value in row.items() if key != "day"})
    for name in ("day", "week", "month"):
        for period in payload[name]:
            _shape(period, _DAY_PERIOD if name == "day" else _PERIOD)
            _require(type(period["period"]) is str and len(period["period"]) <= 16)
            _numeric_tree({
                key: value for key, value in period.items()
                if key not in ("period", "request_models")
            })
            if name == "day":
                tree = period["request_models"]
                _require(type(tree) is dict)
                for backend, names in tree.items():
                    _require(type(backend) is str and type(names) is dict)
                    for alias, total in names.items():
                        _require(type(alias) is str and _nonnegative(total))
        _require(type(payload["reuse"][name]) is list)
        for row in payload["reuse"][name]:
            _require(type(row) is list and len(row) == 2 and type(row[0]) is str)
            _require(type(row[1]) is dict)
            _numeric_tree(row[1])


def _validate_payload(payload, sources, since, until, tz):
    _require(type(payload) is dict and set(payload) == _PAYLOAD_KEYS)
    _require(payload["anonymized"] is False and payload["source"] == list(sources))
    _require(type(payload["source"]) is list)
    _require(type(payload["generated"]) is str and len(payload["generated"]) == 16)
    datetime.strptime(payload["generated"], "%Y-%m-%d %H:%M")
    _date(payload["calendar_day"])
    snapshot = payload["snapshot"]
    _require(type(snapshot) is dict and set(snapshot) == {
        "snapshot_schema", "metric_schema", "timezone", "coverage", "id",
    })
    for key, expected in (("snapshot_schema", dashboard_payload.SNAPSHOT_SCHEMA),
                          ("metric_schema", dashboard_payload.METRIC_SCHEMA)):
        _require(type(snapshot[key]) is int and snapshot[key] == expected)
    _require(snapshot["timezone"] == tz["name"])
    _require(type(snapshot["id"]) is str and _HEX24.fullmatch(snapshot["id"]) is not None)
    coverage = snapshot["coverage"]
    _require(type(coverage) is dict and set(coverage) == {"first_day", "last_day"})
    for value in coverage.values():
        _date(value, optional=True)
    _require((coverage["first_day"] is None) == (coverage["last_day"] is None))
    if coverage["first_day"] is not None:
        _require(coverage["first_day"] <= coverage["last_day"])
    scope = payload["range"]
    _require(type(scope) is dict and set(scope) == {
        "since", "until", "latest_backend", "latest_backend_folded",
    })
    _require(scope["since"] == since and scope["until"] == until)
    _require(scope["latest_backend"] is None or type(scope["latest_backend"]) is str)
    _require(type(scope["latest_backend_folded"]) is bool)
    for key in ("models", "other_models", "hourly", "top_cwds", "achievement_daily",
                "day", "week", "month", "request_models"):
        _require(type(payload[key]) is list)
    for key in ("pretty", "colors", "day_details", "block", "session_series",
                "session_context", "provenance", "achievement_stats", "reuse"):
        _require(type(payload[key]) is dict)
    for key in ("cache_read", "n_cwds", "n_sessions", "max_turns"):
        _require(_nonnegative(payload[key]))
    _require(len(payload["hourly"]) == 24 and all(_nonnegative(v) for v in payload["hourly"]))
    _require(all(type(v) is str for v in payload["models"]))
    _require(len(set(payload["models"])) == len(payload["models"]))
    _require(set(payload["block"]) == {"total", "buckets"})
    _require(_nonnegative(payload["block"]["total"]) and type(payload["block"]["buckets"]) is list)
    _require(set(payload["reuse"]) == {"day", "week", "month"})
    _require(set(payload["colors"]) == {"light", "dark"})
    provenance_sources = payload["provenance"].get("sources")
    achievement_sources = payload["achievement_stats"].get("source_totals")
    _require(type(provenance_sources) is dict and set(provenance_sources) <= set(sources))
    _require(type(achievement_sources) is dict and set(achievement_sources) <= set(sources))
    cost = payload["cost"]
    _require(type(cost) is dict and set(cost) == {
        "schema", "total_incomplete", "components", "models", "rows",
    })
    _require(type(cost["schema"]) is int and cost["schema"] == dashboard_payload.COST_SCHEMA)
    _require(cost["components"] == list(dashboard_payload.COST_COMPONENTS))
    _require(type(cost["total_incomplete"]) is bool)
    _require(type(cost["models"]) is list and type(cost["rows"]) is list)
    for model in cost["models"]:
        _require(type(model) is dict and set(model) == {"source", "model", "identity", "hidden"})
        _require(model["source"] in sources and type(model["model"]) is str
                 and type(model["identity"]) is str and model["hidden"] is False)
    for row in cost["rows"]:
        _require(type(row) is list and len(row) == 6)
        _date(row[0])
        _require(_nonnegative(row[1]) and row[1] < len(cost["models"]))
        _require(type(row[2]) is list and len(row[2]) == len(dashboard_payload.COST_COMPONENTS))
        _require(all(_nonnegative(v) and v <= dashboard_payload.COST_MAX_SAFE for v in row[2]))
        _require(all(_nonnegative(v) and v <= dashboard_payload.COST_MAX_SAFE for v in row[3:5]))
        _require(type(row[5]) is bool)
    _require(type(payload["request_models"]) is list and len(payload["request_models"]) <= 24)
    for entry in payload["request_models"]:
        _shape(entry, _REQUEST_MODEL_ENTRY)
        _require(all(type(entry[key]) is str for key in ("request", "model", "source")))
        _require(entry["source"] in sources and _nonnegative(entry["total"]))
    _aggregate_shapes(payload, sources)
    identity_payload = dict(payload)
    identity_payload.pop("generated")
    identity_payload.pop("calendar_day")
    identity_payload["snapshot"] = {key: value for key, value in snapshot.items() if key != "id"}
    # Same canonical algorithm as dashboard_payload._snapshot_identity, streamed
    # under the decoded budget instead of its unbounded json.dumps allocation.
    _require(_digest(identity_payload, MAX_DECODED_BYTES)[:24] == snapshot["id"])


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _path_signature(path):
    path = os.path.abspath(os.fspath(path))
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return {"path": path, "stat": None, "referent_stat": None}
    try:
        referent = os.stat(path)
    except FileNotFoundError:
        referent = None
    return {"path": path, "stat": list(_signature(info)),
            "referent_stat": list(_signature(referent)) if referent is not None else None}


def _code_digest():
    digest = hashlib.sha256()
    total = 0
    for path in _CODE_FILES:
        digest.update(os.path.basename(path).encode("utf-8") + b"\0")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode))
            while True:
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                _require(total <= _CODE_MAX_BYTES)
                digest.update(chunk)
            _require(_signature(before) == _signature(os.fstat(fd)))
        finally:
            os.close(fd)
        digest.update(b"\0")
    return digest.hexdigest()


class _Directory:
    """Keep the whole path descriptor chain alive and recheck its identities."""
    def __init__(self, path, create):
        self.fds = []
        self.links = []
        try:
            uid = os.getuid()
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            self.fds.append(os.open(os.path.sep, flags))
            parts = [part for part in path.split(os.path.sep) if part]
            _require(bool(parts))
            for index, part in enumerate(parts):
                _require(part not in (".", ".."))
                parent = self.fds[-1]
                try:
                    child = os.open(part, flags, dir_fd=parent)
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=parent)
                    except FileExistsError:
                        pass
                    child = os.open(part, flags, dir_fd=parent)
                self.fds.append(child)
                info = os.fstat(child)
                _require(stat.S_ISDIR(info.st_mode))
                if index == len(parts) - 1:
                    _require(info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o700)
                else:
                    _require(info.st_uid in (0, uid))
                    _require(not (info.st_mode & 0o022)
                             or (info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)))
                self.links.append((parent, part, child))
            self.verify()
        except Exception:
            self.close()
            raise

    @property
    def fd(self):
        return self.fds[-1]

    def verify(self):
        uid = os.getuid()
        for index, (parent, name, fd) in enumerate(self.links):
            linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
            pinned = os.fstat(fd)
            _require(stat.S_ISDIR(linked.st_mode)
                     and (linked.st_dev, linked.st_ino) == (pinned.st_dev, pinned.st_ino))
            if index == len(self.links) - 1:
                _require(linked.st_uid == uid and stat.S_IMODE(linked.st_mode) == 0o700)
            else:
                _require(linked.st_uid in (0, uid))
                _require(not (linked.st_mode & 0o022)
                         or (linked.st_uid == 0 and bool(linked.st_mode & stat.S_ISVTX)))

    def close(self):
        while self.fds:
            _close(self.fds.pop())


def _close(fd):
    try:
        os.close(fd)
    except Exception:
        pass


def _private_file(info):
    _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
             and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1)


def _target(directory, missing_ok=False):
    try:
        fd = os.open("last.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory.fd)
    except FileNotFoundError:
        if missing_ok:
            return None, None
        raise
    try:
        info = os.fstat(fd)
        _private_file(info)
        linked = os.stat("last.json", dir_fd=directory.fd, follow_symlinks=False)
        _require(_signature(info) == _signature(linked))
        return fd, info
    except Exception:
        os.close(fd)
        raise


def _unchanged(directory, before):
    directory.verify()
    try:
        now = os.stat("last.json", dir_fd=directory.fd, follow_symlinks=False)
    except FileNotFoundError:
        _require(before is None)
        return
    _require(before is not None)
    _private_file(now)
    _require(_signature(now) == _signature(before))


class SnapshotStore:
    """Store only the last successful, validated wire; failures stay silent.

    ``directory`` replaces the dedicated directory (not the file name). Passing
    it is intended for temporary tests. Neither construction nor create_store
    opens or stats any path. Only POSIX with an explicit effective timezone is
    enabled; unsafe/unsupported configurations make load/save no-ops.
    """
    def __init__(self, sources, since=None, until=None, directory=None):
        self._valid = False
        try:
            _require(type(sources) in (list, tuple) and bool(sources))
            _require(all(type(source) is str and source in {"claude", "gemini", "codex"}
                         for source in sources))
            _require(len(set(sources)) == len(sources))
            _date(since, optional=True)
            _date(until, optional=True)
            _require(since is None or until is None or since <= until)
            self.sources = tuple(sources)
            self.since, self.until = since, until
            self.directory = os.path.abspath(os.fspath(directory) if directory is not None
                                             else os.path.join(config.CACHE_DIR, "live-snapshot"))
            self._valid = True
        except Exception:
            pass

    def _enabled(self):
        return self._valid and _supported() and _timezone() is not None

    def _fingerprint(self):
        tz = _timezone()
        _require(tz is not None)
        settings = {
            "sources": list(self.sources), "since": self.since, "until": self.until,
            "timezone": tz,
            "roots": {name: os.path.abspath(os.fspath(getattr(config, name))) for name in (
                "CLAUDE_PROJECTS", "GEMINI_TMP", "CODEX_SESSIONS", "CODEX_ARCHIVED_SESSIONS",
            )},
            "router": _path_signature(config.CCR_ROUTER_FILE),
            "title_sidecar": _path_signature(config.SESSION_SUMMARY_FILE),
            "schemas": [STORAGE_SCHEMA, dashboard_wire.WIRE_VERSION,
                        dashboard_payload.SNAPSHOT_SCHEMA, dashboard_payload.METRIC_SCHEMA,
                        dashboard_payload.COST_SCHEMA, readers.CACHE_VERSION],
            "code": _code_digest(),
        }
        return _digest(settings)

    def _validated(self, wire):
        # Detach callers' mutable dictionaries before validation/publication.
        owned = _parsed(_encoded(wire))
        decoded = _decode_wire(owned)
        _validate_payload(decoded, self.sources, self.since, self.until, _timezone())
        return owned

    def load(self):
        directory = None
        fd = None
        try:
            if not self._enabled():
                return None
            fingerprint = self._fingerprint()
            directory = _Directory(self.directory, create=False)
            fd, before = _target(directory)
            _require(before.st_size <= MAX_BYTES)
            raw = bytearray()
            while True:
                chunk = os.read(fd, min(64 * 1024, MAX_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                _require(len(raw) <= MAX_BYTES)
            _require(len(raw) == before.st_size and _signature(before) == _signature(os.fstat(fd)))
            _unchanged(directory, before)
            document = _parsed(raw)
            _require(type(document) is dict and set(document) == {
                "schema", "fingerprint", "wire_sha256", "wire", "checked_at",
            })
            _require(type(document["schema"]) is int and document["schema"] == STORAGE_SCHEMA)
            _require(document["fingerprint"] == fingerprint)
            _checked_at(document["checked_at"])
            _require(type(document["wire_sha256"]) is str
                     and _HEX64.fullmatch(document["wire_sha256"]) is not None)
            wire = self._validated(document["wire"])
            _require(_digest(wire) == document["wire_sha256"])
            _unchanged(directory, before)
            return {"wire": wire, "checked_at": document["checked_at"]}
        except Exception:
            return None
        finally:
            if fd is not None:
                _close(fd)
            if directory is not None:
                directory.close()

    def save(self, wire, checked_at):
        directory = None
        target_fd = temp_fd = None
        temp_name = None
        try:
            if not self._enabled():
                return False
            _checked_at(checked_at)
            wire = self._validated(wire)
            document = {
                "schema": STORAGE_SCHEMA, "fingerprint": self._fingerprint(),
                "wire_sha256": _digest(wire), "wire": wire, "checked_at": checked_at,
            }
            _digest(document)  # Complete size/structure validation precedes mkdir.
            directory = _Directory(self.directory, create=True)
            target_fd, before = _target(directory, missing_ok=True)
            temp_name = ".snapshot-" + secrets.token_hex(16) + ".tmp"
            temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              0o600, dir_fd=directory.fd)
            temp_info = os.fstat(temp_fd)
            _private_file(temp_info)
            for chunk in _json_chunks(document):
                remaining = memoryview(chunk)
                while remaining:
                    written = os.write(temp_fd, remaining)
                    _require(written > 0)
                    remaining = remaining[written:]
            os.fsync(temp_fd)
            _private_file(os.fstat(temp_fd))
            linked = os.stat(temp_name, dir_fd=directory.fd, follow_symlinks=False)
            _require((linked.st_dev, linked.st_ino) == (temp_info.st_dev, temp_info.st_ino))
            _unchanged(directory, before)
            os.replace(temp_name, "last.json", src_dir_fd=directory.fd, dst_dir_fd=directory.fd)
            temp_name = None
            # A directory-fsync failure after replace cannot restore the previous
            # file atomically. The file itself was fsynced before publication.
            try:
                os.fsync(directory.fd)
            except OSError:
                pass
            return True
        except Exception:
            return False
        finally:
            if temp_fd is not None:
                _close(temp_fd)
            if target_fd is not None:
                _close(target_fd)
            if temp_name is not None and directory is not None:
                try:
                    linked = os.stat(temp_name, dir_fd=directory.fd, follow_symlinks=False)
                    if temp_fd is not None and (linked.st_dev, linked.st_ino) == (
                            temp_info.st_dev, temp_info.st_ino):
                        os.unlink(temp_name, dir_fd=directory.fd)
                except Exception:
                    pass
            if directory is not None:
                directory.close()


def create_store(sources, since=None, until=None, anonymize=False, use_cache=True):
    """Explicit opt-in boundary used by create_server, never by the Dashboard."""
    try:
        if anonymize or not use_cache:
            return None
        store = SnapshotStore(sources, since=since, until=until)
        return store if store._enabled() else None
    except Exception:
        return None
