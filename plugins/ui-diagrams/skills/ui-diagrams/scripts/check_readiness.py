"""Report whether draw.io and its upstream Codex skill are ready to use."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple


SKILL_RELATIVE_PATHS = (
    Path(".codex/skills/drawio-skill/skills/drawio-skill/SKILL.md"),
    Path(".agents/skills/drawio-skill/skills/drawio-skill/SKILL.md"),
)


class ProbeResult(NamedTuple):
    returncode: int | None
    stdout: str
    stderr: str


def find_drawio_skill(home: Path) -> Path | None:
    """Return the first installed drawio-skill definition under *home*."""
    for relative_path in SKILL_RELATIVE_PATHS:
        candidate = home / relative_path
        if candidate.is_file():
            return candidate
    return None


def resolve_drawio_command(
    platform: str,
    which: Callable[[str], str | None],
    exists: Callable[[Path], bool],
) -> list[str] | None:
    """Resolve a draw.io Desktop command without launching it."""
    for name in ("drawio", "draw.io"):
        command = which(name)
        if command is not None:
            return [command]

    if platform == "win32":
        program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        program_files_x86 = Path(
            os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")
        )
        for base_path in (program_files, program_files_x86):
            candidate = base_path / "draw.io" / "draw.io.exe"
            if exists(candidate):
                return [str(candidate)]

    if platform == "darwin":
        candidate = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")
        if exists(candidate):
            return [str(candidate)]

    return None


def classify_readiness(skill_path: Path | None, probe: ProbeResult | None) -> str:
    """Classify the availability of both required dependencies."""
    if probe is not None and probe.returncode != 0:
        return "unavailable"
    if skill_path is None or probe is None:
        return "needs-install"
    return "ready"


def probe_command(command: list[str]) -> ProbeResult:
    """Run exactly one bounded version probe for a resolved command."""
    try:
        completed = subprocess.run(
            [*command, "--version"],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(None, "", "draw.io --version timed out after 15 seconds")
    except OSError as error:
        return ProbeResult(None, "", str(error))
    return ProbeResult(completed.returncode, completed.stdout, completed.stderr)


def inspect_environment(
    home: Path,
    platform: str,
    which: Callable[[str], str | None],
    exists: Callable[[Path], bool],
    probe: Callable[[list[str]], ProbeResult | None],
) -> dict[str, object]:
    """Build a JSON-serializable, read-only readiness report."""
    skill_path = find_drawio_skill(home)
    command = resolve_drawio_command(platform, which, exists)
    probe_result = probe(command) if command is not None else None
    if command is not None and probe_result is None:
        probe_result = ProbeResult(None, "", "draw.io probe produced no usable result")

    missing: list[str] = []
    if skill_path is None:
        missing.append("drawio-skill")
    if command is None:
        missing.append("drawio-desktop")

    cli_state = "missing"
    detail = "draw.io command was not found"
    if command is not None:
        cli_state = "available" if probe_result and probe_result.returncode == 0 else "unavailable"
        detail = "\n".join(
            part for part in (probe_result.stdout, probe_result.stderr) if part
        ) if probe_result else "draw.io probe produced no usable result"

    return {
        "status": classify_readiness(skill_path, probe_result),
        "missing": missing,
        "drawioSkill": {
            "state": "available" if skill_path is not None else "missing",
            "path": str(skill_path) if skill_path is not None else "",
        },
        "drawioCli": {
            "state": cli_state,
            "command": command or [],
            "detail": detail,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--platform", choices=("win32", "darwin", "linux"), default=sys.platform)
    args = parser.parse_args()

    report = inspect_environment(
        home=args.home,
        platform=args.platform,
        which=shutil.which,
        exists=Path.is_file,
        probe=probe_command,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
