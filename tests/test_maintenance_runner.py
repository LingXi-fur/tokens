"""Synthetic tests for the opt-in maintenance verifier, not a recursive suite."""

import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_dashboard.py"
SPEC = importlib.util.spec_from_file_location("dashboard_verifier", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class MaintenanceRunnerTests(unittest.TestCase):
    def test_environment_is_allowlisted_and_directories_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            env = verifier.clean_environment({
                "PATH": "/synthetic/bin", "LANG": "C", "HOME": "/private/home",
                "DASHSCOPE_API_KEY": "synthetic", "OPENAI_API_KEY": "synthetic",
                "HTTP_PROXY": "synthetic", "PYTHONPATH": "/private/code",
                "PYTHONSTARTUP": "/private/startup", "SOME_NEW_SECRET": "synthetic",
            }, base)
            self.assertEqual("/synthetic/bin", env["PATH"])
            for key in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "HTTP_PROXY",
                        "PYTHONPATH", "PYTHONSTARTUP", "SOME_NEW_SECRET"):
                self.assertNotIn(key, env)
            self.assertEqual(str(base / "home"), env["HOME"])
            self.assertEqual(str(base / "cache"), env["XDG_CACHE_HOME"])
            self.assertEqual(str(base / "tmp"), env["TMPDIR"])
            self.assertTrue((base / "work").is_dir())

    def test_guard_blocks_aliases_and_remote_connections_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            private = base / "private"
            private.mkdir()
            alias = base / "alias"
            alias.symlink_to(private, target_is_directory=True)
            guard = verifier.audit_guard([private])
            for path in (private / "file", alias / "file", base / "x" / ".." / "private" / "file"):
                for event in ("open", "os.listdir", "os.scandir"):
                    with self.assertRaises(PermissionError):
                        guard(event, (str(path),))
            guard("open", (str(base / "public"),))
            guard("open", (1,))
            for host in ("127.0.0.1", "::1", "localhost"):
                guard("socket.connect", (None, (host, 8765)))
                guard("socket.getaddrinfo", (host, 8765, 0, 0, 0))
            for host in ("192.0.2.1", "example.invalid"):
                with self.assertRaises(PermissionError):
                    guard("socket.connect", (None, (host, 443)))
                with self.assertRaises(PermissionError):
                    guard("socket.getaddrinfo", (host, 443, 0, 0, 0))

    def run_synthetic(self, source, selectors=("synthetic_checks",), timeout=10):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "fixture"
            root.mkdir()
            (root / "synthetic_checks.py").write_text(source, encoding="utf-8")
            evidence = base / "evidence"
            evidence.mkdir()
            report = verifier.run_scope("logic", evidence, selectors, timeout, root)
            summary = json.loads((evidence / "logic" / "summary.json").read_text())
            self.assertEqual(report, summary)
            if report["status"] != "timeout":
                self.assertGreater(report["log_bytes"], 0)
            self.assertEqual(64, len(report["log_sha256"]))
            return report

    def test_worker_isolated_before_import_and_pass_is_structured(self):
        report = self.run_synthetic('''import os
from pathlib import Path
import unittest
assert Path.home().name == "home"
assert Path.cwd().name == "work"
assert Path(os.environ["XDG_CACHE_HOME"]).name == "cache"
assert "OPENAI_API_KEY" not in os.environ
class Check(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
''')
        self.assertEqual("passed", report["status"])
        self.assertEqual(0, report["exit"])
        self.assertEqual((1, 1, 0, 0, 0), tuple(report[k] for k in (
            "run", "passed", "failures", "errors", "skipped")))
        self.assertEqual([], report["issues"])
        self.assertEqual(0, report["issues_omitted"])

    def test_worker_indexes_outcomes_without_diagnostic_text(self):
        report = self.run_synthetic('''import unittest
class Check(unittest.TestCase):
    def test_failure(self): self.fail("synthetic-private-assertion")
    def test_error(self): raise RuntimeError("synthetic-private-error")
    @unittest.skip("synthetic-private-reason")
    def test_skip(self): pass
    @unittest.expectedFailure
    def test_expected(self): self.fail("synthetic-private-expected")
    @unittest.expectedFailure
    def test_unexpected(self): pass
''')
        self.assertEqual("failed", report["status"])
        self.assertNotEqual(0, report["exit"])
        self.assertEqual([
            {"category": "failure", "test": "synthetic_checks.Check.test_failure"},
            {"category": "error", "test": "synthetic_checks.Check.test_error"},
            {"category": "skip", "test": "synthetic_checks.Check.test_skip"},
            {"category": "expected_failure", "test": "synthetic_checks.Check.test_expected"},
            {"category": "unexpected_success", "test": "synthetic_checks.Check.test_unexpected"},
        ], report["issues"])
        self.assertEqual(0, report["issues_omitted"])
        self.assertNotIn("synthetic-private", json.dumps(report))

    def test_worker_indexes_subtests_and_import_errors_without_details(self):
        report = self.run_synthetic('''import unittest
class Check(unittest.TestCase):
    def test_subtests(self):
        for value in ("synthetic-private-path", "synthetic-private-token"):
            with self.subTest(value=value):
                self.fail("synthetic-private-assertion")
''')
        self.assertEqual("failed", report["status"])
        self.assertEqual(2, report["failures"])
        self.assertEqual([
            {"category": "failure", "test": "synthetic_checks.Check.test_subtests"},
            {"category": "failure", "test": "synthetic_checks.Check.test_subtests"},
        ], report["issues"])
        self.assertNotIn("synthetic-private", json.dumps(report))
        report = self.run_synthetic("raise ImportError('synthetic-private-import')")
        self.assertEqual("failed", report["status"])
        self.assertEqual(1, report["errors"])
        self.assertEqual([{
            "category": "error", "test": "unittest.loader._FailedTest.synthetic_checks",
        }], report["issues"])
        self.assertEqual(0, report["issues_omitted"])
        self.assertNotIn("synthetic-private", json.dumps(report))

    def test_issue_index_uses_parent_ids_for_subtests(self):
        class Check(unittest.TestCase):
            def test_subtests(self):
                for value in ("synthetic-private-path", "synthetic-private-token"):
                    with self.subTest(value=value):
                        self.fail("synthetic-private-assertion")

        Check.__qualname__ = "Check"
        case = Check("test_subtests")
        result = unittest.TestResult()
        case.run(result)
        summary = verifier.summarize_issues(result)
        self.assertEqual([
            {"category": "failure", "test": case.id()},
            {"category": "failure", "test": case.id()},
        ], summary["issues"])
        self.assertEqual(0, summary["issues_omitted"])
        self.assertNotIn("synthetic-private", json.dumps(summary))

    def test_issue_index_replaces_invalid_or_unavailable_ids(self):
        class Named:
            def __init__(self, value):
                self.value = value

            def id(self):
                return self.value

        class Broken:
            def id(self):
                raise RuntimeError("synthetic-private-error")

            def __str__(self):
                raise AssertionError("Must not stringify a test for the summary")

        invalid = ["/synthetic/private", "a..b", "test name", "test.名字",
                   "test." + "x" * 240, "test\nname", "", None, 42]
        result = unittest.TestResult()
        result.skipped = [(Named(value), "synthetic-private-reason") for value in invalid]
        result.skipped.append((Broken(), "synthetic-private-reason"))
        summary = verifier.summarize_issues(result)
        self.assertEqual([{"category": "skip", "test": "unknown"}] * 10,
                         summary["issues"])
        self.assertEqual(0, summary["issues_omitted"])
        self.assertNotIn("synthetic-private", json.dumps(summary))

    def test_issue_index_has_one_global_limit_and_exact_omitted_count(self):
        case = unittest.FunctionTestCase(lambda: None)
        result = unittest.TestResult()
        result.failures = [(case, "synthetic-private-traceback")] * 12
        result.errors = [(case, "synthetic-private-traceback")] * 12
        result.skipped = [(case, "synthetic-private-reason")] * 3
        summary = verifier.summarize_issues(result)
        self.assertEqual(20, len(summary["issues"]))
        self.assertEqual(["failure"] * 12 + ["error"] * 8,
                         [item["category"] for item in summary["issues"]])
        self.assertEqual(7, summary["issues_omitted"])
        self.assertEqual((12, 12, 3), (len(result.failures), len(result.errors), len(result.skipped)))
        self.assertNotIn("synthetic-private", json.dumps(summary))

    def test_failure_skip_empty_import_error_and_expected_failure_are_not_passes(self):
        cases = [
            ("def test_bad(self): self.fail('synthetic failure')", "failures"),
            ("@unittest.skip('synthetic skip')\n def test_skip(self): pass", "skipped"),
            ("@unittest.expectedFailure\n def test_expected(self): self.fail()", "expected_failures"),
        ]
        for method, field in cases:
            with self.subTest(field=field):
                report = self.run_synthetic("import unittest\nclass Check(unittest.TestCase):\n " + method + "\n")
                self.assertNotEqual("passed", report["status"])
                self.assertNotEqual(0, report["exit"])
                self.assertEqual(1, report[field])
        for source, selectors in (("", ("synthetic_checks",)),
                                  ("raise ImportError('synthetic')", ("synthetic_checks",)),
                                  ("", ("missing_synthetic_module",))):
            with self.subTest(source=source, selectors=selectors):
                report = self.run_synthetic(source, selectors)
                self.assertNotEqual("passed", report["status"])
                self.assertNotEqual(0, report["exit"])

    def test_timeout_has_no_success_result(self):
        report = self.run_synthetic("import time\ntime.sleep(30)\n", timeout=0.2)
        self.assertEqual("timeout", report["status"])
        self.assertNotEqual(0, report["exit"])
        self.assertLess(report["elapsed_seconds"], 10)

    def test_browser_argv_uses_only_own_cdp_session(self):
        with tempfile.TemporaryDirectory() as directory:
            class Session:
                def send(self, command):
                    self.command = command
                    return {"arguments": ["chromium", "--password-store=basic",
                            "--use-mock-keychain", "--disable-sync", "--disable-extensions",
                            "--user-data-dir=" + directory + "/new-profile"]}

                def detach(self):
                    self.detached = True

            session = Session()
            class Browser:
                def new_browser_cdp_session(self):
                    return session
            self.assertEqual({"temporary_profile": True, "required_flags": True},
                             verifier.verify_browser_process(Browser(), Path(directory)))
            self.assertEqual("Browser.getBrowserCommandLine", session.command)
            self.assertTrue(session.detached)
            with self.assertRaises(RuntimeError):
                verifier.verify_browser_process(Browser(), Path(directory) / "another")

    def test_default_logic_covers_date_ranges_and_collection_regressions(self):
        required = {
            "tests.test_dashboard_range", "tests.test_claude_json", "tests.test_codex_usage",
            "tests.test_collection_integrity", "tests.test_large_claude_logs",
        }
        self.assertFalse(required - set(verifier.LOGIC_TESTS),
                         "Default logic scope must include date and collection regressions")

    def test_default_scopes_account_for_every_non_world_test_module(self):
        modules = {
            "tests." + path.stem
            for path in SCRIPT.parents[1].joinpath("tests").glob("test_*.py")
            if not path.stem.startswith("test_world_")
        }
        selected = {
            ".".join(selector.split(".")[:2])
            for scope in (verifier.LOGIC_TESTS, verifier.BROWSER_TESTS)
            for selector in scope
        }
        self.assertEqual(modules, selected,
                         "Keep explicit maintenance scopes in sync with non-World test modules")

    def test_scope_partition_and_no_world(self):
        self.assertIn("tests.test_dashboard_page_lifecycle", verifier.LOGIC_TESTS)
        self.assertIn("tests.test_cost_end_to_end.PipelineTests", verifier.LOGIC_TESTS)
        self.assertIn("tests.test_cost_end_to_end.CostEndToEndUiTests", verifier.BROWSER_TESTS)
        for scope in (verifier.LOGIC_TESTS, verifier.BROWSER_TESTS):
            self.assertEqual(len(scope), len(set(scope)))
            self.assertFalse(any("world" in selector.lower() for selector in scope))
        self.assertFalse(set(verifier.LOGIC_TESTS) & set(verifier.BROWSER_TESTS))


if __name__ == "__main__":
    unittest.main()
