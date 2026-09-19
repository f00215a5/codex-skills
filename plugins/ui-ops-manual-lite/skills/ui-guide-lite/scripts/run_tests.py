#!/usr/bin/env python3
"""Run every dotted ``*.tests.py`` file in the lite skill test directory.

Python's normal unittest discovery pattern and module-name validation can
silently skip filenames such as ``build_docx.tests.py``.  This runner invokes
each file directly, fails when a child exits non-zero, and fails when a child
does not report at least one executed test.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


RAN_RE = re.compile(r"Ran\s+(\d+)\s+tests?")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tests",
        help="Directory containing dotted *.tests.py files.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress child test output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tests_dir = args.tests_dir.expanduser().resolve()
    files = sorted(tests_dir.glob("*.tests.py"))
    if not files:
        print(f"run_tests.py: no *.tests.py files found under {tests_dir}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    # Child tests invoke subprocesses and decode their output as UTF-8.  Set
    # this at the runner boundary so Windows' active code page cannot produce
    # a false failure or a decoding exception in the test harness.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    failures = 0
    total = 0
    for path in files:
        result = subprocess.run(
            [sys.executable, str(path), "-v"],
            cwd=str(tests_dir.parent),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        match = RAN_RE.search(result.stdout + result.stderr)
        count = int(match.group(1)) if match else 0
        total += count
        if not args.quiet:
            print(f"--- {path.name} ({count} tests) ---")
            output = (result.stdout + result.stderr).strip()
            if output:
                print(output)
        if result.returncode != 0 or count == 0:
            failures += 1
            if args.quiet:
                print(f"FAIL {path.name}: exit={result.returncode}, tests={count}", file=sys.stderr)

    print(f"run_tests.py: {len(files)} files, {total} tests, {failures} file failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
