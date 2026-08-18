"""Contract tests for the concise lite UI guide skill name."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]


class CoreSkillNamingTests(unittest.TestCase):
    def test_lite_plugin_exposes_ui_guide_lite_without_changing_plugin_id(self) -> None:
        expected_skill_root = PLUGIN_ROOT / "skills" / "ui-guide-lite"
        old_skill_root = PLUGIN_ROOT / "skills" / "ui-ops-manual-lite"

        self.assertTrue((expected_skill_root / "SKILL.md").is_file())
        self.assertFalse(old_skill_root.exists())

        skill_text = (expected_skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill_text, r"(?m)^name: ui-guide-lite$")

        agent_text = (expected_skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("$ui-guide-lite", agent_text)
        self.assertNotIn("$ui-ops-manual-lite", agent_text)

        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "ui-ops-manual-lite")
        self.assertTrue(
            all(
                "$ui-guide-lite" in prompt
                for prompt in manifest["interface"]["defaultPrompt"]
            )
        )
        self.assertTrue(
            all(
                path.startswith("./skills/ui-guide-lite/assets/")
                for path in (
                    manifest["interface"]["composerIcon"],
                    manifest["interface"]["logo"],
                    manifest["interface"]["logoDark"],
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
