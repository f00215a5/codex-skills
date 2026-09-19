from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
REDACT = SCRIPTS / "redact.py"
ANNOTATE = SCRIPTS / "annotate.py"
VALIDATE = SCRIPTS / "validate_screenshot_manifest.py"


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


class ScreenshotManifestTests(unittest.TestCase):
    def _write_fixture(self, work: Path) -> tuple[Path, dict]:
        (work / "raw").mkdir()
        (work / "redacted").mkdir()
        (work / "annotated").mkdir()
        raw = work / "raw" / "screen.png"
        Image.new("RGB", (320, 200), "white").save(raw, format="PNG")
        source_hash = sha256(raw)
        manifest = {
            "schema_version": 1,
            "sourceImage": "raw/screen.png",
            "sourceSha256": source_hash,
            "redactedImage": "redacted/screen.png",
            "annotatedImage": "annotated/screen.png",
            "sourceKind": "captured",
            "captureKind": "full-page",
            "captureState": {
                "id": "screen-state-01",
                "rawSha256": source_hash,
                "viewportCssSize": {"width": 320, "height": 200},
                "scroll": {"x": 0, "y": 0},
                "calibration": {
                    "mode": "known-control",
                    "pngSize": {"width": 320, "height": 200},
                    "viewportCssSize": {"width": 320, "height": 200},
                    "knownControl": {
                        "name": "儲存",
                        "bbox": {"x": 120, "y": 80, "width": 70, "height": 30},
                    },
                },
            },
            "originalImageSize": {"width": 320, "height": 200},
            "reviewStatus": "checked",
            "redactions": [{
                "category": "policy-number",
                "method": "opaque-rectangle",
                "bbox": {"x": 20, "y": 20, "width": 40, "height": 18},
                "status": "checked",
            }],
            "annotations": [{
                "id": "1",
                "controlName": "儲存",
                "caption": "紅框 1：儲存按鈕。",
                "bbox": {"x": 120, "y": 80, "width": 70, "height": 30},
                "source": "dom-manual-adjusted",
                "status": "verified",
            }],
            "protectedAreas": [],
        }
        path = work / "screen.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return path, manifest

    def test_canonical_manifest_runs_redact_annotate_and_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            manifest_path, manifest = self._write_fixture(work)
            redacted = work / "redacted" / "screen.png"
            annotated = work / "annotated" / "screen.png"

            redaction = run(REDACT, "draw", "--image", str(work / "raw" / "screen.png"),
                            "--manifest", str(manifest_path), "--output", str(redacted),
                            "--provenance-output", str(work / "redaction-provenance.json"))
            self.assertEqual(redaction.returncode, 0, redaction.stderr)
            manifest["redactedSha256"] = sha256(redacted)
            manifest["redactionProvenance"] = "redaction-provenance.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            redaction_check = run(
                REDACT,
                "check",
                "--require-checked",
                "--image",
                str(work / "raw" / "screen.png"),
                "--redacted",
                str(redacted),
                "--manifest",
                str(manifest_path),
            )
            self.assertEqual(redaction_check.returncode, 0, redaction_check.stderr)
            annotation_check = run(ANNOTATE, "check", "--require-approved", "--image", str(redacted),
                                   "--annotations", str(manifest_path))
            self.assertEqual(annotation_check.returncode, 0, annotation_check.stderr)
            annotation = run(ANNOTATE, "draw", "--require-approved", "--image", str(redacted),
                             "--annotations", str(manifest_path), "--output", str(annotated),
                             "--provenance-output", str(work / "annotation-provenance.json"))
            self.assertEqual(annotation.returncode, 0, annotation.stderr)
            manifest["annotatedSha256"] = sha256(annotated)
            manifest["annotationProvenance"] = "annotation-provenance.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            report_path = work / "validation.json"
            validation = run(VALIDATE, "--manifest", str(manifest_path), "--output", str(report_path))
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["semantic_review"], "not_performed")

    def test_annotation_rejects_declared_redacted_hash_mismatch_or_format(self) -> None:
        for declared in ("0" * 64, "not-a-sha256"):
            with self.subTest(declared=declared), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                manifest_path, manifest = self._write_fixture(work)
                redacted = work / "redacted" / "screen.png"
                redaction = run(REDACT, "draw", "--image", str(work / "raw" / "screen.png"),
                                "--manifest", str(manifest_path), "--output", str(redacted))
                self.assertEqual(redaction.returncode, 0, redaction.stderr)
                manifest["redactedSha256"] = declared
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

                result = run(ANNOTATE, "check", "--require-approved", "--image", str(redacted),
                             "--annotations", str(manifest_path))

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("redactedSha256", result.stderr)

    def test_validator_rejects_declared_derived_hash_mismatch_or_format(self) -> None:
        for redacted_declared, annotated_declared in (("0" * 64, "0" * 64), ("bad", "also-bad")):
            with self.subTest(redacted=redacted_declared), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                manifest_path, manifest = self._write_fixture(work)
                redacted = work / "redacted" / "screen.png"
                annotated = work / "annotated" / "screen.png"
                redaction = run(REDACT, "draw", "--image", str(work / "raw" / "screen.png"),
                                "--manifest", str(manifest_path), "--output", str(redacted))
                self.assertEqual(redaction.returncode, 0, redaction.stderr)
                annotation = run(ANNOTATE, "draw", "--image", str(redacted),
                                 "--annotations", str(manifest_path), "--output", str(annotated))
                self.assertEqual(annotation.returncode, 0, annotation.stderr)
                manifest["redactedSha256"] = redacted_declared
                manifest["annotatedSha256"] = annotated_declared
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                output = work / "validation.json"

                result = run(VALIDATE, "--manifest", str(manifest_path), "--output", str(output))

                self.assertEqual(result.returncode, 1)
                report = json.loads(output.read_text(encoding="utf-8"))
                codes = {item["code"] for item in report["findings"]}
                self.assertTrue({"redacted_sha256_mismatch", "redacted_sha256_invalid"} & codes)
                self.assertTrue({"annotated_sha256_mismatch", "annotated_sha256_invalid"} & codes)

    def test_validator_rejects_stale_capture_binding_even_when_dimensions_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            path, manifest = self._write_fixture(work)
            manifest["captureState"]["rawSha256"] = "0" * 64
            path.write_text(json.dumps(manifest), encoding="utf-8")
            output = work / "validation.json"

            result = run(VALIDATE, "--manifest", str(path), "--output", str(output))

            self.assertEqual(result.returncode, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "fail")
            self.assertTrue(any(item["code"] == "capture_binding_invalid" for item in report["findings"]))

    def test_redaction_cannot_cover_protected_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            path, manifest = self._write_fixture(work)
            manifest["protectedAreas"] = [{"bbox": {"x": 25, "y": 25, "width": 20, "height": 10}}]
            path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run(REDACT, "check", "--image", str(work / "raw" / "screen.png"),
                         "--manifest", str(path))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("protected", result.stderr.lower())

    def test_full_page_naive_height_ratio_is_not_accepted_as_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            path, manifest = self._write_fixture(work)
            manifest["captureState"]["calibration"] = {
                "pngHeight": 2000,
                "viewportHeight": 500,
                "devicePixelRatio": 4,
            }
            path.write_text(json.dumps(manifest), encoding="utf-8")
            output = work / "validation.json"

            result = run(VALIDATE, "--manifest", str(path), "--output", str(output))

            self.assertEqual(result.returncode, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "fail")

    def _complete_chain(self, work: Path) -> tuple[Path, dict]:
        path, manifest = self._write_fixture(work)
        raw = work / "raw" / "screen.png"
        redacted = work / "redacted" / "screen.png"
        annotated = work / "annotated" / "screen.png"
        redaction = run(
            REDACT,
            "draw",
            "--image",
            str(raw),
            "--manifest",
            str(path),
            "--output",
            str(redacted),
            "--provenance-output",
            str(work / "redaction-provenance.json"),
        )
        self.assertEqual(redaction.returncode, 0, redaction.stderr)
        manifest["redactedSha256"] = sha256(redacted)
        manifest["redactionProvenance"] = "redaction-provenance.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        annotation = run(
            ANNOTATE,
            "draw",
            "--image",
            str(redacted),
            "--annotations",
            str(path),
            "--output",
            str(annotated),
            "--provenance-output",
            str(work / "annotation-provenance.json"),
        )
        self.assertEqual(annotation.returncode, 0, annotation.stderr)
        manifest["annotatedSha256"] = sha256(annotated)
        manifest["annotationProvenance"] = "annotation-provenance.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return path, manifest

    def test_annotation_chain_rejects_parent_geometry_and_cursor_changes(self) -> None:
        mutations = {
            "parent": lambda manifest, work: Image.new("RGB", (320, 200), "#e8ffff").save(
                work / "redacted" / "screen.png", format="PNG"
            ),
            "bbox": lambda manifest, work: manifest["annotations"][0]["bbox"].update(x=121),
            "id": lambda manifest, work: manifest["annotations"][0].update(id="2", caption="紅框 2：儲存按鈕。"),
            "cursor": lambda manifest, work: manifest["annotations"][0].update(cursor={"x": 40, "y": 40}),
            "badge": lambda manifest, work: manifest["annotations"][0].update(badgePosition={"x": 180, "y": 20}),
        }
        for name, mutate in mutations.items():
            with self.subTest(change=name), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                path, manifest = self._complete_chain(work)
                mutate(manifest, work)
                if name == "parent":
                    manifest["redactedSha256"] = sha256(work / "redacted" / "screen.png")
                path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                output = work / "validation.json"
                result = run(VALIDATE, "--manifest", str(path), "--output", str(output))
                self.assertEqual(result.returncode, 1)
                report = json.loads(output.read_text(encoding="utf-8"))
                codes = {item["code"] for item in report["findings"]}
                expected = (
                    "annotation_provenance_parent_mismatch"
                    if name == "parent"
                    else "annotation_provenance_input_mismatch"
                )
                self.assertIn(expected, codes)

    def test_review_status_change_does_not_invalidate_annotation_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            path, manifest = self._complete_chain(work)
            manifest["reviewStatus"] = "verified"
            manifest["annotations"][0]["status"] = "checked"
            manifest["redactions"][0]["status"] = "checked"
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = work / "validation.json"
            result = run(VALIDATE, "--manifest", str(path), "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "pass")


if __name__ == "__main__":
    unittest.main()
