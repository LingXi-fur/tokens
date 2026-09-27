"""输出语言解析：终端与静态 HTML 报告共用。

优先级：--lang 显式参数 > TOKENS_LANG 环境变量 > 系统 locale（zh* → zh，其余 → en）。
Dashboard 页面语言不受此模块影响（页面内自行切换）。
"""
import os

SUPPORTED = ("en", "zh")

_LOCALE_VARS = ("LC_ALL", "LC_MESSAGES", "LANG")


def _normalize(value):
    if value is None:
        return None
    tag = value.strip().lower()
    if not tag:
        return None
    if tag.startswith("zh"):
        return "zh"
    if tag.startswith("en"):
        return "en"
    raise ValueError(f"unsupported language: {value}")


def resolve_lang(value=None):
    """返回 'en' 或 'zh'；显式给出不支持的值时抛 ValueError。"""
    for candidate in (value, os.environ.get("TOKENS_LANG")):
        resolved = _normalize(candidate)
        if resolved:
            return resolved
    for variable in _LOCALE_VARS:
        tag = os.environ.get(variable, "")
        if tag:
            return "zh" if tag.lower().startswith("zh") else "en"
    return "en"
