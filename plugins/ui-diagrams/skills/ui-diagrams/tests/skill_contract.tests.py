"""Structural contract tests for the ui-diagrams orchestration skill."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
SKILL_MD = SKILL_ROOT / "SKILL.md"
POLICY_MD = SKILL_ROOT / "references/dependency-and-install-policy.md"
MARKETPLACE_PATH = PLUGIN_ROOT.parents[1] / ".agents/plugins/marketplace.json"


class UiDiagramsSkillContractTests(unittest.TestCase):
    def test_plugin_exposes_the_only_ui_diagrams_skill(self) -> None:
        manifest_path = PLUGIN_ROOT / ".codex-plugin/plugin.json"
        skill_path = PLUGIN_ROOT / "skills/ui-diagrams/SKILL.md"
        self.assertTrue(manifest_path.is_file())
        self.assertTrue(skill_path.is_file())
        if not manifest_path.is_file() or not skill_path.is_file():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skill = skill_path.read_text(encoding="utf-8")
        self.assertEqual(manifest["name"], "ui-diagrams")
        self.assertRegex(skill, r"(?m)^name: ui-diagrams$")
        self.assertIn("$drawio-skill", skill)

    def test_marketplace_exposes_ui_diagrams_with_the_required_install_policy(self) -> None:
        self.assertTrue(MARKETPLACE_PATH.is_file())
        if not MARKETPLACE_PATH.is_file():
            return
        marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
        entry = next(
            (
                plugin
                for plugin in marketplace["plugins"]
                if plugin["name"] == "ui-diagrams"
            ),
            None,
        )
        self.assertEqual(
            entry,
            {
                "name": "ui-diagrams",
                "source": {"source": "local", "path": "./plugins/ui-diagrams"},
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            },
        )

    def test_skill_requires_consent_and_preserves_the_manual_when_diagrams_stop(self) -> None:
        self.assertTrue(SKILL_MD.is_file())
        self.assertTrue(POLICY_MD.is_file())
        if not SKILL_MD.is_file() or not POLICY_MD.is_file():
            return
        guidance = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SKILL_MD, POLICY_MD)
        )
        self.assertIn("明確同意", guidance)
        self.assertIn("只停止圖表分支", guidance)
        self.assertIn("立即交棒給 $drawio-skill", guidance)
        self.assertIn("不自行建立、預覽、匯出或修改", guidance)
        self.assertIn(".drawio", guidance)
        self.assertIn("PNG", guidance)

    def test_install_failure_is_terminal_and_keeps_the_manual_running(self) -> None:
        guidance = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SKILL_MD, POLICY_MD)
        )
        self.assertIn("clone、desktop 安裝或重新檢查失敗", guidance)
        self.assertIn("分類為 `unavailable`", guidance)
        self.assertIn("不得重新進入同意或安裝迴圈", guidance)
        self.assertIn("僅在對話中", guidance)
        self.assertIn("只停止圖表分支", guidance)
        self.assertIn("繼續 UI 手冊流程", guidance)

    def test_current_task_directly_loads_a_successful_install_before_handoff(self) -> None:
        guidance = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SKILL_MD, POLICY_MD)
        )
        self.assertIn("目前任務直接載入並閱讀", guidance)
        self.assertIn(
            ".codex/skills/drawio-skill/skills/drawio-skill/SKILL.md", guidance
        )
        self.assertIn("直接讀取後立即交棒給 $drawio-skill", guidance)
        self.assertIn("新的 Codex 任務仍可能需要", guidance)
        self.assertIn("正常自動發現", guidance)
        self.assertIn("不自行建立、預覽、匯出或修改", guidance)


if __name__ == "__main__":
    unittest.main()
