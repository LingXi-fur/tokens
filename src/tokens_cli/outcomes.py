"""Read-only git outcomes: what the tokens bought.

Maps each session's working directory to its git repository, matches the
local user's commits in the report range to sessions, and measures what
survived: commit/file/line counts, surviving lines (blamed at HEAD, cached
per repository+SHA+HEAD), and a rework tax over the session spend.

Privacy: only counts, ratios and anonymous labels ever enter the payload or
the on-disk cache.  Commit messages, diffs, file paths and author identities
are read in memory and immediately reduced to numbers.  Every git call is
read-only (GIT_OPTIONAL_LOCKS=0), bounded by a timeout, decoded as UTF-8, and
any git failure degrades to a status instead of failing the report.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import fnmatch
import json
import os
import re
import sqlite3
import subprocess
import tempfile
from shutil import which

from . import config, readers

OUTCOMES_SCHEMA = 2
SURVIVAL_DAYS = 7
SESSION_GRACE_SECONDS = 30 * 60
GIT_TIMEOUT_SECONDS = 15.0
BLAME_TIMEOUT_SECONDS = 10.0
BLAME_CACHE_VERSION = 1
BLAME_CACHE_MAX_ENTRIES = 20000
BLAME_CACHE_MAX_BYTES = 8 * 1024 * 1024
# Cold budget: at most this many commits get blamed per build; the rest are
# reported as blame_skipped and flip status to partial.
NO_CWD_LABEL = "(no working directory)"
BLAME_COMMIT_BUDGET = 400
# subprocess-bound work; a small pool is plenty and stays friendly to laptops.
_BLAME_WORKERS = min(8, (os.cpu_count() or 2))
# Range fallback when the report range is unbounded (keeps git log bounded).

# Default generated/vendored path exclusions; append via
# TOKENS_OUTCOME_EXCLUDE="pattern;pattern" (fnmatch patterns, semicolon separated).
DEFAULT_EXCLUDES = (
    "*.lock",
    "package-lock.json",
    "dist/*",
    "*/dist/*",
    "node_modules/*",
    "*/node_modules/*",
    "*.min.js",
)

# Author matching: git config user.email / user.name, plus extra emails via
# TOKENS_OUTCOME_EMAILS="a@x.com,b@y.org".
_STATUS_REASONS = (
    "git_missing", "repo_unavailable", "blame_timeout", "blame_skipped",
    "bad_session_ts", "blame_cache_reset",
)
_INFO_REASONS = ("no_repo", "binary_commit", "unestimated_cost")

_REPO_CACHE = {}


# ---------- reference prices (single source: dashboard cost_core.js) -------

_RATE_RE = re.compile(
    r"'([^']+)'\s*:\s*\{vendor:'[^']*',"
    r"(?:date:'[^']*',)?rates:\['([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'\]"
)
_ALIAS_BLOCK_RE = re.compile(r"const COST_ALIASES=\{(.*?)\n\};", re.S)
_ALIAS_RE = re.compile(r"'([^']+)'\s*:\s*'([^']+)'")


def _reference_rates():
    """Parse the official reference table out of cost_core.js (read-only).

    The dashboard's cost math stays the single source of truth for prices;
    this only mirrors it so outcomes converts tokens into the same reference
    USD amounts the cost ledger shows.  A missing vendor rate ('') never
    becomes a guessed zero.
    """
    cache = getattr(_reference_rates, "_cache", None)
    if cache is not None:
        return cache
    rates = {}
    try:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "dashboard_assets", "cost_core.js",
        )
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        for match in _RATE_RE.finditer(source):
            model, *values = match.groups()
            rates[model] = [
                None if value == "" else Decimal(value)
                for value in values
            ]
        alias_block = _ALIAS_BLOCK_RE.search(source)
        if alias_block:
            for match in _ALIAS_RE.finditer(alias_block.group(1)):
                alias, target = match.groups()
                if target in rates:
                    rates[alias] = rates[target]
    except OSError:
        pass
    _reference_rates._cache = rates
    return rates


def _extra_emails():
    raw = os.environ.get("TOKENS_OUTCOME_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def _extra_excludes():
    raw = os.environ.get("TOKENS_OUTCOME_EXCLUDE", "")
    return tuple(pattern.strip() for pattern in raw.split(";") if pattern.strip())


def _model_rates(record, rates_table):
    """(parts, rates) for one record, or (None, None) when unpriceable.

    A vendor rate the reference table leaves blank is not a guessed zero: a
    record can still be priced exactly when that component's tokens are zero
    (the same conservative rule the cost ledger applies).
    """
    parts, uncertain = readers.billing_view(record)
    if uncertain:
        return None, None
    model = record.get("model")
    rates = rates_table.get(model) if isinstance(model, str) else None
    if rates is None or len(parts) != len(rates):
        return None, None
    for part, rate in zip(parts, rates):
        if rate is None and part:
            return None, None  # unpriced tokens: never estimate, never free
    return parts, rates


# ---------- git plumbing ----------------------------------------------------

def _git_executable():
    return which("git")


def _git(args, cwd, timeout=GIT_TIMEOUT_SECONDS):
    """Run one read-only git call; returns decoded stdout or raises."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=cwd, env=env, capture_output=True, timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.returncode)
    return completed.stdout.decode("utf-8", errors="replace")


def _worktree_repository(gitdir):
    """Repository root for a worktree gitdir path, or None.

    A worktree's .git file points at ``<repo>/.git/worktrees/<name>``;
    stripping that trailing segment gives the shared git directory, so every
    worktree of one repository resolves to the same root and its commits are
    counted exactly once for all sessions inside that repository.
    """
    normalized = os.path.normpath(gitdir)
    parts = normalized.split(os.sep)
    if len(parts) >= 2 and parts[-2] == "worktrees":
        common = os.sep.join(parts[:-2])
        if os.path.isdir(os.path.join(common, "refs")):
            return os.path.dirname(common)
    return None


_OPENCODE_REPO_CACHE = {}


def _opencode_project_repo(cwd, session):
    """Main repository path for an OpenCode session/worktree, or None.

    OpenCode keeps the project's main path even after a worktree directory is
    removed: ``session_v2.project_id`` and ``worktree.project_id`` both point
    at ``project.worktree``.  This is a read-only lookup, used only when the
    filesystem walk cannot find a repository; a missing DB or schema is a
    miss, not an error.  The database never leaves the machine.
    """
    key = (cwd, session)
    if key in _OPENCODE_REPO_CACHE:
        return _OPENCODE_REPO_CACHE[key]
    repo = None
    path = config.OPENCODE_DB
    if os.path.isfile(path):
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.5)
            try:
                if session:
                    for table in ("session_v2", "session"):
                        try:
                            row = con.execute(
                                "SELECT p.worktree FROM " + table + " s "
                                "JOIN project p ON p.id = s.project_id "
                                "WHERE s.id = ? LIMIT 1", (session,)).fetchone()
                        except sqlite3.Error:
                            continue
                        if row and row[0]:
                            repo = row[0]
                            break
                if not repo and cwd:
                    for sql in (
                        "SELECT p.worktree FROM worktree w "
                        "JOIN project p ON p.id = w.project_id "
                        "WHERE w.directory = ? LIMIT 1",
                        "SELECT p.worktree FROM project_directory d "
                        "JOIN project p ON p.id = d.project_id "
                        "WHERE d.directory = ? LIMIT 1",
                        "SELECT p.worktree FROM worktree w "
                        "JOIN project p ON p.id = w.project_id "
                        "WHERE ? LIKE w.directory || '/' || '%' "
                        "ORDER BY length(w.directory) DESC LIMIT 1",
                    ):
                        try:
                            row = con.execute(sql, (cwd,)).fetchone()
                        except sqlite3.Error:
                            continue
                        if row and row[0]:
                            repo = row[0]
                            break
            finally:
                con.close()
        except (OSError, sqlite3.Error):
            repo = None
    if repo and os.path.isdir(repo):
        found = _repo_root(repo, None, False)
        repo = found
    else:
        repo = None
    _OPENCODE_REPO_CACHE[key] = repo
    return repo


def _repo_root(cwd, session=None, _tool_lookup=True):
    """Repository root above cwd; worktrees merge into their main root.

    A missing cwd or a cwd without any ``.git`` ancestor falls back to the
    read-only OpenCode project mapping (including deleted worktrees).  Other
    tools keep their historical behaviour: no repo means no repo.
    """
    if cwd is None:
        if _tool_lookup:
            return _opencode_project_repo(None, session)
        return None
    cache_key = (cwd, session) if _tool_lookup else cwd
    if cache_key in _REPO_CACHE:
        return _REPO_CACHE[cache_key]
    root = None
    probe = os.path.abspath(cwd)
    while True:
        marker = os.path.join(probe, ".git")
        if os.path.isfile(marker):
            try:
                with open(marker, "r", encoding="utf-8", errors="replace") as handle:
                    line = handle.readline().strip()
                if line.startswith("gitdir:"):
                    gitdir = os.path.abspath(
                        os.path.join(probe, line.split(":", 1)[1].strip()))
                    root = _worktree_repository(gitdir)
                    if root is None and os.path.isdir(os.path.join(gitdir, "refs")):
                        root = probe  # a standalone .git pointer, not a worktree
            except OSError:
                root = None
            break
        if os.path.isdir(marker):
            root = probe
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if root is None and _tool_lookup:
        root = _opencode_project_repo(cwd, session)
    # Normalize through realpath so the main checkout and its worktrees (git
    # stores resolved paths in their .git pointers) land on one identical key.
    if root is not None:
        root = os.path.realpath(root)
    _REPO_CACHE[cache_key] = root
    return root


def _repo_identity(repo):
    """Stable cache key for a repository (its resolved root)."""
    return os.path.realpath(repo)


def _repo_authors(repo, reasons):
    """(email, name) from git config; failures degrade to empty identity."""
    email = name = ""
    try:
        text = _git(["config", "--get-regexp", r"^user\.(email|name)$"],
                    cwd=repo, timeout=3.0)
        for line in text.splitlines():
            key, _, value = line.partition(" ")
            if key.endswith(".email"):
                email = value.strip().lower()
            elif key.endswith(".name"):
                name = value.strip()
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        reasons["repo_unavailable"] += 1
    return email, name


_LOG_FORMAT = "%x1e%H%x1f%at%x1f%ae%x1f%an"


def _collect_commits(repo, since_epoch, until_epoch, email, name, extras, reasons):
    """Commits by the matched authors in [since, until] with numstat rows.

    The newest commit in the output is the repository HEAD; callers reuse it
    instead of paying for an extra rev-parse per repository.
    """
    # Bare epoch numbers are not a git date format; ISO-8601 with the
    # reporting-timezone offset is what git actually parses.
    text = _git(
        ["log", "--no-merges", "--numstat",
         f"--since={_iso(since_epoch)}", f"--until={_iso(until_epoch)}",
         f"--format={_LOG_FORMAT}", "HEAD"],
        cwd=repo,
    )
    excludes = DEFAULT_EXCLUDES + _extra_excludes()
    commits = []
    head = ""
    unit = None

    def _flush():
        nonlocal unit
        if unit is not None and unit["files"]:
            commits.append(unit)
        unit = None

    # splitlines() treats \x1e as a line boundary, which would eat the
    # commit separator; split only on the newline git emits.
    for line in text.split("\n"):
        if not line:
            continue
        if line.startswith("\x1e"):
            _flush()
            fields = line[1:].split("\x1f")
            if len(fields) != 4:
                continue
            sha, stamp, author_email, author_name = fields
            stamp = int(stamp) if stamp.isdigit() else 0
            author_email = (author_email or "").lower()
            if not ((email and author_email == email)
                    or (name and author_name == name)
                    or (author_email and author_email in extras)):
                continue
            unit = {
                "sha": sha, "time": stamp,
                "added": 0, "deleted": 0, "files": 0,
                "binary": False, "paths": [], "surviving": None,
            }
            if not head:
                head = sha  # newest commit first == current HEAD
            continue
        if unit is None:
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added_raw, deleted_raw, path = parts
        if any(fnmatch.fnmatch(path, pattern) for pattern in excludes):
            continue
        unit["files"] += 1
        if added_raw == "-":
            unit["binary"] = True  # binary: counts as a file, lines unknowable
        else:
            try:
                unit["added"] += int(added_raw)
                unit["deleted"] += int(deleted_raw)
            except ValueError:
                continue
        unit["paths"].append(path)
    _flush()
    return commits, head


def _blame_surviving(repo, sha, paths, head, timeout=BLAME_TIMEOUT_SECONDS):
    """Count lines currently at HEAD whose blame origin is the given commit."""
    surviving = 0
    incomplete = False
    for path in paths:
        try:
            text = _git(
                ["blame", "--line-porcelain", head, "--", path],
                cwd=repo, timeout=timeout,
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            incomplete = True
            continue
        for line in text.splitlines():
            if line.startswith("\t"):
                continue
            if line.split(" ", 1)[0].lstrip("^") == sha:
                surviving += 1
    return surviving, incomplete


def _git_state(repo):
    """Cheap fingerprint of a repository's object store (no subprocess).

    Any new commit or fetched branch writes into .git and moves one of these
    directory mtimes, so a cached git log goes stale the moment the
    repository changes.
    """
    marker = os.path.join(repo, ".git")
    try:
        if os.path.isfile(marker):
            with open(marker, "r", encoding="utf-8", errors="replace") as handle:
                line = handle.readline().strip()
            if not line.startswith("gitdir:"):
                return None
            gitdir = os.path.abspath(
                os.path.join(repo, line.split(":", 1)[1].strip()))
        else:
            gitdir = marker
        stamps = [os.stat(gitdir).st_mtime_ns]
        for name in ("objects", "refs"):
            stamps.append(os.stat(os.path.join(gitdir, name)).st_mtime_ns)
        return max(stamps)
    except OSError:
        return None


# ---------- blame disk cache -------------------------------------------------

def _cache_path():
    return os.path.join(config.CACHE_DIR, "outcomes-blame-v1.json")


def _empty_cache():
    return {"v": BLAME_CACHE_VERSION, "entries": {}, "heads": {},
            "sessions": {}, "logs": {}}


def _load_outcomes_cache(reasons):
    try:
        with open(_cache_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return _empty_cache()
    if (not isinstance(data, dict) or data.get("v") != BLAME_CACHE_VERSION
            or not isinstance(data.get("entries"), dict)
            or not isinstance(data.get("heads"), dict)
            or not isinstance(data.get("sessions"), dict)
            or not isinstance(data.get("logs"), dict)):
        reasons["blame_cache_reset"] += 1
        return _empty_cache()
    data.setdefault("sessions", {})
    return data


_SESSION_SUMMARY_FIELDS = ("start", "last", "tokens", "cost",
                          "cost_estimated", "cwds", "models",
                          "model_costs", "source_costs", "source_tokens")


def _freeze_sessions(sessions):
    """Plain-JSON snapshot of the session windows (no derived fields)."""
    frozen = {}
    for sid, window in sessions.items():
        frozen[sid] = {
            "start": window["start"], "last": window["last"],
            "tokens": window["tokens"],
            "cost": str(window["cost"]),
            "cost_estimated": window["cost_estimated"],
            "cwds": dict(window["cwds"]), "models": dict(window["models"]),
            "model_costs": {key: str(value)
                            for key, value in window["model_costs"].items()},
            "source_costs": {key: str(value)
                             for key, value in window["source_costs"].items()},
            "source_tokens": dict(window["source_tokens"]),
        }
    return frozen


def _thaw_sessions(frozen):
    sessions = {}
    for sid, item in frozen.items():
        try:
            sessions[sid] = {
                "start": item["start"], "last": item["last"],
                "tokens": item["tokens"],
                "cost": Decimal(item["cost"]),
                "cost_estimated": item["cost_estimated"],
                "cwds": dict(item["cwds"]), "models": dict(item["models"]),
                "model_costs": {key: Decimal(value)
                                for key, value in item["model_costs"].items()},
                "source_costs": {key: Decimal(value)
                                 for key, value in item["source_costs"].items()},
                "source_tokens": dict(item["source_tokens"]),
            }
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return None  # any malformed entry: recompute from records
    for window in sessions.values():
        window["cwd"] = (max(window["cwds"], key=window["cwds"].get)
                         if window["cwds"] else None)
        window["model"] = (max(window["models"], key=window["models"].get)
                           if window["models"] else None)
    return sessions


def _freeze_commits(commits):
    """Plain-JSON commit rows for the log cache.

    File paths are deliberately left out of the cache (privacy rule); the log
    cache is only used when every measured commit already has a blame entry,
    so a consumer never needs the paths.  Anything that would need a fresh
    blame fails the usability check and reruns the real git log.
    """
    return [[commit["sha"], commit["time"], commit["added"], commit["deleted"],
             commit["files"], commit["binary"]]
            for commit in commits]


def _thaw_commits(rows):
    commits = []
    for row in rows:
        sha, time_, added, deleted, files, binary = row
        commits.append({
            "sha": sha, "time": time_, "added": added, "deleted": deleted,
            "files": files, "binary": binary, "paths": [],
            "surviving": None,
        })
    return commits


def _log_cache_usable(cached, blame_cache, identity, now_epoch):
    """A cached log is usable only when no commit still needs a fresh blame.

    The cache stores no file paths (privacy), so any commit whose survival is
    still unknown would be unable to run blame; in that case the repository
    falls back to a real git log.
    """
    if not isinstance(cached, dict):
        return False
    head = cached.get("head")
    entries = blame_cache.get("entries", {})
    if not isinstance(head, str) or not head:
        return False
    if blame_cache.get("heads", {}).get(identity) != head:
        return False
    rows = cached.get("commits")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            return False
        sha, time_, binary = row[0], row[1], row[5]
        if not isinstance(sha, str) or type(time_) is not int:
            return False
        if binary:
            continue
        # Only commits old enough to be measured need a blame entry.
        if time_ and now_epoch - time_ >= SURVIVAL_DAYS * 86400:
            entry = entries.get(f"{identity}\0{sha}")
            if not isinstance(entry, dict) or type(entry.get("s")) is not int:
                return False
    return True


def _store_outcomes_cache(data):
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        entries = data["entries"]
        while len(payload.encode("utf-8")) > BLAME_CACHE_MAX_BYTES and entries:
            key = min(entries, key=lambda k: entries[k].get("t", 0))
            entries.pop(key)
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        sessions = data.setdefault("sessions", {})
        while len(sessions) > 64:  # a few ranges x model views is plenty
            sessions.pop(next(iter(sessions)))
        if len(entries) > BLAME_CACHE_MAX_ENTRIES:
            ordered = sorted(entries.items(), key=lambda kv: kv[1].get("t", 0))
            for key, _value in ordered[:len(entries) - BLAME_CACHE_MAX_ENTRIES]:
                del entries[key]
        fd, tmp = tempfile.mkstemp(prefix=".outcomes-blame-", dir=config.CACHE_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, _cache_path())
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except (OSError, ValueError):
        pass


def records_fingerprint(since=None, until=None):
    """Fingerprint the (cached) record set for the summary cache, or None.

    The caller must pass the records-cache file signature; a --no-cache read
    has no trustworthy fingerprint and stays None (recompute every time).
    """
    try:
        st = os.stat(config.CACHE_FILE)
    except OSError:
        return None
    return f"{st.st_mtime_ns}|{st.st_size}|{since}|{until}"


# ---------- session windows ---------------------------------------------------

def _epoch(ts, reasons):
    try:
        stamp = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        reasons["bad_session_ts"] += 1
        return None
    if stamp.tzinfo is None:
        reasons["bad_session_ts"] += 1
        return None
    return stamp.timestamp()


def _session_windows(records, rates_table, reasons, model_of=None):
    """sid -> session window with exact per-model and per-source costs.

    Billing components are accumulated per (session, source, model) bucket and
    priced once per bucket, so a large report does not pay a Decimal multiply
    per record.  ``model_costs``/``source_costs`` are exact USD amounts;
    ``models``/``source_tokens`` keep token weights for sessions whose priced
    cost is zero (local/free models), where cost share cannot allocate output.
    Unpriceable records only flip cost_estimated; their tokens stay in totals.
    """
    sessions = {}
    for record in records:
        sid = record.get("session")
        if not sid:
            continue
        stamp = _epoch(record.get("ts"), reasons)
        if stamp is None:
            continue
        total = record.get("total", 0) or 0
        source = record.get("source") or "unknown"
        window = sessions.get(sid)
        if window is None:
            window = sessions[sid] = {
                "start": stamp, "last": stamp, "tokens": 0,
                "cost": Decimal(0), "cost_estimated": True,
                "cwds": {}, "models": {}, "source_tokens": {},
                "model_costs": {}, "source_costs": {}, "priced": {},
            }
        if stamp < window["start"]:
            window["start"] = stamp
        if stamp > window["last"]:
            window["last"] = stamp
        window["tokens"] += total
        cwd = record.get("cwd")
        if cwd:
            window["cwds"][cwd] = window["cwds"].get(cwd, 0) + total
        window["source_tokens"][source] = (
            window["source_tokens"].get(source, 0) + total)
        model = (model_of(record) if model_of is not None
                 else record.get("model"))
        if model:
            window["models"][model] = window["models"].get(model, 0) + total
        parts, rates = _model_rates(record, rates_table)
        if parts is None:
            window["cost_estimated"] = False
            continue
        key = (source, model)
        bucket = window["priced"].get(key)
        if bucket is None:
            bucket = window["priced"][key] = [Decimal(0)] * len(parts)
        for index, (part, rate) in enumerate(zip(parts, rates)):
            if rate is not None and part:
                bucket[index] += Decimal(part) * rate
    for window in sessions.values():
        window["cwd"] = (max(window["cwds"], key=window["cwds"].get)
                         if window["cwds"] else None)
        window["model"] = (max(window["models"], key=window["models"].get)
                           if window["models"] else None)
        model_costs = {}
        source_costs = {}
        for (source, model), bucket in window["priced"].items():
            amount = sum(bucket) / Decimal(1_000_000)
            model_costs[model] = model_costs.get(model, Decimal(0)) + amount
            source_costs[source] = (
                source_costs.get(source, Decimal(0)) + amount)
        window["model_costs"] = model_costs
        window["source_costs"] = source_costs
        window["cost"] = sum(model_costs.values(), Decimal(0))
        del window["priced"]
    return sessions


# ---------- main builder -------------------------------------------------------

def build_outcomes(records, since=None, until=None, anonymize=False,
                   aliases=None, now=None, model_of=None, records_key=None):
    """Compute the outcomes block for the report range.

    since/until are ISO days in the reporting timezone; the git window covers
    those whole days (an unbounded range falls back to the last 30 days).
    ``now`` (aware datetime) drives the 7-day survival rule and defaults to
    the current time, so tests can pin the clock.  ``model_of`` maps a record
    to the identity used for the per-model grouping; the dashboard passes its
    own canonicalization so anonymized reports never leak folded names.
    ``records_key`` identifies the record set (records-cache fingerprint plus
    range): when given and unchanged, a warm summary cache skips the per-record
    pass entirely.  Callers must pass None when records may not be represented
    by the records cache (for example a --no-cache read).
    """
    rates_table = _reference_rates()
    reasons = {key: 0 for key in _STATUS_REASONS + _INFO_REASONS}
    generated = now or datetime.now(config.TZ)
    now_epoch = generated.timestamp()
    # The window is derived from the data itself unless the caller pins a
    # range: two builds over the same records must produce the same block
    # (and the same snapshot identity) even on different days.
    range_days = _resolve_range(records, since, until, generated)
    records = _in_range_records(records, range_days[0], range_days[1])
    since_epoch = _day_start(range_days[0]) if range_days[0] else 0.0
    until_epoch = _day_end(range_days[1]) if range_days[1] else 0.0

    block = {
        "schema": OUTCOMES_SCHEMA,
        "range": {"since": range_days[0], "until": range_days[1]},
        "status": "ok",
        "reasons": {},
        "totals": _empty_totals(),
        "days": [], "projects": [], "models": [], "sources": [],
        "no_commit_sessions": [], "no_repo_sessions": [],
    }
    cache = _load_outcomes_cache(reasons)
    sessions = None
    model_key = "canon" if model_of is not None else "raw"
    if records_key:
        summary = cache["sessions"].get(f"{records_key}\0{model_key}")
        if summary is not None:
            sessions = _thaw_sessions(summary)
    if sessions is None:
        sessions = _session_windows(records, rates_table, reasons, model_of)
        if records_key and sessions:
            cache["sessions"][f"{records_key}\0{model_key}"] = _freeze_sessions(sessions)
            _store_outcomes_cache(cache)
    if not sessions:
        return _decimals_to_floats(block)
    git_ready = _git_executable() is not None
    if not git_ready:
        # Session spend is still reported; only the git side stays empty.
        reasons["git_missing"] = 1

    repos = {}
    for sid, window in sessions.items():
        cwd = window.get("cwd")
        repo = _repo_root(cwd, sid) if git_ready else None
        window["repo"] = repo
        if repo is None:
            if git_ready:
                reasons["no_repo"] += 1
        else:
            repos.setdefault(repo, []).append(sid)

    commits_by_repo = {}
    attributed = {}
    no_session = []
    blame_cache = cache
    if not git_ready:
        blame_cache = _empty_cache()
    blame_entries = blame_cache["entries"]
    blame_heads = blame_cache["heads"]
    extras = _extra_emails()
    heads = {}
    log_cache = blame_cache.setdefault("logs", {})
    log_dirty = False

    for repo in sorted(repos, key=_repo_identity) if git_ready else ():
        identity = _repo_identity(repo)
        state = _git_state(repo)
        log_key = f"{identity}\0{int(since_epoch)}\0{int(until_epoch)}"
        cached = log_cache.get(log_key) if state is not None else None
        if _log_cache_usable(cached, blame_cache, identity, now_epoch):
            try:
                commits = _thaw_commits(cached["commits"])
            except (KeyError, TypeError, ValueError):
                commits = None
            if commits is not None:
                # Warm path: no git subprocess at all for this repository.
                commits_by_repo[repo] = commits
                heads[repo] = cached["head"]
                continue
        email, name = _repo_authors(repo, reasons)
        if not email and not name:
            continue  # No identity configured: nothing can be attributed.
        try:
            commits, head = _collect_commits(
                repo, since_epoch, until_epoch, email, name, extras, reasons)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            reasons["repo_unavailable"] += 1
            continue
        commits_by_repo[repo] = commits
        heads[repo] = head
        if state is not None:
            log_cache[log_key] = {
                "state": state, "head": head,
                "commits": _freeze_commits(commits),
            }
            log_dirty = True

    # Attribute commits to sessions (same repository only); leftovers are
    # treated as manual work outside any session.
    for repo, commits in commits_by_repo.items():
        windows = [(sid, sessions[sid]) for sid in repos[repo]]
        for commit in commits:
            candidates = [
                (sid, window) for sid, window in windows
                if window["start"] <= commit["time"]
                <= window["last"] + SESSION_GRACE_SECONDS
            ]
            if candidates:
                sid, _window = min(
                    candidates, key=lambda item: abs(commit["time"] - item[1]["last"]))
                attributed.setdefault(sid, []).append(commit)
            else:
                no_session.append(commit)

    # Survival via blame, cached per repository+SHA and invalidated when the
    # repository HEAD moves on.  Each file is blamed once per build and the
    # surviving lines are bucketed to every target commit that touched it.
    blamed = 0
    dirty = False
    for repo, commits in (commits_by_repo.items() if git_ready else ()):
        identity = _repo_identity(repo)
        head = heads.get(repo) or "HEAD"
        head_known = bool(heads.get(repo))
        cache_fresh = (head_known and blame_heads.get(identity) == head)
        by_sha = {commit["sha"]: commit for commit in commits}

        # (path) -> [shas] that need surviving counts from that file.
        wanted = {}
        for commit in commits:
            age = now_epoch - commit["time"] if commit["time"] else 0
            if commit["binary"]:
                reasons["binary_commit"] += 1
                continue
            if age < SURVIVAL_DAYS * 86400:
                commit["pending"] = True  # too young: survival stays unknown
                continue
            key = f"{identity}\0{commit['sha']}"
            entry = blame_entries.get(key)
            if entry is not None and cache_fresh and type(entry.get("s")) is int:
                commit["surviving"] = entry["s"]
                continue
            if blamed >= BLAME_COMMIT_BUDGET:
                reasons["blame_skipped"] += 1
                continue
            blamed += 1
            for path in commit["paths"]:
                wanted.setdefault(path, []).append(commit["sha"])

        # Blame runs one subprocess per file; files are independent, so a
        # small thread pool keeps a cold start inside its budget without
        # changing any result.
        def _blame_one(path):
            try:
                return path, _git(
                    ["blame", "--line-porcelain", head, "--", path],
                    cwd=repo, timeout=BLAME_TIMEOUT_SECONDS,
                )
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                return path, None

        with ThreadPoolExecutor(max_workers=_BLAME_WORKERS) as pool:
            for path, text in pool.map(_blame_one, wanted):
                shas = wanted[path]
                counts = dict.fromkeys(shas, 0)
                incomplete = text is None
                if not incomplete:
                    for line in text.split("\n"):
                        if line.startswith("\t"):
                            continue
                        origin = line.split(" ", 1)[0].lstrip("^")
                        if origin in counts:
                            counts[origin] += 1
                for sha in shas:
                    commit = by_sha[sha]
                    if incomplete:
                        # One unreadable file makes the commit's survival
                        # only partially known; keep it unknown, not guessed.
                        reasons["blame_timeout"] += 1
                        commit["blame_incomplete"] = True
                        commit["surviving"] = None
                        continue
                    if commit.get("blame_incomplete"):
                        continue
                    if commit.get("surviving") is None:
                        commit["surviving"] = 0
                    commit["surviving"] += counts[sha]
        if head_known and wanted:
            blame_heads[identity] = head
        # Persist one count per commit: commits with an unreadable file stay
        # unknown instead of persisting a partial number.
        measured = {sha for shas in wanted.values() for sha in shas}
        for sha in measured:
            commit = by_sha[sha]
            if commit.get("blame_incomplete") or commit.get("surviving") is None:
                continue
            blame_entries[f"{identity}\0{sha}"] = {
                "s": commit["surviving"], "t": commit["time"]}
            dirty = True
    if dirty or log_dirty:
        _store_outcomes_cache(blame_cache)

    # ---- aggregate ----
    totals = block["totals"]
    per_day = {}
    per_project = {}
    per_model = {}
    per_source = {}
    settled_cost = Decimal(0)

    def _share_map(costs, tokens):
        """Allocation weights for commits/lines inside one session.

        Exact priced cost is the primary weight.  Only when every priced
        amount is zero (local/free models) do token counts decide; a model
        with neither cost nor tokens gets no share.  This is why the split
        never hands all output to a "primary model": every model that
        actually consumed tokens gets a proportional slice.
        """
        keys = set(costs) | set(tokens)
        total_cost = sum(costs.values(), Decimal(0))
        if total_cost > 0:
            return {key: float(costs.get(key, Decimal(0)) / total_cost)
                    for key in keys}
        total_tokens = sum(tokens.values())
        if total_tokens > 0:
            return {key: tokens.get(key, 0) / total_tokens for key in keys}
        return {}

    def _project_label(window):
        cwd = window.get("cwd")
        repo = window.get("repo")
        # Sessions inside a worktree roll up to their repository; the worktree
        # itself is an implementation detail of one project and never becomes
        # its own project row.  A recovered repo also labels sessions whose
        # working directory was deleted or never recorded.
        if aliases is not None:
            return aliases.get("project", repo or cwd or NO_CWD_LABEL)
        if repo:
            return repo
        return cwd or NO_CWD_LABEL

    for sid, window in sessions.items():
        label = _project_label(window)
        project = per_project.setdefault(label, _empty_project())
        project["repo"] = bool(window.get("repo"))
        project["sessions"] += 1
        project["tokens"] += window["tokens"]
        project["cost"] += window["cost"]
        if not window["cost_estimated"]:
            reasons["unestimated_cost"] += 1

        session_commits = attributed.get(sid, [])
        if not session_commits:
            entry = {
                "session": aliases.get("session", sid) if aliases is not None else sid,
                "project": label,
                "cost": _money(window["cost"]),
                "tokens": window["tokens"],
                "duration_min": max(0, int((window["last"] - window["start"]) // 60)),
            }
            if window.get("repo") is None:
                # Sessions outside any git repository are their own category:
                # they can never have matched commits, so calling them
                # "sessions without commits" would be misleading.
                block["no_repo_sessions"].append(entry)
            else:
                entry["repo"] = True
                block["no_commit_sessions"].append(entry)
        added = deleted = files = surviving = settled_added = pending = 0
        session_settled = False
        for commit in session_commits:
            added += commit["added"]
            deleted += commit["deleted"]
            files += commit["files"]
            day_row = per_day.setdefault(_day_of(commit["time"]), _empty_day())
            day_row["commits"] += 1
            day_row["added"] += commit["added"]
            day_row["deleted"] += commit["deleted"]
            if commit.get("pending"):
                pending += commit["added"]
                day_row["pending_added"] += commit["added"]
            if commit.get("surviving") is not None:
                surviving += commit["surviving"]
                settled_added += commit["added"]
                session_settled = True
                day_row["surviving"] += commit["surviving"]
        tax = Decimal(0)
        if session_settled:
            settled_cost += window["cost"]
            if added:
                reworked = max(0, settled_added - surviving)
                tax = window["cost"] * Decimal(reworked) / Decimal(added)
                totals["rework_tax"] += tax
                project["rework_tax"] += tax
        # Output follows spend inside this session; cost itself stays exact.
        # A model/tool with a zero priced share still gets its row (sessions,
        # tokens, cost) but no invented output.
        for model, share in _share_map(window["model_costs"],
                                       window["models"]).items():
            model_row = per_model.setdefault(model, _empty_model())
            model_cost = window["model_costs"].get(model, Decimal(0))
            model_row["sessions"] += 1
            model_row["tokens"] += window["models"].get(model, 0)
            model_row["cost"] += model_cost
            model_row["commits"] += len(session_commits) * share
            model_row["added"] += added * share
            model_row["surviving"] += surviving * share
            model_row["pending_added"] += pending * share
            model_row["rework_tax"] += tax * Decimal(str(share))
            if session_settled:
                model_row["settled_cost"] += model_cost
        for source, share in _share_map(window["source_costs"],
                                        window["source_tokens"]).items():
            source_row = per_source.setdefault(source, _empty_model())
            source_cost = window["source_costs"].get(source, Decimal(0))
            source_row["sessions"] += 1
            source_row["tokens"] += window["source_tokens"].get(source, 0)
            source_row["cost"] += source_cost
            source_row["commits"] += len(session_commits) * share
            source_row["added"] += added * share
            source_row["surviving"] += surviving * share
            source_row["pending_added"] += pending * share
            source_row["rework_tax"] += tax * Decimal(str(share))
            if session_settled:
                source_row["settled_cost"] += source_cost
        project["commits"] += len(session_commits)
        project["added"] += added
        project["deleted"] += deleted
        project["surviving"] += surviving
        totals["sessions"] += 1
        totals["tokens"] += window["tokens"]
        totals["cost"] += window["cost"]
        totals["commits"] += len(session_commits)
        totals["added"] += added
        totals["deleted"] += deleted
        totals["files"] += files
        totals["surviving"] += surviving

    for commit in no_session:
        day_row = per_day.setdefault(_day_of(commit["time"]), _empty_day())
        day_row["commits"] += 1
        day_row["added"] += commit["added"]
        day_row["deleted"] += commit["deleted"]
        day_row["no_session"] += 1
        if commit.get("pending"):
            day_row["pending_added"] += commit["added"]
        if commit.get("surviving") is not None:
            day_row["surviving"] += commit["surviving"]
            totals["surviving"] += commit["surviving"]
        totals["commits"] += 1
        totals["no_session_commits"] += 1
        totals["added"] += commit["added"]
        totals["deleted"] += commit["deleted"]
        totals["files"] += commit["files"]

    totals["sessions_without_commits"] = len(block["no_commit_sessions"])
    totals["no_repo_sessions"] = len(block["no_repo_sessions"])
    totals["settled_cost"] = _money(settled_cost)
    totals["cost"] = _money(totals["cost"])
    totals["rework_tax"] = _money(totals["rework_tax"])
    totals["retained_per_dollar"] = _ratio(totals["surviving"], totals["cost"])
    totals["retained_per_dollar_settled"] = _ratio(
        totals["surviving"], totals["settled_cost"])
    totals["cost_per_commit"] = _ratio(totals["cost"], totals["commits"])

    block["days"] = [dict(row, day=day) for day, row in sorted(per_day.items())]
    block["projects"] = [
        dict(row, project=label) for label, row in sorted(per_project.items())
    ]
    def _value_sort(item):
        label, row = item
        # Real rankings first (highest retained lines per settled $1); rows
        # marked low_sample are displayed after them and never win a ranking.
        return (row["low_sample"], -row["retained_per_dollar"],
                -float(row["cost"]), label)

    for label, row in list(per_model.items()) + list(per_source.items()):
        row["retained_per_dollar"] = (
            _ratio(row["surviving"], row["settled_cost"])
            if row["settled_cost"] > 0 else 0.0)
        row["low_sample"] = bool(row["sessions"] < 3
                                 or row["settled_cost"] < 1)
        row["commits"] = round(row["commits"], 3)
        row["added"] = round(row["added"], 3)
        row["surviving"] = round(row["surviving"], 3)
        row["pending_added"] = round(row["pending_added"], 3)
    block["models"] = [
        dict(row, model=label) for label, row in sorted(per_model.items(),
                                                        key=_value_sort)
    ]
    block["sources"] = [
        dict(row, source=label) for label, row in sorted(per_source.items(),
                                                         key=_value_sort)
    ]
    for project in block["projects"]:
        project["cost"] = _money(project["cost"])
        project["rework_tax"] = _money(project["rework_tax"])
    for row in block["models"] + block["sources"]:
        row["cost"] = _money(row["cost"])
        row["settled_cost"] = _money(row["settled_cost"])
        row["rework_tax"] = _money(row["rework_tax"])
        row["retained_per_dollar"] = round(row["retained_per_dollar"], 3)
    block["no_commit_sessions"].sort(key=lambda row: (-row["cost"], row["session"]))
    block["no_repo_sessions"].sort(key=lambda row: (-row["cost"], row["session"]))
    _finish(block, reasons, sessions, anonymize, aliases)
    return _decimals_to_floats(block)


def _finish(block, reasons, sessions, anonymize, aliases):
    for key in _STATUS_REASONS:
        if reasons[key]:
            block["reasons"][key] = reasons[key]
    for key in _INFO_REASONS:
        if reasons[key]:
            block["reasons"][key] = reasons[key]
    if reasons["git_missing"]:
        block["status"] = "unavailable"
    elif reasons["repo_unavailable"] or reasons["blame_timeout"] \
            or reasons["blame_skipped"]:
        block["status"] = "partial"
    return block


def _empty_totals():
    return {
        "sessions": 0, "tokens": 0, "cost": Decimal(0),
        "commits": 0, "no_session_commits": 0, "sessions_without_commits": 0,
        "no_repo_sessions": 0,
        "added": 0, "deleted": 0, "files": 0, "surviving": 0,
        "settled_cost": Decimal(0), "rework_tax": Decimal(0),
        "retained_per_dollar": 0.0, "retained_per_dollar_settled": 0.0,
        "cost_per_commit": 0.0,
    }


def _empty_day():
    return {"commits": 0, "added": 0, "deleted": 0, "surviving": 0,
            "no_session": 0, "pending_added": 0}


def _empty_project():
    return {"repo": False, "sessions": 0, "commits": 0, "tokens": 0,
            "cost": Decimal(0), "added": 0, "deleted": 0, "surviving": 0,
            "rework_tax": Decimal(0)}


def _empty_model():
    """One value row (model or tool): exact spend, allocated output."""
    return {"sessions": 0, "commits": 0, "tokens": 0, "cost": Decimal(0),
            "settled_cost": Decimal(0), "added": 0, "surviving": 0,
            "pending_added": 0, "rework_tax": Decimal(0),
            "retained_per_dollar": 0.0, "low_sample": True}


# ---------- terminal report ---------------------------------------------------

_STATUS_TEXT = {
    "zh": {
        "ok": "状态：正常",
        "partial": "状态：部分数据（详见原因）",
        "unavailable": "状态：git 不可用，投入产出未统计",
        "reasons": "原因",
        "title": "投入产出（{since} ~ {until}）",
        "spend": "会话花费",
        "commits": "提交",
        "manual": "无会话提交",
        "no_commit_sessions": "无提交会话",
        "no_repo_sessions": "不在 git 仓库的会话",
        "lines": "新增/删除行",
        "surviving": "留存行",
        "rework_tax": "返工税",
        "per_dollar": "每 $1 留存行",
        "per_dollar_settled": "每 $1 留存行（仅满 7 天）",
        "per_commit": "每提交成本",
        "unpriced": "（部分记录无官方参考价，金额为可估部分）",
        "project": "项目",
        "project_repo": "仓库",
        "project_commits": "提交",
        "project_surviving": "留存",
        "project_cost": "花费",
        "project_tax": "返工税",
        "value_by_model": "按模型",
        "value_by_source": "按工具",
        "value_name": "名称",
        "value_sessions": "会话",
        "value_spend": "花费",
        "value_commits": "提交",
        "value_added": "新增",
        "value_settled": "已定案留存",
        "value_pending": "待定",
        "value_per_dollar": "每 $1 留存行",
        "value_tax": "返工税",
        "value_low_sample": "* 样本少（少于 3 个会话或已定案花费低于 $1），不参与排名",
        "value_alloc": "提交与行数按会话内花费占比分摊；手工提交不计入；同一会话可出现在多行。",
        "value_empty": "该范围没有可统计的模型或工具产出。",
        "yes": "是",
        "no": "否",
        "no_repo": "非 git 目录",
        "no_cwd_label": "(无工作目录)",
        "pending": "另有 {count} 行新增不满 7 天，留存待定",
        "dash": "—",
        "no_settled": "—（所有新增行都不满 7 天，留存待定）",
        "empty": "该范围内没有可统计的会话。",
    },
    "en": {
        "ok": "Status: ok",
        "partial": "Status: partial (see reasons)",
        "unavailable": "Status: git unavailable; outcomes not measured",
        "reasons": "Reasons",
        "title": "Outcomes ({since} ~ {until})",
        "spend": "Session spend",
        "commits": "Commits",
        "manual": "Commits outside any session",
        "no_commit_sessions": "Sessions without commits",
        "no_repo_sessions": "Sessions outside any git repo",
        "lines": "Added/deleted lines",
        "surviving": "Surviving lines",
        "rework_tax": "Rework tax",
        "per_dollar": "Retained lines per $1",
        "per_dollar_settled": "Retained lines per $1 (settled only)",
        "per_commit": "Cost per commit",
        "unpriced": "(some records lack an official reference price; amounts cover the priced part)",
        "project": "Project",
        "project_repo": "Repo",
        "project_commits": "Commits",
        "project_surviving": "Surviving",
        "project_cost": "Spend",
        "project_tax": "Rework",
        "value_by_model": "By model",
        "value_by_source": "By tool",
        "value_name": "Name",
        "value_sessions": "Sessions",
        "value_spend": "Spend",
        "value_commits": "Commits",
        "value_added": "Added",
        "value_settled": "Settled kept",
        "value_pending": "Pending",
        "value_per_dollar": "Kept / $1",
        "value_tax": "Rework",
        "value_low_sample": "* low sample (fewer than 3 sessions or under $1 settled spend); not ranked",
        "value_alloc": "Commits and lines are allocated by spend share inside each session; manual commits are excluded; one session can appear in several rows.",
        "value_empty": "No measurable models or tools in this range.",
        "yes": "yes",
        "no": "no",
        "no_repo": "not a git repo",
        "no_cwd_label": "(no working directory)",
        "pending": "{count} added lines are under 7 days old; survival pending",
        "dash": "—",
        "no_settled": "— (all lines under 7 days old)",
        "empty": "No measurable sessions in this range.",
    },
}


def _fmt_money(value):
    return f"${value:,.2f}"


def _fmt_ratio(value):
    """Terminal-only formatting: one decimal, thousands separators."""
    return f"{value:,.1f}"


def _print_value_table(rows, title, text, key):
    """One model/tool table: one decimal, thousands, — when unsettled."""
    print()
    print(title)
    print(f"{text['value_name']:30} {text['value_sessions']:>6} "
          f"{text['value_spend']:>10} {text['value_commits']:>8} "
          f"{text['value_added']:>10} {text['value_settled']:>10} "
          f"{text['value_pending']:>9} {text['value_per_dollar']:>12} "
          f"{text['value_tax']:>9}")
    if not rows:
        print(text["value_empty"])
        return
    low_sample = False
    for row in rows:
        name = str(row[key])
        mark = "*" if row.get("low_sample") else ""
        low_sample = low_sample or bool(mark)
        per_dollar = (_fmt_ratio(row["retained_per_dollar"])
                      if row.get("settled_cost", 0) > 0 else text["dash"])
        print(f"{name[:29] + mark:30} {row['sessions']:>6} "
              f"{_fmt_money(row['cost']):>10} {_fmt_ratio(row['commits']):>8} "
              f"{_fmt_ratio(row['added']):>10} {_fmt_ratio(row['surviving']):>10} "
              f"{_fmt_ratio(row['pending_added']):>9} {per_dollar:>12} "
              f"{_fmt_money(row['rework_tax']):>9}")
    print(text["value_alloc"])
    if low_sample:
        print(text["value_low_sample"])


def _clip_path(path, width):
    """Middle-clip long paths: keep both ends so the project stays recognizable."""
    if len(path) <= width:
        return path
    half = max(4, (width - 1) // 2)
    return f"{path[:half]}…{path[-(width - half - 1):]}"


def print_report(report, lang="zh"):
    """Print a compact terminal summary; counts and ratios only."""
    text = _STATUS_TEXT.get(lang, _STATUS_TEXT["en"])
    scope = report["range"]
    print(text["title"].format(since=scope["since"], until=scope["until"]))
    totals = report["totals"]
    if not totals["sessions"]:
        print(text["empty"])
        return
    print(text[report["status"]])
    for key, count in sorted(report["reasons"].items()):
        if key in ("binary_commit", "no_repo", "unestimated_cost"):
            continue
        print(f"  {text['reasons']}.{key}: {count}")
    print()
    print(f"{text['spend']}: {_fmt_money(totals['cost'])}"
          f"  ·  {text['commits']}: {totals['commits']}"
          f"  ·  {text['manual']}: {totals['no_session_commits']}"
          f"  ·  {text['no_commit_sessions']}: {totals['sessions_without_commits']}")
    if totals["no_repo_sessions"]:
        print(f"{text['no_repo_sessions']}: {totals['no_repo_sessions']}"
              f"  ·  {text['spend']}: {_fmt_money(sum(row['cost'] for row in report['no_repo_sessions']))}")
    print(f"{text['lines']}: {totals['added']:,} / {totals['deleted']:,}"
          f"  ·  {text['surviving']}: {totals['surviving']:,}")
    pending = sum(row.get("pending_added", 0) for row in report["days"])
    if totals["settled_cost"] > 0:
        per_dollar = _fmt_ratio(totals["retained_per_dollar"])
        per_dollar_settled = _fmt_ratio(totals["retained_per_dollar_settled"])
    elif pending:
        # Survival is unknown, not zero: a bare 0.0 would read as "no output".
        per_dollar = text["no_settled"]
        per_dollar_settled = text["dash"]
    else:
        per_dollar = _fmt_ratio(totals["retained_per_dollar"])
        per_dollar_settled = _fmt_ratio(totals["retained_per_dollar_settled"])
    print(f"{text['rework_tax']}: {_fmt_money(totals['rework_tax'])}"
          f"  ·  {text['per_dollar']}: {per_dollar}"
          f"  ·  {text['per_dollar_settled']}: {per_dollar_settled}"
          f"  ·  {text['per_commit']}: {_fmt_money(totals['cost_per_commit'])}")
    if pending:
        print(text["pending"].format(count=f"{pending:,}"))
    print()
    print(f"{text['project']:38} {text['project_repo']:>4} "
          f"{text['project_commits']:>8} "
          f"{text['project_surviving']:>10} {text['project_cost']:>12} "
          f"{text['project_tax']:>10}")
    for row in report["projects"][:15]:
        name = row["project"]
        if name == NO_CWD_LABEL:
            name = text["no_cwd_label"]
        else:
            name = _clip_path(name, 38)
        print(f"{name:38} {(text['yes'] if row['repo'] else text['no']):>4} "
              f"{row['commits']:>8} {row['surviving']:>10,} "
              f"{_fmt_money(row['cost']):>12} {_fmt_money(row['rework_tax']):>10}")
    _print_value_table(report.get("models", []), text["value_by_model"],
                       text, "model")
    _print_value_table(report.get("sources", []), text["value_by_source"],
                       text, "source")


def _decimals_to_floats(value):
    """Final guard: no Decimal may ever reach the JSON payload."""
    if isinstance(value, Decimal):
        return _money(value)
    if isinstance(value, dict):
        return {key: _decimals_to_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimals_to_floats(item) for item in value]
    return value


def _money(value):
    return float(value.quantize(Decimal("0.01")))


def _ratio(numerator, denominator):
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _day_of(epoch):
    return datetime.fromtimestamp(epoch, tz=config.TZ).date().isoformat()


def _resolve_range(records, since, until, now):
    """Explicit range wins; otherwise the records' own day span bounds git.

    A lone --since extends to today in the reporting timezone, so the title,
    the spend, and the commit window all describe the same span.  Without any
    explicit bound the records' own day span is used: deriving the window from
    the data keeps the block (and the snapshot identity) independent of the
    generation day, and still bounded.
    """
    if since and until:
        return since, until
    if since:
        return since, until or now.date().isoformat()
    if until:
        first = None
        for record in records:
            day = record.get("date") if isinstance(record, dict) else None
            if isinstance(day, str) and len(day) == 10:
                if first is None or day < first:
                    first = day
        return first or now.date().isoformat(), until
    days = []
    for record in records:
        day = record.get("date") if isinstance(record, dict) else None
        if isinstance(day, str) and len(day) == 10:
            days.append(day)
    if days:
        return min(days), max(days)
    return None, None


def _in_range_records(records, since, until):
    """The title, the spend, and the commits must describe one same range."""
    if not since and not until:
        return records
    return [
        record for record in records
        if (not since or record.get("date") >= since)
        and (not until or record.get("date") <= until)
    ]


def _iso(epoch):
    """Git-readable ISO-8601 timestamp in the reporting timezone."""
    stamp = datetime.fromtimestamp(epoch, tz=config.TZ)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S%z")


def _day_start(day):
    stamp = datetime.fromisoformat(day)
    return datetime(stamp.year, stamp.month, stamp.day, tzinfo=config.TZ).timestamp()


def _day_end(day):
    stamp = datetime.fromisoformat(day)
    return datetime(stamp.year, stamp.month, stamp.day, tzinfo=config.TZ).timestamp() + 86400
