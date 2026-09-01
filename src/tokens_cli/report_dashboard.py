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
import sys

from . import config, dashboard_payload, dashboard_wire
from .opener import open_path

def build_payload(records, since=None, until=None, sources=None, anonymize=False):
    return dashboard_payload.build_payload(
        records,
        since=since,
        until=until,
        sources=sources,
        anonymize=anonymize,
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



def _embed_json(payload):
    """JSON → 可安全嵌进 <script> 的 JS 字面量（防 </script> 与 U+2028/2029）。"""
    s = json.dumps(payload, ensure_ascii=False)
    return (s.replace("<", "\\u003c")
             .replace(">", "\\u003e")
             .replace(chr(0x2028), "\\u2028")
             .replace(chr(0x2029), "\\u2029"))


def write_dashboard(records, since=None, until=None, sources=None, anonymize=False):
    payload = build_payload(
        records,
        since=since,
        until=until,
        sources=sources,
        anonymize=anonymize,
    )
    wire = dashboard_wire.encode_payload(payload)
    html_doc = _TEMPLATE.replace("__DATA__", _embed_json(wire))
    os.makedirs(config.OUT_DIR, exist_ok=True)
    filename = "dashboard-anonymized.html" if anonymize else "dashboard.html"
    path = os.path.join(config.OUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    return path
