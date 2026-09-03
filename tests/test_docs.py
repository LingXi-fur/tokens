import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DASHBOARD_ASSETS = ROOT / "src" / "tokens_cli" / "dashboard_assets"
ENGLISH_PAGES = {
    "index.html",
    "getting-started.html",
    "cli.html",
    "dashboard.html",
    "data-and-privacy.html",
    "architecture.html",
    "faq.html",
}
REQUIRED_PAGES = ENGLISH_PAGES | {"404.html"}
CHINESE_PAGES = {f"zh/{name}" for name in ENGLISH_PAGES}
REQUIRED_ASSETS = {
    "assets/site.css",
    "assets/site.js",
    "assets/readme-preview.svg",
    "favicon.svg",
    "robots.txt",
    "sitemap.xml",
}
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
SESSION_RE = re.compile(
    r"\b(?:session|conversation|thread)[_-]?(?:id[_-]?)?"
    r"[0-9a-fA-F]{16,}\b",
    re.IGNORECASE,
)


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title_parts = []
        self.in_title = False
        self.has_viewport = False
        self.links = []
        self.resources = []
        self.ids = []
        self.controls = []
        self.missing_labels = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if attrs.get("aria-controls"):
            self.controls.append((tag, attrs["aria-controls"]))
        if tag in {"button", "input", "nav"} and not attrs.get("aria-label"):
            self.missing_labels.append((tag, attrs.get("class", "")))
        if tag == "html":
            self.lang = attrs.get("lang")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta" and attrs.get("name", "").lower() == "viewport":
            self.has_viewport = bool(attrs.get("content"))
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "link" and attrs.get("href"):
            rel = set(attrs.get("rel", "").lower().split())
            if rel & {"stylesheet", "icon", "preload", "modulepreload"}:
                self.resources.append(attrs["href"])
        elif tag == "script" and attrs.get("src"):
            self.resources.append(attrs["src"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        return "".join(self.title_parts).strip()


class DocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html_files = sorted(DOCS.rglob("*.html"))
        cls.parsers = {}
        for path in cls.html_files:
            parser = DocumentParser()
            parser.feed(path.read_text(encoding="utf-8"))
            cls.parsers[path] = parser

    def test_required_pages_exist(self):
        missing = sorted(
            name for name in REQUIRED_PAGES | CHINESE_PAGES if not (DOCS / name).is_file()
        )
        self.assertEqual([], missing, f"缺少页面: {missing}")

    def test_required_assets_exist(self):
        missing = sorted(name for name in REQUIRED_ASSETS if not (DOCS / name).is_file())
        self.assertEqual([], missing, f"缺少静态资源: {missing}")

    def test_pages_have_metadata(self):
        self.assertTrue(self.html_files, "docs 中没有 HTML 页面")
        for path, parser in self.parsers.items():
            with self.subTest(page=path.name):
                self.assertTrue(parser.title, "缺少非空 title")
                expected = "zh" if path.parent == DOCS / "zh" else "en"
                self.assertTrue(
                    parser.lang and parser.lang.lower().startswith(expected),
                    f"lang should start with {expected}",
                )
                self.assertTrue(parser.has_viewport, "缺少 viewport meta")

    def test_language_switches_are_reciprocal(self):
        for name in sorted(ENGLISH_PAGES):
            english = self.parsers[DOCS / name]
            chinese = self.parsers[DOCS / "zh" / name]
            with self.subTest(page=name):
                self.assertIn(f"zh/{name}", english.links)
                english_href = f"../{name}"
                self.assertGreaterEqual(
                    chinese.links.count(english_href),
                    2,
                    "中文页面的桌面与移动导航都应提供英文入口",
                )

    def test_internal_relative_links_resolve(self):
        missing = []
        for path, parser in self.parsers.items():
            for raw_href in parser.links:
                parts = urlsplit(raw_href)
                if parts.scheme or parts.netloc or raw_href.startswith(("mailto:", "tel:", "javascript:")):
                    continue
                target_path = unquote(parts.path)
                if not target_path:
                    continue
                target = (path.parent / target_path).resolve()
                try:
                    target.relative_to(DOCS.resolve())
                except ValueError:
                    missing.append(f"{path.name}: 链接越出 docs: {raw_href}")
                    continue
                if target_path.endswith("/"):
                    target = target / "index.html"
                if not target.exists():
                    missing.append(f"{path.name}: {raw_href}")
        self.assertEqual([], missing, "无效内部链接:\n" + "\n".join(missing))

    def test_referenced_static_resources_exist(self):
        missing = []
        for path, parser in self.parsers.items():
            for raw_ref in parser.resources:
                parts = urlsplit(raw_ref)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                target = (path.parent / unquote(parts.path)).resolve()
                try:
                    target.relative_to(DOCS.resolve())
                except ValueError:
                    missing.append(f"{path.name}: 资源越出 docs: {raw_ref}")
                    continue
                if not target.is_file():
                    missing.append(f"{path.name}: {raw_ref}")
        self.assertEqual([], missing, "缺失静态资源:\n" + "\n".join(missing))

    def test_docs_do_not_contain_local_identifiers(self):
        violations = []
        for path in sorted(p for p in DOCS.rglob("*") if p.is_file()):
            text = path.read_text(encoding="utf-8", errors="ignore")
            checks = {
                "macOS 用户绝对路径": "/Users/",
                "本机用户名": "a" + "123",
            }
            for label, needle in checks.items():
                if needle in text:
                    violations.append(f"{path.relative_to(DOCS)}: {label}")
            if UUID_RE.search(text):
                violations.append(f"{path.relative_to(DOCS)}: UUID")
            if SESSION_RE.search(text):
                violations.append(f"{path.relative_to(DOCS)}: session 标识")
        self.assertEqual([], violations, "检测到可能的本机/会话泄漏:\n" + "\n".join(violations))

    def test_interactive_controls_are_accessible(self):
        violations = []
        for path, parser in self.parsers.items():
            for tag, css_class in parser.missing_labels:
                violations.append(f"{path.name}: {tag}.{css_class} 缺少 aria-label")
            for tag, control_id in parser.controls:
                if control_id not in parser.ids:
                    violations.append(
                        f"{path.name}: {tag} 的 aria-controls={control_id} 没有对应 id"
                    )
            duplicates = sorted(item for item in set(parser.ids) if parser.ids.count(item) > 1)
            if duplicates:
                violations.append(f"{path.name}: 重复 id {duplicates}")
        self.assertEqual([], violations, "无障碍属性问题:\n" + "\n".join(violations))

    def test_mobile_escape_resets_expanded_state(self):
        script = (DOCS / "assets/site.js").read_text(encoding="utf-8")
        self.assertIn("event.key === 'Escape'", script)
        self.assertIn("mobilePanel.classList.remove('open')", script)
        self.assertIn("mobileButton.setAttribute('aria-expanded', 'false')", script)

    def test_404_is_self_contained_and_base_aware(self):
        page = (DOCS / "404.html").read_text(encoding="utf-8")
        parser = self.parsers[DOCS / "404.html"]
        external_resources = [ref for ref in parser.resources if not ref.startswith("data:")]
        self.assertFalse(external_resources, "404 不应引用 CSS/JS 等外部资源")
        self.assertIn("location.protocol==='file:'", page)
        self.assertIn("location.hostname.endsWith('github.io')", page)
        self.assertIn("repoBase='/'+segments[0]+'/'", page)
        self.assertIn("document.getElementById('home-button').href=base", page)

    def test_pages_workflow_runs_tests_and_watches_them(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn('"tests/test_docs.py"', workflow)
        self.assertIn("python3 -m unittest discover -s tests", workflow)
        self.assertLess(
            workflow.index("python3 -m unittest discover -s tests"),
            workflow.index("actions/upload-pages-artifact"),
            "测试应在上传 Pages artifact 之前运行",
        )

    def test_workflow_tests_can_import_src_package(self):
        workflows = (
            ("ci.yml", "python -m unittest discover -s tests"),
            ("pages.yml", "python3 -m unittest discover -s tests"),
            ("release.yml", "python -m unittest discover -s tests"),
        )
        for filename, command in workflows:
            workflow = (
                ROOT / ".github" / "workflows" / filename
            ).read_text(encoding="utf-8")
            command_index = workflow.index(command)
            environment = workflow[command_index:command_index + 140]
            self.assertIn(
                "PYTHONPATH: src",
                environment,
                f"{filename} tests must import the src-layout package",
            )

    def test_live_dashboard_is_documented_as_loopback_and_offline_is_snapshot(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        english_start = (DOCS / "getting-started.html").read_text(encoding="utf-8")
        chinese_start = (DOCS / "zh" / "getting-started.html").read_text(encoding="utf-8")
        english_dashboard = (DOCS / "dashboard.html").read_text(encoding="utf-8")
        chinese_dashboard = (DOCS / "zh" / "dashboard.html").read_text(encoding="utf-8")

        for text in (readme, chinese_readme, english_start, chinese_start):
            self.assertIn("tokens serve --open", text)
        for text in (readme, chinese_readme, english_dashboard, chinese_dashboard):
            self.assertIn("127.0.0.1", text)
        self.assertIn("generation-time snapshot", english_dashboard)
        self.assertIn("之后新增的日志不会自动进入", chinese_dashboard)

    def test_readme_preview_is_synthetic_and_referenced(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        preview = (DOCS / "assets" / "readme-preview.svg").read_text(encoding="utf-8")
        self.assertIn(
            "https://raw.githubusercontent.com/LingXi-fur/tokens/v0.2.0/docs/assets/readme-preview.svg",
            readme,
        )
        self.assertIn("SYNTHETIC DATA", preview)
        self.assertNotIn("/Users/", preview)
        self.assertNotIn("/home/", preview)
        self.assertNotRegex(preview, UUID_RE)

    def test_pypi_readme_links_are_absolute_or_anchors(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        targets = re.findall(r"!?\[[^]]*\]\(([^)]+)\)", readme)
        relative = [
            target for target in targets
            if not target.startswith(("https://", "http://", "#", "mailto:"))
        ]
        self.assertEqual([], relative, f"PyPI README contains relative links: {relative}")
        image_sources = re.findall(r"<img\s+[^>]*src=[\"']([^\"']+)", readme)
        self.assertTrue(image_sources)
        self.assertTrue(all(source.startswith("https://") for source in image_sources))

    def test_anonymized_dashboard_is_documented_without_overclaiming(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        pages = "\n".join(
            (DOCS / language / name).read_text(encoding="utf-8")
            for language in (Path(), Path("zh"))
            for name in ("cli.html", "dashboard.html", "data-and-privacy.html", "architecture.html")
        )
        combined = readme + "\n" + pages
        self.assertIn("--anonymize", combined)
        self.assertIn("dashboard-anonymized.html", combined)
        for retained in ("精确日期", "Token", "模型", "逐轮"):
            self.assertIn(retained, combined)
        self.assertTrue("假名化" in combined or "不是完全匿名" in combined)
        for overclaim in (
            "完全匿名，可直接公开",
            "保证匿名，可直接公开",
            "无条件公开",
        ):
            self.assertNotIn(overclaim, combined)

    def test_data_trail_semantics_and_privacy_are_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        dashboard = "\n".join(
            (DOCS / path).read_text(encoding="utf-8")
            for path in ("dashboard.html", "zh/dashboard.html")
        )
        privacy = "\n".join(
            (DOCS / path).read_text(encoding="utf-8")
            for path in ("data-and-privacy.html", "zh/data-and-privacy.html")
        )
        combined = "\n".join((readme, dashboard, privacy))
        for marker in (
            "Data Trail", "数据寻迹", "项目与会话", "平行",
            "不按寻迹模型", "最近 200 轮", "Cache Read", "Other",
            "页面内存", "不写入 URL", "localStorage",
        ):
            self.assertIn(marker, combined)
        self.assertIn("<h2 id=\"trail\">", dashboard)
        self.assertIn("<h3 id=\"trail-state\">", privacy)
        self.assertIn("<kbd>I</kbd>", dashboard)
        for overclaim in (
            "项目与会话自动配对", "Cache Read 等于货币节省",
            "数据寻迹会写入 URL", "数据寻迹会保存到 localStorage",
        ):
            self.assertNotIn(overclaim, combined)

    def test_signal_lens_exactness_and_compare_privacy_are_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        dashboard = "\n".join(
            (DOCS / path).read_text(encoding="utf-8")
            for path in ("dashboard.html", "zh/dashboard.html")
        )
        privacy = "\n".join(
            (DOCS / path).read_text(encoding="utf-8")
            for path in ("data-and-privacy.html", "zh/data-and-privacy.html")
        )
        combined = "\n".join((readme, dashboard, privacy))
        for marker in (
            "Signal Lens", "Exactness Key", "按住对比", "页面内存",
            "项目 / 会话 ID", "固定幻影对比", "compare=1",
            "项目 → 模型", "模型 → 会话", "不写入 URL",
        ):
            self.assertIn(marker, combined)
        self.assertIn('<h2 id="interaction-state">', privacy)
        self.assertIn('<h3 id="signal-state">', privacy)
        for retired in (
            "快捷键与隐藏操作", "点击总数本身只切换数字表达格式",
            "点击总数切换", "项目与会话自动配对",
            "Signal Lens 会写入 URL", "精确层会保存到 localStorage",
        ):
            self.assertNotIn(retired, combined)

    def test_data_moments_and_hidden_gestures_are_retired_in_docs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        dashboard = "\n".join(
            (DOCS / path).read_text(encoding="utf-8")
            for path in ("dashboard.html", "zh/dashboard.html")
        )
        combined = readme + "\n" + dashboard
        for marker in (
            "趋势注释轨道", "独立 Data Moments 卡片已移除",
            "不依赖双击、右键", "普通复选",
        ):
            self.assertIn(marker, combined)
        for stale in (
            "Alt 点击全选", "右键反选", "双击 solo",
            "点击锁定 · 会话可逐轮回放",
        ):
            self.assertNotIn(stale, combined)

    def test_cache_read_is_not_documented_as_guaranteed_savings(self):
        files = [
            ROOT / "README.md",
            DOCS / "dashboard.html",
            DOCS / "data-and-privacy.html",
            DOCS / "zh" / "dashboard.html",
            DOCS / "zh" / "data-and-privacy.html",
        ]
        dashboard_asset = (DASHBOARD_ASSETS / "dashboard.js").read_text(encoding="utf-8")
        preview_asset = (DOCS / "assets" / "readme-preview.svg").read_text(encoding="utf-8")
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in files
        ) + "\n" + dashboard_asset + "\n" + preview_asset
        self.assertIn("Cache Read 是缓存 Token", combined)
        for overclaim in (
            "CACHE SAVED", "缓存帮你省了", "钱包松了口气",
            "Cache Read 等于货币节省", "缓存命中 · 省",
        ):
            self.assertNotIn(overclaim, combined)

    def test_docs_do_not_load_third_party_runtime_assets(self):
        remote = []
        for path, parser in self.parsers.items():
            for ref in parser.resources:
                parts = urlsplit(ref)
                if parts.scheme in {"http", "https"} or parts.netloc:
                    remote.append(f"{path.name}: {ref}")
        self.assertEqual([], remote, "检测到远程运行时资源:\n" + "\n".join(remote))


if __name__ == "__main__":
    unittest.main()
