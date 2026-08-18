from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "annotate.py"


def make_raw_image(path: Path, size: tuple[int, int] = (320, 200)) -> None:
    image = Image.new("RGB", size, "#F7FFFC")
    image.save(path)


def manifest_for(image_name: str, annotations: list[dict]) -> dict:
    return {
        "sourceImage": image_name,
        "originalImageSize": {"width": 320, "height": 200},
        "annotations": annotations,
    }


class AnnotateCheckTests(unittest.TestCase):
    def run_tool(self, subcommand: str, image: Path, manifest_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), subcommand, "--image", str(image),
             "--annotations", str(manifest_path), *extra],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_valid_manifest_passes_and_draws(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            raw = workspace / "raw.png"
            output = workspace / "annotated.png"
            make_raw_image(raw, (320, 200))
            self.assertTrue(raw.exists())
            ann = manifest_for("raw.png", [
                {"id": "1", "controlName": "儲存", "caption": "紅框 1：儲存按鈕。",
                 "bbox": {"x": 40, "y": 60, "width": 80, "height": 30}, "status": "verified"},
            ])
            manifest_path = workspace / "annotations.json"
            manifest_path.write_text(json.dumps(ann), encoding="utf-8")

            check = self.run_tool("check", raw, manifest_path)
            draw = self.run_tool("draw", raw, manifest_path, "--output", str(output))

            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(draw.returncode, 0, draw.stderr)
            self.assertTrue(output.exists())
            with Image.open(output) as annotated, Image.open(raw) as source:
                self.assertEqual(annotated.size, source.size)
                self.assertNotEqual(annotated.tobytes(), source.tobytes())

    def test_out_of_bounds_box_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            raw = workspace / "raw.png"
            make_raw_image(raw)
            ann = manifest_for("raw.png", [
                {"id": "1", "controlName": "儲存", "caption": "紅框 1：儲存按鈕。",
                 "bbox": {"x": 300, "y": 100, "width": 80, "height": 200}, "status": "verified"},
            ])
            manifest_path = workspace / "annotations.json"
            manifest_path.write_text(json.dumps(ann), encoding="utf-8")

            result = self.run_tool("check", raw, manifest_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside", result.stderr)

    def test_duplicate_id_and_caption_mismatch_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            raw = workspace / "raw.png"
            make_raw_image(raw)
            ann = manifest_for("raw.png", [
                {"id": "1", "controlName": "儲存", "caption": "紅框 2：儲存按鈕。",
                 "bbox": {"x": 10, "y": 10, "width": 80, "height": 30}, "status": "verified"},
                {"id": "1", "controlName": "取消", "caption": "紅框 3：取消按鈕。",
                 "bbox": {"x": 10, "y": 60, "width": 80, "height": 30}, "status": "verified"},
            ])
            manifest_path = workspace / "annotations.json"
            manifest_path.write_text(json.dumps(ann), encoding="utf-8")

            result = self.run_tool("check", raw, manifest_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate id", result.stderr)
            self.assertIn("!= id", result.stderr)

    def test_unverified_caption_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            raw = workspace / "raw.png"
            make_raw_image(raw)
            ann = manifest_for("raw.png", [
                {"id": "1", "controlName": "儲存", "caption": "紅框 1：儲存按鈕。",
                 "bbox": {"x": 10, "y": 10, "width": 80, "height": 30}, "status": "proposed"},
            ])
            manifest_path = workspace / "annotations.json"
            manifest_path.write_text(json.dumps(ann), encoding="utf-8")

            result = self.run_tool("check", raw, manifest_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("status", result.stderr)


if __name__ == "__main__":
    unittest.main()