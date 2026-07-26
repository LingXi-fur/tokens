"""路径与常量。纯 stdlib。"""
import os
from zoneinfo import ZoneInfo

HOME = os.path.expanduser("~")

# 三个 CLI 的本地日志根
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")     # ~/.claude/projects/**/*.jsonl
GEMINI_TMP = os.path.join(HOME, ".gemini", "tmp")               # ~/.gemini/tmp/<hash>/chats/session-*.json
CODEX_SESSIONS = os.path.join(HOME, ".codex", "sessions")        # ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
CACHE_FILE = os.path.join(OUT_DIR, "cache.json")
# 会话自然语言摘要 sidecar（sessionId → 摘要文本）。无则回退到首条提问提取。
SESSION_SUMMARY_FILE = os.path.join(OUT_DIR, "session_summaries.json")

# 本地时区：避免 UTC 跨日把今天的算到昨天
TZ = ZoneInfo("Asia/Shanghai")

# 默认只统计 claude（经 claude-code-router 走 GLM-5.2 / DeepSeek）。
# gemini / codex 仍可经 --source 显式开启。
DEFAULT_SOURCES = ["claude"]

# 模型显示名（仅美化，可选）
MODEL_ALIASES = {
    "glm-5.2": "GLM-5.2",
    "glm-5.1": "GLM-5.1",
    "glm-4.7": "GLM-4.7",
    "deepseek-v4-pro": "DeepSeek-V4-Pro",
    "deepseek-v4-flash": "DeepSeek-V4-Flash",
}


def pretty_model(name):
    """模型名美化，未知原样返回。"""
    if not name:
        return "(unknown)"
    return MODEL_ALIASES.get(name, name)
