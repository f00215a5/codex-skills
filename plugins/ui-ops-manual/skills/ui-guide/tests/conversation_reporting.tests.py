"""Contract tests for renderer limitations reported outside the manual."""

from __future__ import annotations

import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class ConversationReportingTests(unittest.TestCase):
    def test_renderer_availability_is_reported_in_chat_not_the_docx(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        layout_text = (SKILL_ROOT / "references" / "default-document-layout.md").read_text(
            encoding="utf-8"
        )
        qa_text = (SKILL_ROOT / "references" / "render-and-annotation-qa.md").read_text(
            encoding="utf-8"
        )
        guidance = "\n".join((skill_text, layout_text, qa_text))

        self.assertIn("對話中向使用者回報", guidance)
        self.assertIn("不得寫入 DOCX", guidance)
        self.assertIn("交付文件只保留使用者確認的操作內容", guidance)


if __name__ == "__main__":
    unittest.main()
