"""交互式自包含 HTML dashboard。

单个 HTML：数据内嵌为 `const DATA = {...}`，vanilla JS 渲染内联 SVG。
零依赖、无 CDN、双击即开、可邮件分发；亮/暗双色自动跟随系统。

设计原则（见 frontend-ui-engineering skill）：
- 统一间距/圆角刻度，单一阴影层级；不堆砌渐变与圆角。
- 微交互有目的：KPI 数字 count-up、总量迷你折线、柱子生长动画、悬停/聚焦反馈。
- 按日/周/月均为堆叠柱状图（带数值标签与背景轨道）。
"""
import json
import os
import tempfile

from . import config, dashboard_payload, dashboard_wire
from .opener import open_path

def build_payload(records, since=None, until=None, sources=None, anonymize=False,
                  generated_at=None, session_titles=None):
    return dashboard_payload.build_payload(
        records,
        since=since,
        until=until,
        sources=sources,
        anonymize=anonymize,
        generated_at=generated_at,
        session_titles=session_titles,
    )


_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_assets")
_ASSET_CACHE = {}


def _read_asset(name):
    if name not in _ASSET_CACHE:
        with open(os.path.join(_ASSET_DIR, name), "r", encoding="utf-8") as fh:
            _ASSET_CACHE[name] = fh.read()
    return _ASSET_CACHE[name]


def _dashboard_template():
    return (_read_asset("template.html")
            .replace("__STYLE__", _read_asset("dashboard.css"))
            .replace("__SCRIPT__", _read_asset("dashboard.js")))

_TEMPLATE = _dashboard_template()
_LANGUAGE_TAGS = {
    "zh": "zh-CN",
    "en": "en",
}



def _embed_json(payload):
    """JSON → 可安全嵌进 <script> 的 JS 字面量（防 </script> 与 U+2028/2029）。"""
    s = json.dumps(payload, ensure_ascii=False)
    return (s.replace("<", "\\u003c")
             .replace(">", "\\u003e")
             .replace(chr(0x2028), "\\u2028")
             .replace(chr(0x2029), "\\u2029"))


def render_dashboard(wire, live=None, demo=False, language="zh", head_meta=""):
    # head_meta 是受信任的静态标记，按原样插入 <head>；本地 CLI 路径保持默认空值，
    # 只有 scripts/build_docs_demo.py 会传入公开 Demo 的常量元数据。
    try:
        language_tag = _LANGUAGE_TAGS[language]
    except KeyError as exc:
        raise ValueError("dashboard language must be 'zh' or 'en'") from exc
    live_config = live or {"enabled": False, "interval": 0}
    return (_TEMPLATE
            .replace("__LANG__", language_tag)
            .replace("__HEAD_META__", head_meta)
            .replace("__DATA__", _embed_json(wire))
            .replace("__LIVE__", _embed_json(live_config))
            .replace("__DEMO__", _embed_json(bool(demo))))


def build_dashboard_html(records, since=None, until=None, sources=None,
                         anonymize=False, generated_at=None,
                         session_titles=None, demo=False, language="zh",
                         head_meta=""):
    payload = build_payload(
        records,
        since=since,
        until=until,
        sources=sources,
        anonymize=anonymize,
        generated_at=generated_at,
        session_titles=session_titles,
    )
    wire = dashboard_wire.encode_payload(payload)
    return render_dashboard(
        wire,
        demo=demo,
        language=language,
        head_meta=head_meta,
    )


def _write_html(html_doc, filename):
    if not filename or filename != os.path.basename(filename):
        raise ValueError("dashboard filename must be a basename")
    os.makedirs(config.OUT_DIR, exist_ok=True)
    path = os.path.join(config.OUT_DIR, filename)
    fd, tmp = tempfile.mkstemp(prefix=f".{filename}.", dir=config.OUT_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(html_doc)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def write_dashboard(records, since=None, until=None, sources=None, anonymize=False,
                    filename=None, generated_at=None, session_titles=None,
                    demo=False, language="zh"):
    html_doc = build_dashboard_html(
        records,
        since=since,
        until=until,
        sources=sources,
        anonymize=anonymize,
        generated_at=generated_at,
        session_titles=session_titles,
        demo=demo,
        language=language,
    )
    filename = filename or (
        "dashboard-anonymized.html" if anonymize else "dashboard.html"
    )
    return _write_html(html_doc, filename)
