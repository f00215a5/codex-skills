from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).parents[1] / "scripts"
BUILD_SCRIPT = SCRIPTS / "build_docx.py"
VERIFY_SCRIPT = SCRIPTS / "verify_docx.py"

MINIMAL_MANIFEST = {
    "title": "訂單管理操作說明書",
    "subtitle": "系統後台操作指引",
    "applicableScreens": ["系統後台 > 訂單管理 > 訂單列表"],
    "revision": {"version": "1.0", "date": "2026-01-15", "summary": "初版"},
    "usageReminders": ["截圖與操作以測試環境為準，遮蔽敏感資料。"],
    "commonRules": ["必填欄位以紅色 * 標示。"],
    "fontName": "PingFang TC",
    "chapter": {
        "title": "訂單管理功能",
        "entry": {"caption": "功能入口：訂單管理。", "image": "annotated/entry.png",
                  "detail": "從側邊欄進入。"},
        "sections": [
            {
                "title": "查詢訂單",
                "preconditions": "已登入系統後台。",
                "steps": [
                    {"caption": "紅框 1：點選「訂單查詢」。", "image": "annotated/step1.png",
                     "detail": "系統顯示查詢表單。"},
                    {"caption": "紅框 2：輸入訂單編號後按查詢。", "image": "annotated/step2.png"},
                ],
                "fields": [
                    {"name": "訂單編號", "definition": "訂單的唯一識別碼。",
                     "required": "選填", "limits": "最大 30 字元", "display": "查詢區"},
                ],
                "impact": "查詢結果會依權限過濾，不影響資料本身。",
                "failure": "無符合資料時顯示空清單與提示。",
                "verification": "以同一筆訂單編號重查可得到相同結果。",
            },
            {
                "title": "開立訂單",
                "steps": [
                    {"caption": "紅框 1：點選「新增訂單」。", "image": "annotated/step3.png"},
                ],
                "fields": [
                    {"name": "客戶", "definition": "訂單所屬客戶。",
                     "required": "必填", "limits": "下拉選單"},
                ],
                "impact": "成功後建立新訂單並產生訂單編號。",
                "verification": "於訂單列表可見新訂單。",
            },
        ],
    },
    "updateLog": [{"version": "1.0", "date": "2026-01-15", "changes": "初版"}],
}


def make_annotated_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 200), "#F7FFFC").save(path)


def run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class BuildAndVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.images = self.workspace / "annotated"
        for name in ("entry.png", "step1.png", "step2.png", "step3.png"):
            make_annotated_image(self.images / name)
        self.manifest_path = self.workspace / "manual.json"
        self.manifest_path.write_text(json.dumps(MINIMAL_MANIFEST), encoding="utf-8")
        self.docx_path = self.workspace / "manual.docx"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_and_verify(self) -> subprocess.CompletedProcess[str]:
        build = run(BUILD_SCRIPT, "--manifest", str(self.manifest_path), "--output", str(self.docx_path))
        self.assertEqual(build.returncode, 0, build.stderr)
        return run(VERIFY_SCRIPT, "--docx", str(self.docx_path), "--manifest", str(self.manifest_path))

    def test_round_trip_build_passes_structure_qa(self) -> None:
        verify = self.build_and_verify()
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        self.assertIn("all structure checks passed", verify.stdout)

    def test_missing_image_fails_build(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["chapter"]["sections"][0]["steps"][0]["image"] = "annotated/does-not-exist.png"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        build = run(BUILD_SCRIPT, "--manifest", str(self.manifest_path), "--output", str(self.docx_path))

        self.assertNotEqual(build.returncode, 0)
        self.assertIn("image not found", build.stderr)

    def test_verify_catches_empty_update_log(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["updateLog"] = []
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        build = run(BUILD_SCRIPT, "--manifest", str(self.manifest_path), "--output", str(self.docx_path))
        self.assertEqual(build.returncode, 0, build.stderr)

        verify = run(VERIFY_SCRIPT, "--docx", str(self.docx_path), "--manifest", str(self.manifest_path))

        self.assertNotEqual(verify.returncode, 0)
        self.assertIn("update log has data rows", verify.stdout)

    def test_docx_is_a_valid_zip_package(self) -> None:
        self.build_and_verify()
        import zipfile
        with zipfile.ZipFile(self.docx_path) as archive:
            bad = archive.testzip()
        self.assertIsNone(bad)


if __name__ == "__main__":
    unittest.main()