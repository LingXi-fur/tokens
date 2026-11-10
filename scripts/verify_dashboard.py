#!/usr/bin/env python3
"""Run synthetic Dashboard maintenance checks with an isolated HOME and cwd.

This application-level Python audit guard is not an OS sandbox. Node and
browser children still have normal OS permissions; use only reviewed synthetic
tests. Logs and results remain in a new system temporary directory.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOGIC_TESTS = (
    "tests.test_cli", "tests.test_config_doctor", "tests.test_readers",
    "tests.test_claude_json", "tests.test_codex_usage", "tests.test_collection_integrity",
    "tests.test_large_claude_logs", "tests.test_dashboard_range", "tests.test_budget_core", "tests.test_period_core",
    "tests.test_dashboard_budget.BudgetIntegrationContracts",
    "tests.test_cost_core", "tests.test_cost_payload",
    "tests.test_cost_end_to_end.PipelineTests", "tests.test_dashboard",
    "tests.test_dashboard_exports", "tests.test_dashboard_model_colors",
    "tests.test_docs", "tests.test_docs_demo", "tests.test_live_dashboard",
    "tests.test_live_progress", "tests.test_reader_progress", "tests.test_live_snapshot",
    "tests.test_reader_memo",
    "tests.test_release_contracts", "tests.test_report_term_sorting",
    "tests.test_maintenance_runner", "tests.test_dashboard_page_lifecycle",
)
BROWSER_TESTS = (
    "tests.test_dashboard_runtime", "tests.test_dashboard_crossbrowser",
    "tests.test_dashboard_live_runtime", "tests.test_dashboard_cost",
    "tests.test_dashboard_cost_actions",
    "tests.test_dashboard_budget.DashboardBudgetTests",
    "tests.test_cost_end_to_end.CostEndToEndUiTests",
)
TIMEOUTS = {"logic": 900, "browser": 1800}


def clean_environment(parent, base):
    """Allow only runtime essentials, not provider credentials or Python hooks."""
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
               "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ")
    env = {key: parent[key] for key in allowed if key in parent}
    home, cache, work, tmp = (base / name for name in ("home", "cache", "work", "tmp"))
    for directory in (home, cache, work, tmp):
        directory.mkdir()
    env.update(HOME=str(home), USERPROFILE=str(home), XDG_CACHE_HOME=str(cache),
               LOCALAPPDATA=str(cache), APPDATA=str(home), TMPDIR=str(tmp),
               TMP=str(tmp), TEMP=str(tmp), PYTHONDONTWRITEBYTECODE="1",
               PYTHONNOUSERSITE="1", PYTHONIOENCODING="utf-8")
    return env


def browser_cache(parent, home):
    """Reuse installed binaries only, never a browser user-data directory."""
    explicit = parent.get("PLAYWRIGHT_BROWSERS_PATH")
    if explicit and explicit != "0":
        return str(Path(explicit).expanduser().resolve())
    if sys.platform == "darwin":
        return str(home / "Library" / "Caches" / "ms-playwright")
    if os.name == "nt":
        return str(Path(parent.get("LOCALAPPDATA", home / "AppData" / "Local")) / "ms-playwright")
    return str(Path(parent.get("XDG_CACHE_HOME", home / ".cache")) / "ms-playwright")


def protected_paths(home, root):
    return [home / ".claude" / "projects", home / ".claude-code-router",
            home / ".codex", home / ".gemini", home / ".config",
            home / "Library" / "Keychains", home / "Library" / "Application Support" / "Google",
            home / "Library" / "Application Support" / "Chromium",
            root / "out", root / ".claude"]


def within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def audit_guard(protected):
    # Resolve before installing the hook: symlink/.. aliases must not bypass it.
    paths = tuple(Path(p).resolve() for p in protected)

    def guard(event, args):
        if event in ("open", "os.listdir", "os.scandir") and args:
            value = args[0]
            if isinstance(value, (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(value)).resolve()
                if any(within(path, parent) for parent in paths):
                    raise PermissionError("Maintenance guard: private data access blocked")
        if event in ("socket.connect", "socket.getaddrinfo"):
            address = args[1] if event == "socket.connect" else args
            if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
                raise PermissionError("Maintenance guard: non-loopback connection blocked")
    return guard


def verify_browser_process(browser, tmp):
    """Query actual argv from this Chromium instance, never other processes."""
    session = browser.new_browser_cdp_session()
    try:
        args = session.send("Browser.getBrowserCommandLine")["arguments"]
    finally:
        session.detach()
    flags = {"--password-store=basic", "--use-mock-keychain", "--disable-sync", "--disable-extensions"}
    profiles = [arg.split("=", 1)[1] for arg in args if arg.startswith("--user-data-dir=")]
    if flags.issubset(args) and len(profiles) == 1 and within(Path(profiles[0]).resolve(), tmp.resolve()):
        return {"temporary_profile": True, "required_flags": True}
    raise RuntimeError("Could not verify our temporary Chromium profile and isolation flags")


class BrowserSafetyStop(BaseException):
    """Abort verification; test fixtures must not catch and retry unsafe launches."""


def isolate_browser(launches, tmp):
    from playwright.sync_api import BrowserType, sync_playwright
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            raise RuntimeError("Installed Chromium binary unavailable; no download attempted")
    original = BrowserType.launch

    def launch(self, **kwargs):
        if self.name != "chromium":
            raise BrowserSafetyStop("Maintenance browser scope supports Chromium only")
        if kwargs.get("ignore_default_args") or kwargs.get("executable_path") or kwargs.get("channel"):
            raise BrowserSafetyStop("Browser launch overrides are not supported")
        kwargs["args"] = list(kwargs.get("args", [])) + [
            "--password-store=basic", "--use-mock-keychain", "--disable-sync", "--disable-extensions",
        ]
        browser = original(self, **kwargs)
        try:
            launches.append(verify_browser_process(browser, tmp))
        except Exception as exc:
            browser.close()
            raise BrowserSafetyStop("Chromium isolation verification failed; no retry") from exc
        return browser

    def no_persistent_profile(self, *args, **kwargs):
        raise BrowserSafetyStop("Persistent browser profiles are forbidden")

    BrowserType.launch = launch
    BrowserType.launch_persistent_context = no_persistent_profile


def summarize_issues(result):
    """Index outcomes without diagnostic text or parameterized subtest names."""
    issues = []
    total = 0
    groups = (
        ("failure", result.failures), ("error", result.errors),
        ("skip", result.skipped), ("expected_failure", result.expectedFailures),
        ("unexpected_success", result.unexpectedSuccesses),
    )
    for category, entries in groups:
        total += len(entries)
        for entry in entries[:max(0, 20 - len(issues))]:
            test = entry if category == "unexpected_success" else entry[0]
            try:
                parent = getattr(test, "test_case", None)
                name = (parent if parent is not None else test).id()
                if (not isinstance(name, str) or len(name) > 240 or
                        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", name)):
                    name = "unknown"
            except Exception:
                name = "unknown"
            issues.append({"category": category, "test": name})
    return {"issues": issues, "issues_omitted": total - len(issues)}


class MaintenanceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successes = 0

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes += 1


def worker(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    report = {"status": "failed", "run": 0, "passed": 0, "failures": 0,
              "errors": 0, "skipped": 0, "expected_failures": 0,
              "unexpected_successes": 0, "launches": [],
              "issues": [], "issues_omitted": 0}
    started = time.monotonic()
    try:
        sys.dont_write_bytecode = True
        sys.addaudithook(audit_guard(config["protected"]))
        root = Path(config["root"])
        sys.path[:0] = [str(root), str(root / "src")]
        if config["scope"] == "browser":
            isolate_browser(report["launches"], Path(os.environ["TMPDIR"]))
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        for name in config["selectors"]:
            suite.addTests(loader.loadTestsFromName(name))
        result = unittest.TextTestRunner(verbosity=2, resultclass=MaintenanceResult).run(suite)
        report.update(run=result.testsRun, passed=result.successes,
                      failures=len(result.failures), errors=len(result.errors),
                      skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                      unexpected_successes=len(result.unexpectedSuccesses))
        report.update(summarize_issues(result))
        ok = (result.wasSuccessful() and result.testsRun > 0 and not result.skipped
              and not result.expectedFailures
              and (config["scope"] != "browser" or bool(report["launches"])))
        report["status"] = "passed" if ok else "failed"
    except (Exception, BrowserSafetyStop) as exc:
        # Details remain in the local log, never in the public status summary.
        import traceback
        traceback.print_exc()
        report.update(status="blocked", error_type=type(exc).__name__)
    report["seconds"] = round(time.monotonic() - started, 3)
    Path(config["result"]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


def stop_owned_process(proc):
    """Terminate only the process group created for this worker."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        proc.kill()
    proc.wait(timeout=10)


def run_scope(scope, evidence, selectors=None, timeout=None, root=ROOT):
    base = evidence / scope
    base.mkdir()
    env = clean_environment(os.environ, base)
    if scope == "browser":
        env["PLAYWRIGHT_BROWSERS_PATH"] = browser_cache(os.environ, Path.home())
    config = {"root": str(root), "scope": scope,
              "protected": [str(p) for p in protected_paths(Path.home(), root)],
              "selectors": list(selectors if selectors is not None else
                                (LOGIC_TESTS if scope == "logic" else BROWSER_TESTS)),
              "result": str(base / "result.json")}
    config_path = base / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    started = time.monotonic()
    with (base / "tests.log").open("wb") as log:
        proc = subprocess.Popen(
            [sys.executable, "-s", str(Path(__file__).resolve()), "--worker", str(config_path)],
            cwd=base / "work", env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=(os.name == "posix"),
        )
        try:
            code = proc.wait(timeout=TIMEOUTS[scope] if timeout is None else timeout)
            if Path(config["result"]).is_file():
                report = json.loads(Path(config["result"]).read_text(encoding="utf-8"))
            else:
                report = {"status": "blocked", "error_type": "MissingWorkerResult"}
            if code != 0 and report.get("status") == "passed":
                report["status"] = "failed"
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            stop_owned_process(proc)
            report = {"status": "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "interrupted"}
            code = 1
    log_path = base / "tests.log"
    digest = hashlib.sha256()
    with log_path.open("rb") as log:
        for chunk in iter(lambda: log.read(65536), b""):
            digest.update(chunk)
    report.update(scope=scope, exit=code, elapsed_seconds=round(time.monotonic() - started, 3),
                  log_bytes=log_path.stat().st_size, log_sha256=digest.hexdigest())
    (base / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scope", nargs="?", choices=("logic", "browser", "all"), default="logic")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return worker(args.worker)
    evidence = Path(tempfile.mkdtemp(prefix="tokens-verification-"))
    scopes = ("logic", "browser") if args.scope == "all" else (args.scope,)
    reports = [run_scope(scope, evidence) for scope in scopes]
    result = {"status": "passed" if all(r["status"] == "passed" for r in reports) else "failed",
              "evidence_dir": str(evidence), "scopes": reports}
    (evidence / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
