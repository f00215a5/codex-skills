"""Contract tests for the Python-only lite workflow and chat-only limits."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]


class ConversationReportingTests(unittest.TestCase):
    def test_lite_workflow_is_python_only_and_reports_limits_in_chat(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        qa_text = (SKILL_ROOT / "references" / "document-structure-qa.md").read_text(
            encoding="utf-8"
        )
        guidance = "\n".join((skill_text, qa_text))

        self.assertIn("Python-only", manifest["description"])
        self.assertIn("external document engine", manifest["interface"]["longDescription"])
        self.assertIn("對話中向使用者回報", guidance)
        self.assertIn("不得寫入 DOCX", guidance)
        self.assertIn("交付文件只保留使用者確認的操作內容", guidance)


if __name__ == "__main__":
    unittest.main()
