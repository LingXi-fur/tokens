"""Single registry for every local usage source.

Adding a source means adding one entry here plus synthetic reader tests. Reader
implementations stay in ``readers.py``; this module only records discovery
metadata and lazy references, so importing it never opens a log file.
"""
from dataclasses import dataclass
import os

from . import config


@dataclass(frozen=True)
class Source:
    name: str
    label: str
    root: object
    root_kind: str
    files_name: str
    parse_name: str
    billing_keys_name: str
    billing_name: str
    docs_path: str
    quota_supported: bool = True
    size_exempt: bool = True
    strict_discovery: bool = True
    sqlite_wal: bool = False

    @property
    def files(self):
        from . import readers
        return getattr(readers, self.files_name)

    @property
    def parse(self):
        from . import readers
        return getattr(readers, self.parse_name)

    @property
    def billing(self):
        from . import readers
        return (getattr(readers, self.billing_keys_name),
                getattr(readers, self.billing_name))


SOURCES = (
    Source(
        name="claude", label="Claude Code",
        root=lambda: config.CLAUDE_PROJECTS, root_kind="dir",
        files_name="claude_files", parse_name="claude_parse",
        billing_keys_name="_CLAUDE_BILLING_KEYS", billing_name="_claude_billing",
        docs_path="~/.claude",
    ),
    Source(
        name="gemini", label="Gemini CLI",
        root=lambda: config.GEMINI_TMP, root_kind="dir",
        files_name="gemini_files", parse_name="gemini_parse",
        billing_keys_name="_GEMINI_BILLING_KEYS", billing_name="_gemini_billing",
        docs_path="~/.gemini", quota_supported=False, size_exempt=False,
        strict_discovery=False,
    ),
    Source(
        name="codex", label="Codex",
        root=lambda: config.CODEX_SESSIONS, root_kind="dir",
        files_name="codex_files", parse_name="codex_parse",
        billing_keys_name="_CODEX_BILLING_KEYS", billing_name="_codex_billing",
        docs_path="~/.codex",
    ),
    Source(
        name="opencode", label="OpenCode",
        root=lambda: config.OPENCODE_DB, root_kind="file",
        files_name="opencode_files", parse_name="opencode_parse",
        billing_keys_name="_OPENCODE_BILLING_KEYS", billing_name="_opencode_billing",
        docs_path="~/.local/share/opencode", sqlite_wal=True,
    ),
    Source(
        name="antigravity", label="Antigravity",
        root=lambda: _antigravity_root(), root_kind="dir",
        files_name="antigravity_files", parse_name="antigravity_parse",
        billing_keys_name="_ANTIGRAVITY_BILLING_KEYS", billing_name="_antigravity_billing",
        docs_path="~/.gemini/antigravity", quota_supported=False,
        size_exempt=True, strict_discovery=False, sqlite_wal=True,
    ),
)


def _antigravity_root():
    from . import antigravity_usage
    return antigravity_usage._get_root()
BY_NAME = {source.name: source for source in SOURCES}
NAMES = tuple(source.name for source in SOURCES)


def detect():
    """Return existing/readable sources and explicit skip reasons.

    Only path predicates and permission checks are used; no file is opened.
    """
    detected, skipped = [], []
    for source in SOURCES:
        root = source.root()
        exists = (os.path.isfile(root) if source.root_kind == "file"
                  else os.path.isdir(root))
        if not exists:
            skipped.append({
                "name": source.name,
                "label": source.label,
                "reason": "not_found",
                "docs_path": source.docs_path,
            })
        elif not os.access(root, os.R_OK):
            skipped.append({
                "name": source.name,
                "label": source.label,
                "reason": "unreadable",
                "docs_path": source.docs_path,
            })
        else:
            detected.append(source)
    return detected, skipped


def resolve(selected=None):
    """Resolve ``auto`` and explicit names into a deduplicated ordered list."""
    requested = list(selected) if selected else ["auto"]
    auto = "auto" in requested
    explicit = [name for name in requested if name != "auto"]
    detected, skipped = detect() if auto else ([], [])
    enabled = [source.name for source in SOURCES
               if source.name in explicit or (auto and source in detected)]
    for name in explicit:
        if name not in enabled:
            enabled.append(name)
    return enabled, detected, skipped, auto


def format_detection(detected, skipped, lang="en"):
    if lang == "zh":
        labels = "、".join(source.label for source in detected) or "无"
        text = f"自动发现来源：{labels}"
        if skipped:
            reasons = "、".join(
                f"{row['label']}，" +
                ("未找到 " if row["reason"] == "not_found" else "无法读取 ") +
                row["docs_path"]
                for row in skipped
            )
            text += f"（跳过：{reasons}）"
        return text
    labels = ", ".join(source.label for source in detected) or "none"
    text = f"Auto-detected sources: {labels}"
    if skipped:
        reasons = ", ".join(
            f"{row['label']}, " + row["docs_path"] +
            (" not found" if row["reason"] == "not_found" else " unreadable")
            for row in skipped
        )
        text += f" (skipped: {reasons})"
    return text
