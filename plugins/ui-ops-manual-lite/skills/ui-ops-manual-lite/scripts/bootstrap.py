#!/usr/bin/env python3
"""Create the dedicated venv used by the ui-ops-manual-lite skill.

The skill only depends on Python stdlib plus the two packages installed
inside this venv (python-docx, Pillow).  No system tools, no Word or
LibreOffice, no word-render plugin.

Usage:
    python3 <skill>/scripts/bootstrap.py [--venv DIR] [--python PYTHON]

Default venv location: ~/.codex/venvs/ui-ops-manual-lite
Run once per machine.  Idempotent: existing venv is reused and deps re-checked.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_VENV = "~/.codex/venvs/ui-ops-manual-lite"
REQUIREMENTS = ("python-docx", "Pillow")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the venv for the ui-ops-manual-lite skill."
    )
    parser.add_argument("--venv", default=DEFAULT_VENV, help="Directory of the venv.")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Base interpreter used to create the venv (default: current python3).",
    )
    return parser.parse_args()


def run(command: list[str]) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    venv_dir = Path(args.venv).expanduser().resolve()
    if sys.platform == "win32":
        python = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "python.exe"
        pip_args = [str(python), "-m", "pip"]
    else:
        python = venv_dir / "bin" / "python"
        pip_args = [str(python), "-m", "pip"]

    if not python.exists():
        print(f"Creating venv at {venv_dir} ...")
        run([sys.executable if args.python == sys.executable else args.python,
             "-m", "venv", str(venv_dir)])

    run([*pip_args, "install", "--quiet", *REQUIREMENTS])

    probe = subprocess.run(
        [str(python), "-c", "import docx, PIL; print('docx', docx.__version__); print('Pillow', PIL.__version__)"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        print(probe.stderr, file=sys.stderr)
        print(f"bootstrap.py: venv at {venv_dir} is broken", file=sys.stderr)
        return 1

    print(probe.stdout, end="")
    print(f"VENV_PYTHON={python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())