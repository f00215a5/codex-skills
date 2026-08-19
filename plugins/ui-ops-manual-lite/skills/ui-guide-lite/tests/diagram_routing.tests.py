"""Contract tests for conditional ui-diagrams routing."""

from __future__ import annotations

import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class DiagramRoutingTests(unittest.TestCase):
    def test_routes_explicit_non_screenshot_diagrams_to_the_shared_skill(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("$ui-diagrams", skill_text)
        self.assertIn("流程圖、關係圖、架構圖、狀態圖或泳道圖", skill_text)
        self.assertIn("明確要求", skill_text)

    def test_keeps_screenshot_annotations_in_the_ui_manual_workflow(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("截圖、紅框、游標", skill_text)
        self.assertIn("不呼叫 $ui-diagrams", skill_text)


if __name__ == "__main__":
    unittest.main()
