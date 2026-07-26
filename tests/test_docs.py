import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REQUIRED_PAGES = {
    "index.html",
    "getting-started.html",
    "cli.html",
    "dashboard.html",
    "data-and-privacy.html",
    "architecture.html",
    "faq.html",
    "404.html",
}
REQUIRED_ASSETS = {
    "assets/site.css",
    "assets/site.js",
    "favicon.svg",
    "robots.txt",
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
        cls.html_files = sorted(DOCS.glob("*.html"))
        cls.parsers = {}
        for path in cls.html_files:
            parser = DocumentParser()
            parser.feed(path.read_text(encoding="utf-8"))
            cls.parsers[path] = parser

    def test_required_pages_exist(self):
        missing = sorted(name for name in REQUIRED_PAGES if not (DOCS / name).is_file())
        self.assertEqual([], missing, f"缺少页面: {missing}")

    def test_required_assets_exist(self):
        missing = sorted(name for name in REQUIRED_ASSETS if not (DOCS / name).is_file())
        self.assertEqual([], missing, f"缺少静态资源: {missing}")

    def test_pages_have_metadata(self):
        self.assertTrue(self.html_files, "docs 中没有 HTML 页面")
        for path, parser in self.parsers.items():
            with self.subTest(page=path.name):
                self.assertTrue(parser.title, "缺少非空 title")
                self.assertTrue(parser.lang and parser.lang.lower().startswith("zh"), "lang 应为中文")
                self.assertTrue(parser.has_viewport, "缺少 viewport meta")

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
