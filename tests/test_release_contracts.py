import os
import re
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"
PREVIEW = ROOT / "docs" / "assets" / "readme-preview.png"


def _toml_section(text, name):
    match = re.search(
        rf"(?ms)^\[{re.escape(name)}\]\s*$\n(.*?)(?=^\[|\Z)",
        text,
    )
    if not match:
        raise AssertionError(f"missing [{name}] section")
    return match.group(1)


def _toml_string(section, key):
    match = re.search(
        rf'(?m)^{re.escape(key)}\s*=\s*"([^"]+)"\s*$',
        section,
    )
    if not match:
        raise AssertionError(f"missing string key {key}")
    return match.group(1)


class ReleaseContractsTests(unittest.TestCase):
    def test_source_launcher_exists_and_is_executable(self):
        launcher = ROOT / "run"
        self.assertTrue(launcher.is_file())
        if os.name != "nt":
            mode = launcher.stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, "run must have its user executable bit set")
            self.assertTrue(os.access(launcher, os.X_OK), "run must be executable")

    def test_source_module_version_and_doctor_use_temporary_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            home = sandbox / "home"
            work = sandbox / "work"
            home.mkdir()
            work.mkdir()
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env["PYTHONPATH"] = str(SRC)
            env.pop("XDG_CACHE_HOME", None)
            env.pop("LOCALAPPDATA", None)

            version = subprocess.run(
                [sys.executable, "-m", "tokens_cli", "--version"],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, version.returncode, version.stderr)
            self.assertRegex(version.stdout.strip(), r"^tokens \d+\.\d+\.\d+$")

            doctor = subprocess.run(
                [sys.executable, "-m", "tokens_cli", "doctor"],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            output = doctor.stdout + doctor.stderr
            self.assertEqual(0, doctor.returncode, output)
            self.assertIn("tokens doctor", doctor.stdout)
            self.assertIn(str(home), output)
            self.assertIn(str(work / "out"), output)
            self.assertIn(str(home / ".claude" / "projects"), output)
            self.assertIn(str(home / ".gemini" / "tmp"), output)
            self.assertIn(str(home / ".codex" / "sessions"), output)
            real_home = str(Path.home())
            if real_home != str(home):
                self.assertNotIn(real_home, output)

    def test_pyproject_exposes_source_layout_console_script_and_assets(self):
        text = PYPROJECT.read_text(encoding="utf-8")

        scripts = _toml_section(text, "project.scripts")
        self.assertEqual("tokens_cli.cli:main", _toml_string(scripts, "tokens"))

        setuptools = _toml_section(text, "tool.setuptools")
        package_dir = re.search(
            r'(?m)^package-dir\s*=\s*\{\s*""\s*=\s*"([^"]+)"\s*\}\s*$',
            setuptools,
        )
        self.assertIsNotNone(package_dir, "missing setuptools package-dir mapping")
        self.assertEqual("src", package_dir.group(1))

        finder = _toml_section(text, "tool.setuptools.packages.find")
        where = re.search(r"(?ms)^where\s*=\s*\[(.*?)\]", finder)
        self.assertIsNotNone(where, "missing package finder path")
        self.assertEqual(["src"], re.findall(r'"([^"]+)"', where.group(1)))

        package_data = _toml_section(text, "tool.setuptools.package-data")
        tokens_assets = re.search(r"(?ms)^tokens_cli\s*=\s*\[(.*?)\]", package_data)
        self.assertIsNotNone(tokens_assets, "missing tokens_cli package data")
        self.assertEqual(
            {
                "dashboard_assets/*.html",
                "dashboard_assets/*.css",
                "dashboard_assets/*.js",
            },
            set(re.findall(r'"([^"]+)"', tokens_assets.group(1))),
        )

    def test_readme_preview_is_tracked_synthetic_png(self):
        readme = README.read_text(encoding="utf-8")
        self.assertIn("docs/assets/readme-preview.png", readme)
        self.assertRegex(readme, r"(?i)synthetic[^\n]*preview|preview[^\n]*synthetic")

        data = PREVIEW.read_bytes()
        self.assertGreaterEqual(len(data), 33)
        self.assertEqual(b"\x89PNG\r\n\x1a\n", data[:8])
        self.assertEqual(b"IHDR", data[12:16])
        width, height = struct.unpack(">II", data[16:24])
        self.assertGreaterEqual(width, 640)
        self.assertGreaterEqual(height, 360)
        self.assertLessEqual(width, 5000)
        self.assertLessEqual(height, 5000)

        tracked = subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                "docs/assets/readme-preview.png",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            0,
            tracked.returncode,
            "README preview must be tracked by Git, not only present locally",
        )


if __name__ == "__main__":
    unittest.main()
