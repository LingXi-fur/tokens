"""Runtime paths and user-facing defaults."""
import os
import sys
import time
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HOME = os.path.expanduser("~")

CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
GEMINI_TMP = os.path.join(HOME, ".gemini", "tmp")
CODEX_SESSIONS = os.path.join(HOME, ".codex", "sessions")


def _cache_root():
    if sys.platform == "win32":
        return os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
    if sys.platform == "darwin":
        return os.path.join(HOME, "Library", "Caches")
    return os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache"))


class _SystemLocalTimezone(tzinfo):
    def _timestamp(self, dt):
        return time.mktime((
            dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second,
            dt.weekday(), 0, -1,
        ))

    def utcoffset(self, dt):
        if dt is None:
            return None
        timestamp = self._timestamp(dt)
        local = datetime.fromtimestamp(timestamp)
        utc = datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
        return local - utc

    def dst(self, dt):
        if dt is None:
            return None
        timestamp = self._timestamp(dt)
        if time.localtime(timestamp).tm_isdst <= 0:
            return timedelta(0)
        return timedelta(seconds=time.timezone - time.altzone)

    def tzname(self, dt):
        if dt is None:
            return None
        timestamp = self._timestamp(dt)
        is_dst = time.localtime(timestamp).tm_isdst > 0
        return time.tzname[1 if is_dst else 0]

    def fromutc(self, dt):
        if dt.tzinfo is not self:
            raise ValueError("fromutc: dt.tzinfo is not self")
        timestamp = datetime(*dt.timetuple()[:6], tzinfo=timezone.utc).timestamp()
        return datetime.fromtimestamp(timestamp).replace(tzinfo=self)

    def __str__(self):
        return "system local time"


_SYSTEM_LOCAL_TIMEZONE = _SystemLocalTimezone()


def _system_zone_name():
    for path in ("/etc/localtime", "/var/db/timezone/zoneinfo/default"):
        target = os.path.realpath(path)
        marker = "/zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
    try:
        with open("/etc/timezone", "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def _system_timezone():
    configured = os.environ.get("TOKENS_TIMEZONE") or os.environ.get("TZ") or _system_zone_name()
    if configured:
        try:
            return ZoneInfo(configured)
        except ZoneInfoNotFoundError:
            pass
    return _SYSTEM_LOCAL_TIMEZONE


CACHE_DIR = os.path.join(_cache_root(), "ai-cli-tokens")
CACHE_FILE = os.path.join(CACHE_DIR, "records-v3.json")
OUT_DIR = os.path.abspath(os.path.join(os.getcwd(), "out"))
SESSION_SUMMARY_FILE = os.path.join(OUT_DIR, "session_summaries.json")
TZ = _system_timezone()
DEFAULT_SOURCES = ["claude"]

MODEL_ALIASES = {
    "glm-5.2": "GLM-5.2",
    "glm-5.1": "GLM-5.1",
    "glm-4.7": "GLM-4.7",
    "deepseek-v4-pro": "DeepSeek-V4-Pro",
    "deepseek-v4-flash": "DeepSeek-V4-Flash",
}


def set_output_dir(path):
    global OUT_DIR, SESSION_SUMMARY_FILE
    OUT_DIR = os.path.abspath(os.path.expanduser(path))
    SESSION_SUMMARY_FILE = os.path.join(OUT_DIR, "session_summaries.json")


def set_timezone(name):
    global TZ
    try:
        TZ = ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def timezone_name():
    return getattr(TZ, "key", str(TZ))


def pretty_model(name):
    if not name:
        return "(unknown)"
    return MODEL_ALIASES.get(name, name)
