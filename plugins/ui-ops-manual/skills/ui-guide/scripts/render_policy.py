#!/usr/bin/env python3
"""Persist the UI-manual-only decision for a Word renderer permission failure.

The file deliberately stores only an allow/deny fallback policy.  It never
records document paths, repository URLs, account details, or font selections.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence


POLICY_FILE_NAME = "ui-ops-manual-render-policy.json"
SCHEMA_VERSION = 1
ALLOWED_POLICIES = {"allow", "deny"}


def policy_path(work_root: Path) -> Path:
    return work_root.expanduser().resolve() / POLICY_FILE_NAME


def ask_response() -> dict[str, str]:
    return {"mode": "ask"}


def read_policy(work_root: Path) -> dict[str, str]:
    """Return ask for absent or invalid data, so malformed state fails closed."""

    path = policy_path(work_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return ask_response()

    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != SCHEMA_VERSION
        or payload.get("scope") != "ui-ops-manual"
        or payload.get("fallbackPolicy") not in ALLOWED_POLICIES
    ):
        return ask_response()
    return {"mode": "remember", "fallbackPolicy": payload["fallbackPolicy"]}


def save_policy(work_root: Path, fallback_policy: str) -> dict[str, str]:
    if fallback_policy not in ALLOWED_POLICIES:
        raise ValueError(f"Unsupported fallback policy: {fallback_policy}")

    path = policy_path(work_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "scope": "ui-ops-manual",
        "fallbackPolicy": fallback_policy,
    }
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, path)
    return {"mode": "remember", "fallbackPolicy": fallback_policy}


def reset_policy(work_root: Path) -> dict[str, str]:
    try:
        policy_path(work_root).unlink(missing_ok=True)
    except OSError as error:
        raise RuntimeError(f"Cannot reset UI manual render policy: {error}") from error
    return ask_response()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read, remember, or reset the UI-manual-only Word fallback policy."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("get", "reset"):
        command = subparsers.add_parser(name)
        command.add_argument("--work-root", required=True)
    set_command = subparsers.add_parser("set")
    set_command.add_argument("--work-root", required=True)
    set_command.add_argument("--fallback-policy", choices=sorted(ALLOWED_POLICIES), required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    work_root = Path(args.work_root)
    try:
        if args.command == "get":
            response = read_policy(work_root)
        elif args.command == "set":
            response = save_policy(work_root, args.fallback_policy)
        else:
            response = reset_policy(work_root)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"render_policy.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
