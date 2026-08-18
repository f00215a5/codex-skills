"""Contract tests for the concise full UI guide skill name."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]


class CoreSkillNamingTests(unittest.TestCase):
    def test_full_plugin_exposes_ui_guide_without_changing_plugin_id(self) -> None:
        expected_skill_root = PLUGIN_ROOT / "skills" / "ui-guide"
        old_skill_root = PLUGIN_ROOT / "skills" / "ui-ops-manual"

        self.assertTrue((expected_skill_root / "SKILL.md").is_file())
        self.assertFalse(old_skill_root.exists())

        skill_text = (expected_skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill_text, r"(?m)^name: ui-guide$")

        agent_text = (expected_skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("$ui-guide", agent_text)
        self.assertNotIn("$ui-ops-manual", agent_text)

        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "ui-ops-manual")
        self.assertTrue(
            all("$ui-guide" in prompt for prompt in manifest["interface"]["defaultPrompt"])
        )
        self.assertTrue(
            all(
                path.startswith("./skills/ui-guide/assets/")
                for path in (
                    manifest["interface"]["composerIcon"],
                    manifest["interface"]["logo"],
                    manifest["interface"]["logoDark"],
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
