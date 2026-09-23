from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import validate_screenshot_manifest as validator  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class CoordinateProvenanceTests(unittest.TestCase):
    def test_viewport_transform_keeps_float_geometry_and_does_not_apply_dpr_twice(self) -> None:
        transform = {
            "status": "calibrated",
            "sourceSpace": "css-viewport",
            "targetSpace": "png-pixels",
            "viewportSize": {"width": 1536, "height": 674},
            "clip": {"x": 0, "y": 0, "width": 1536, "height": 674},
            "screenshotSize": {"width": 1521, "height": 667},
            "scrollOffset": {"x": 0, "y": 0},
            "devicePixelRatio": 1.25,
        }
        result = validator.transform_css_viewport_bbox(
            {
                "x": 591.7000122070312,
                "y": 196.8000030517578,
                "width": 68.63750457763672,
                "height": 28,
            },
            transform,
        )
        self.assertAlmostEqual(result["bbox"]["x"], 585.921692, places=5)
        self.assertAlmostEqual(result["bbox"]["y"], 194.756086, places=5)
        self.assertFalse(result["devicePixelRatioApplied"])

    def test_transform_rejects_source_outside_clip(self) -> None:
        transform = {
            "status": "calibrated",
            "sourceSpace": "css-viewport",
            "targetSpace": "png-pixels",
            "viewportSize": {"width": 100, "height": 100},
            "clip": {"x": 10, "y": 10, "width": 80, "height": 80},
            "screenshotSize": {"width": 80, "height": 80},
            "scrollOffset": {"x": 0, "y": 0},
            "devicePixelRatio": 1,
        }
        with self.assertRaises(validator.CoordinateTransformError) as context:
            validator.transform_css_viewport_bbox({"x": 0, "y": 10, "width": 10, "height": 10}, transform)
        self.assertEqual(context.exception.code, "coordinate_source_bbox_out_of_clip")

    def test_strict_gate_blocks_legacy_manual_box_without_transform(self) -> None:
        manifest = {
            "schema_version": 1,
            "sourceImage": "raw.png",
            "sourceSha256": "0" * 64,
            "redactedImage": "redacted.png",
            "redactedSha256": "1" * 64,
            "annotatedImage": "annotated.png",
            "annotatedSha256": "2" * 64,
            "sourceKind": "captured",
            "captureKind": "detail",
            "captureState": {"id": "terra-legacy", "rawSha256": "0" * 64},
            "originalImageSize": {"width": 1398, "height": 674},
            "reviewStatus": "checked",
            "redactions": [],
            "noSensitiveDataReason": "test fixture",
            "annotations": [{
                "id": "button-2",
                "controlName": "按鈕",
                "caption": "紅框 2：按鈕。",
                "bbox": {"x": 758, "y": 180, "width": 59, "height": 29},
                "source": "dom-manual-adjusted",
                "status": "checked",
            }],
            "protectedAreas": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coordinate-fixture.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            report = validator.validate_manifest(path, require_coordinate_provenance=True)
        codes = {item["code"] for item in report["findings"]}
        self.assertEqual(report["coordinate_provenance"]["status"], "blocked")
        self.assertIn("coordinate_transform_missing", codes)

    def test_strict_gate_accepts_complete_chain_with_pending_only_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            (root / "redacted").mkdir()
            (root / "annotated").mkdir()
            raw = root / "raw" / "screen.png"
            redacted = root / "redacted" / "screen.png"
            annotated = root / "annotated" / "screen.png"
            Image.new("RGB", (320, 200), "white").save(raw, format="PNG")
            source_sha = sha256(raw)
            transform = {
                "status": "calibrated",
                "sourceSpace": "css-viewport",
                "targetSpace": "png-pixels",
                "viewportSize": {"width": 320, "height": 200},
                "clip": {"x": 0, "y": 0, "width": 320, "height": 200},
                "screenshotSize": {"width": 320, "height": 200},
                "scrollOffset": {"x": 0, "y": 0},
                "devicePixelRatio": 1,
            }
            manifest = {
                "schema_version": 1,
                "sourceImage": "raw/screen.png",
                "sourceSha256": source_sha,
                "redactedImage": "redacted/screen.png",
                "annotatedImage": "annotated/screen.png",
                "sourceKind": "captured",
                "captureKind": "viewport-sequence",
                "captureState": {
                    "id": "complete-state-01",
                    "rawSha256": source_sha,
                    "viewportCssSize": {"width": 320, "height": 200},
                    "scroll": {"x": 0, "y": 0},
                    "coordinateTransform": transform,
                    "calibration": {
                        "mode": "known-control",
                        "pngSize": {"width": 320, "height": 200},
                        "viewportCssSize": {"width": 320, "height": 200},
                        "knownControl": {"bbox": {"x": 120, "y": 80, "width": 70, "height": 30}},
                    },
                },
                "originalImageSize": {"width": 320, "height": 200},
                "reviewStatus": "pending",
                "redactions": [],
                "noSensitiveDataReason": "synthetic fixture",
                "annotations": [{
                    "id": "1",
                    "controlName": "儲存",
                    "caption": "紅框 1：儲存按鈕。",
                    "bbox": {"x": 120, "y": 80, "width": 70, "height": 30},
                    "source": "dom",
                    "coordinateProvenance": {
                        "captureStateId": "complete-state-01",
                        "sourceSha256": source_sha,
                        "sourceBbox": {"x": 120, "y": 80, "width": 70, "height": 30},
                    },
                    "status": "pending",
                }],
                "protectedAreas": [],
            }
            manifest_path = root / "screen.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            redaction = run(
                SCRIPT_ROOT / "redact.py", "draw", "--image", str(raw), "--manifest", str(manifest_path),
                "--output", str(redacted), "--provenance-output", str(root / "redaction-provenance.json"),
            )
            self.assertEqual(redaction.returncode, 0, redaction.stderr)
            manifest["redactedSha256"] = sha256(redacted)
            manifest["redactionProvenance"] = "redaction-provenance.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            annotation = run(
                SCRIPT_ROOT / "annotate.py", "draw", "--image", str(redacted), "--annotations", str(manifest_path),
                "--output", str(annotated), "--provenance-output", str(root / "annotation-provenance.json"),
            )
            self.assertEqual(annotation.returncode, 0, annotation.stderr)
            manifest["annotatedSha256"] = sha256(annotated)
            manifest["annotationProvenance"] = "annotation-provenance.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            report = validator.validate_manifest(manifest_path, require_coordinate_provenance=True)
            self.assertEqual(report["coordinate_provenance"]["status"], "pass")
            self.assertEqual(report["geometry_status"], "pass")
            self.assertEqual(report["manifest_status"], "blocked")
            self.assertEqual(report["semantic_review"], "not_performed")
            self.assertEqual({item["code"] for item in report["findings"]}, {"approval_pending"})


if __name__ == "__main__":
    unittest.main()
