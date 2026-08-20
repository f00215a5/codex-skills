#!/usr/bin/env python3
"""Run the plugin's deliberately non-standard ``*.tests.py`` test files."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


TESTS_DIR = Path(__file__).resolve().parent


def _load_test_module(path: Path, ordinal: int):
    module_name = f"mantis_excel_update_test_{ordinal}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load test file: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_suite() -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for ordinal, path in enumerate(sorted(TESTS_DIR.glob("*.tests.py"))):
        suite.addTests(loader.loadTestsFromModule(_load_test_module(path, ordinal)))
    return suite


def main() -> int:
    suite = build_suite()
    if suite.countTestCases() == 0:
        print("No tests discovered for pattern *.tests.py", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
