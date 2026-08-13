from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "render_policy.py"


class RenderPolicyTests(unittest.TestCase):
    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_missing_policy_requires_a_choice(self) -> None:
        """First use must not silently authorize a LibreOffice fallback."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_root = Path(temporary_directory) / "word-render"
            result = self.run_tool("get", "--work-root", str(work_root))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({"mode": "ask"}, json.loads(result.stdout))

    def test_remembered_fallback_can_be_read_and_reset(self) -> None:
        """Only the UI-manual renderer policy survives between tasks on this device."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_root = Path(temporary_directory) / "word-render"
            saved = self.run_tool(
                "set",
                "--work-root",
                str(work_root),
                "--fallback-policy",
                "allow",
            )
            restored = self.run_tool("get", "--work-root", str(work_root))
            reset = self.run_tool("reset", "--work-root", str(work_root))
            after_reset = self.run_tool("get", "--work-root", str(work_root))

        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(
            {"mode": "remember", "fallbackPolicy": "allow"},
            json.loads(restored.stdout),
        )
        self.assertEqual(reset.returncode, 0, reset.stderr)
        self.assertEqual({"mode": "ask"}, json.loads(after_reset.stdout))

    def test_invalid_policy_fails_closed_by_requesting_a_choice(self) -> None:
        """A corrupted local file must never enable an implicit renderer fallback."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_root = Path(temporary_directory) / "word-render"
            work_root.mkdir()
            (work_root / "ui-ops-manual-render-policy.json").write_text(
                '{"fallbackPolicy":"anything"}',
                encoding="utf-8",
            )
            result = self.run_tool("get", "--work-root", str(work_root))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({"mode": "ask"}, json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
