"""Run Node snippets from a short temporary file instead of ``node -e``.

Windows command lines are limited (WinError 206), so large test harnesses must
not be passed as a single ``-e`` argument.
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path


def run_node(script, *args, **kwargs):
    suffix = ".mjs" if re.search(r"^\s*import\s", script, re.MULTILINE) else ".cjs"
    if args:
        # Keep the historical ``node -e`` argv[1] contract used by test scripts.
        script = "process.argv[1]=process.argv[2];\n" + script
    fd, path = tempfile.mkstemp(prefix="tokens-node-", suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(script)
        return subprocess.run(["node", path, *map(str, args)], **kwargs)
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass
