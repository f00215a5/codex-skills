"""Contract tests for placing the update log directly below the title."""

from __future__ import annotations

import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class UpdateLogLayoutTests(unittest.TestCase):
    def test_full_guide_places_the_update_log_below_the_title(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        layout_text = (SKILL_ROOT / "references" / "default-document-layout.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("2. **更新紀錄**：標題區塊正下方", skill_text)
        self.assertIn("2. **更新紀錄**：緊接標題區塊", layout_text)
        self.assertNotIn("## 文件末頁", layout_text)


if __name__ == "__main__":
    unittest.main()
