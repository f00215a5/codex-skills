"""Test package for the ui-ops-manual-lite skill.

The repo names tests `*.tests.py` (a dotted filename, so `unittest discover`
would skip them as non-identifiers).  `load_tests` loads each sibling
`*.tests.py` explicitly so both `python -m unittest discover -s tests` and
direct execution work.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


def load_tests(loader, standard_tests, pattern):
    package_dir = pathlib.Path(__file__).parent
    for module_path in sorted(package_dir.glob("*.tests.py")):
        module_name = f"{__name__}.{module_path.stem.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        standard_tests.addTests(loader.loadTestsFromModule(module))
    return standard_tests