"""Contract tests for the per-image screenshot manifest validator."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from PIL import Image


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))
import validate_screenshot_manifest as validator  # noqa: E402


class ScreenshotManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        # CI can set UI_GUIDE_TEST_TMP to a writable task-local directory when
        # the bundled Windows runtime has a read-only user TEMP.  The default
        # stays portable and does not encode a machine path in the product.
        override = os.environ.get("UI_GUIDE_TEST_TMP")
        if override:
            temp_root = Path(override) / "ui-guide-manifest-tests"
            temp_root.mkdir(parents=True, exist_ok=True)
            self.root = temp_root / f"run-{uuid.uuid4().hex}"
            self.root.mkdir(parents=True)
            self.temp_dir = None
        else:
            self.temp_dir = tempfile.TemporaryDirectory()
            self.root = Path(self.temp_dir.name)
        self.qa = self.root / "qa"
        self.qa.mkdir()
        (self.root / "raw").mkdir()
        (self.root / "redacted").mkdir()
        (self.root / "annotated").mkdir()

    def tearDown(self) -> None:
        if self.temp_dir is None:
            shutil.rmtree(self.root, ignore_errors=True)
        else:
            self.temp_dir.cleanup()

    def _image(self, path: Path, color: tuple[int, int, int]) -> None:
        Image.new("RGB", (20, 10), color).save(path, format="PNG")

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _write_manifest(self, *, no_sensitive: bool = False) -> Path:
        raw_path = self.root / "raw" / "screen.png"
        redacted_path = self.root / "redacted" / "screen.png"
        annotated_path = self.root / "annotated" / "screen.png"
        if not raw_path.exists():
            self._image(raw_path, (20, 30, 40))
        if not redacted_path.exists():
            self._image(redacted_path, (20, 30, 40))
        if not annotated_path.exists():
            self._image(annotated_path, (50, 60, 70))
        source_sha = self._sha256(raw_path)
        manifest = {
            "schema_version": 1,
            "sourceImage": "raw/screen.png",
            "sourceSha256": source_sha,
            "redactedImage": "redacted/screen.png",
            "annotatedImage": "annotated/screen.png",
            "sourceKind": "captured",
            "captureKind": "full-page",
            "captureState": {"id": "screen-state-01", "rawSha256": source_sha},
            "originalImageSize": {"width": 20, "height": 10},
            "reviewStatus": "checked",
            "redactions": [],
            "annotations": [],
        }
        if no_sensitive:
            manifest["noSensitiveDataReason"] = "No sensitive values are visible in this state."
        path = self.qa / "screen.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return path

    def _load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_recapture_with_different_hash_and_same_dimensions_is_bound_to_new_state(self) -> None:
        manifest_path = self._write_manifest(no_sensitive=True)
        first = validator.validate_manifest(manifest_path, "..")
        self.assertEqual(first["status"], "pass")
        original_manifest = self._load(manifest_path)
        old_sha = original_manifest["sourceSha256"]

        self._image(self.root / "raw" / "screen.png", (220, 30, 40))
        stale = validator.validate_manifest(manifest_path, "..")
        self.assertNotEqual(stale["status"], "pass")
        self.assertIn(
            "source_sha256_mismatch",
            {item["code"] for item in stale["findings"]},
        )
        manifest = self._load(manifest_path)
        new_sha = self._sha256(self.root / "raw" / "screen.png")
        manifest["sourceSha256"] = new_sha
        manifest["captureState"] = {"id": "screen-state-02", "rawSha256": new_sha}
        self._save(manifest_path, manifest)

        second = validator.validate_manifest(manifest_path, "..")
        self.assertNotEqual(old_sha, new_sha)
        self.assertEqual(second["geometry_status"], "pass")
        self.assertEqual(second["status"], "pass")

    def test_out_of_bounds_redaction_and_annotation_are_rejected(self) -> None:
        manifest_path = self._write_manifest()
        manifest = self._load(manifest_path)
        manifest["redactions"] = [{
            "category": "identifier",
            "method": "opaque-rectangle",
            "status": "checked",
            "bbox": {"x": 19, "y": 1, "width": 3, "height": 2},
        }]
        manifest["annotations"] = [{
            "id": "1",
            "controlName": "Save",
            "caption": "Box 1",
            "source": "dom-manual-adjusted",
            "status": "verified",
            "bbox": {"x": 1, "y": -1, "width": 3, "height": 2},
        }]
        self._save(manifest_path, manifest)

        report = validator.validate_manifest(manifest_path, "..")
        codes = {item["code"] for item in report["findings"]}
        self.assertIn("bbox_invalid", codes)
        self.assertEqual(report["status"], "fail")

    def test_wrong_image_dimensions_are_rejected(self) -> None:
        manifest_path = self._write_manifest(no_sensitive=True)
        self._image(self.root / "redacted" / "screen.png", (20, 30, 40))
        # Pillow's save above is 20x10; replace with a deliberately different
        # PNG while keeping the manifest's originalImageSize unchanged.
        Image.new("RGB", (21, 10), (20, 30, 40)).save(self.root / "redacted" / "screen.png", format="PNG")

        report = validator.validate_manifest(manifest_path, "..")
        self.assertIn(
            "image_dimensions_mismatch",
            {item["code"] for item in report["findings"]},
        )
        self.assertEqual(report["status"], "fail")

    def test_no_sensitive_image_with_explicit_reason_can_pass(self) -> None:
        manifest_path = self._write_manifest(no_sensitive=True)
        report = validator.validate_manifest(manifest_path, "..")
        self.assertEqual(report["geometry_status"], "pass")
        self.assertEqual(report["manifest_status"], "pass")

    def test_pending_preview_has_geometry_pass_but_never_delivery_pass(self) -> None:
        manifest_path = self._write_manifest(no_sensitive=True)
        manifest = self._load(manifest_path)
        manifest["reviewStatus"] = "pending"
        self._save(manifest_path, manifest)

        report = validator.validate_manifest(manifest_path, "..")
        self.assertEqual(report["geometry_status"], "pass")
        self.assertEqual(report["manifest_status"], "blocked")
        self.assertNotEqual(report["status"], "pass")
        self.assertEqual(report["semantic_review"], "not_performed")

    def test_protected_area_overlap_is_rejected(self) -> None:
        manifest_path = self._write_manifest()
        manifest = self._load(manifest_path)
        manifest["redactions"] = [{
            "category": "identifier",
            "method": "opaque-rectangle",
            "status": "checked",
            "bbox": {"x": 4, "y": 2, "width": 4, "height": 3},
        }]
        manifest["protectedAreas"] = [{"bbox": {"x": 6, "y": 3, "width": 4, "height": 2}}]
        self._save(manifest_path, manifest)

        report = validator.validate_manifest(manifest_path, "..")
        self.assertIn(
            "redaction_overlaps_protected_area",
            {item["code"] for item in report["findings"]},
        )

    def test_missing_status_is_not_defaulted_and_output_does_not_echo_caption(self) -> None:
        manifest_path = self._write_manifest(no_sensitive=True)
        manifest = self._load(manifest_path)
        manifest["annotations"] = [{
            "id": "1",
            "controlName": "Save",
            "caption": "SECRET-VALUE-123",
            "source": "dom-manual-adjusted",
        }]
        self._save(manifest_path, manifest)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = validator.main(["--manifest", str(manifest_path), "--base-dir", "..", "--output", "-"])
        self.assertEqual(code, 1)
        self.assertIn("annotation_status_missing", output.getvalue())
        self.assertNotIn("SECRET-VALUE-123", output.getvalue())

    def test_cli_refuses_to_overwrite_any_input_image(self) -> None:
        manifest_path = self._write_manifest(no_sensitive=True)
        original_path = self.root / "raw-original.capture"
        original_path.write_bytes((self.root / "raw" / "screen.png").read_bytes())
        original_alias_path = self.root / "original-capture-alias.capture"
        original_alias_path.write_bytes(original_path.read_bytes())
        artifact_path = self.root / "capture-artifact.bin"
        artifact_path.write_bytes(original_path.read_bytes())
        manifest = self._load(manifest_path)
        manifest["captureProvenance"] = {
            "originalFile": "raw-original.capture",
            "originalMime": "image/png",
            "originalSha256": self._sha256(original_path),
            "decodedSourceImage": "raw/screen.png",
            "pixelEquality": "verified",
        }
        manifest["originalCapturePath"] = "original-capture-alias.capture"
        manifest["captureArtifact"] = "capture-artifact.bin"
        self._save(manifest_path, manifest)
        input_paths = [
            manifest_path,
            self.root / "raw" / "screen.png",
            self.root / "redacted" / "screen.png",
            self.root / "annotated" / "screen.png",
            original_path,
            original_alias_path,
            artifact_path,
        ]
        for output_path in input_paths:
            before = output_path.read_bytes()
            code = validator.main([
                "--manifest", str(manifest_path),
                "--base-dir", "..",
                "--output", str(output_path),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(output_path.read_bytes(), before)

        hardlink = self.root / "raw-hardlink.png"
        try:
            hardlink.hardlink_to(self.root / "raw" / "screen.png")
        except (FileExistsError, OSError):
            hardlink = None
        if hardlink is not None:
            before = hardlink.read_bytes()
            code = validator.main([
                "--manifest", str(manifest_path),
                "--base-dir", "..",
                "--output", str(hardlink),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(hardlink.read_bytes(), before)

    def test_cli_refuses_file_output_for_unreadable_manifest(self) -> None:
        manifest_path = self.qa / "broken.json"
        manifest_path.write_text("{\"sourceImage\":", encoding="utf-8")
        source_path = self.root / "raw" / "screen.png"
        self._image(source_path, (20, 30, 40))
        before = source_path.read_bytes()

        code = validator.main([
            "--manifest", str(manifest_path),
            "--base-dir", "..",
            "--output", str(source_path),
        ])

        self.assertEqual(code, 2)
        self.assertEqual(source_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
