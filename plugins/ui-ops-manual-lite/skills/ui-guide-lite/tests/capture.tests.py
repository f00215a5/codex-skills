from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "capture.py"
sys.path.insert(0, str(ROOT / "scripts"))
from evidence import capture_binding_errors  # noqa: E402


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class CaptureCanonicalizeTests(unittest.TestCase):
    def test_preserves_non_png_bytes_and_marks_missing_capture_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "capture.png"  # Deliberately has a misleading suffix.
            Image.new("RGB", (9, 6), (10, 20, 30)).save(source, format="JPEG", quality=86)
            original_bytes = source.read_bytes()
            raw = work / "raw.capture"
            canonical = work / "canonical.png"
            provenance_path = work / "capture.json"

            result = run(
                "canonicalize",
                "--input",
                str(source),
                "--raw-output",
                str(raw),
                "--canonical-output",
                str(canonical),
                "--provenance-output",
                str(provenance_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(raw.read_bytes(), original_bytes)
            with Image.open(canonical) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (9, 6))
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            state = provenance["captureState"]
            self.assertEqual(provenance["originalMime"], "image/jpeg")
            self.assertEqual(provenance["pixelEquality"], "verified")
            self.assertEqual(state["metadataStatus"], "incomplete")
            self.assertIn("viewportCssSize", state["missingMetadata"])
            self.assertIn("scroll", state["missingMetadata"])
            self.assertIn("captureKind", state["missingMetadata"])
            self.assertNotIn("viewportCssSize", state)
            self.assertNotIn("scroll", state)
            self.assertNotIn("captureKind", provenance)
            gate_errors = capture_binding_errors(
                {
                    "sourceSha256": provenance["canonicalSha256"],
                    "originalImageSize": provenance["canonicalImageSize"],
                    "captureState": state,
                },
                (9, 6),
                require=True,
            )
            self.assertTrue(any("viewportCssSize" in error for error in gate_errors))
            self.assertTrue(any("scroll" in error for error in gate_errors))

    def test_complete_metadata_is_retained_without_inventing_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "capture.jpg"
            Image.new("RGB", (20, 12), "white").save(source, format="JPEG")
            state_path = work / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "id": "detail-01",
                        "viewportCssSize": {"width": 800, "height": 600},
                        "scroll": {"x": 12, "y": 48},
                        "calibration": {
                            "mode": "known-control",
                            "pngSize": {"width": 20, "height": 12},
                            "viewportCssSize": {"width": 800, "height": 600},
                            "knownControl": {
                                "bbox": {"x": 2, "y": 2, "width": 5, "height": 4}
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            provenance_path = work / "capture.json"
            result = run(
                "canonicalize",
                "--input",
                str(source),
                "--raw-output",
                str(work / "raw.capture"),
                "--canonical-output",
                str(work / "canonical.png"),
                "--provenance-output",
                str(provenance_path),
                "--capture-kind",
                "detail",
                "--capture-state",
                str(state_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            self.assertEqual(provenance["captureKind"], "detail")
            self.assertEqual(provenance["captureState"]["metadataStatus"], "complete")
            self.assertEqual(provenance["captureState"]["viewportCssSize"], {"width": 800, "height": 600})
            self.assertEqual(provenance["captureState"]["scroll"], {"x": 12, "y": 48})

    def test_invalid_metadata_and_aliases_leave_no_partial_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "capture.png"
            Image.new("RGB", (10, 8), "white").save(source)
            state_path = work / "invalid-state.json"
            state_path.write_text(
                json.dumps({"viewportCssSize": {"width": 0, "height": 8}}),
                encoding="utf-8",
            )
            raw = work / "raw.capture"
            canonical = work / "canonical.png"
            provenance = work / "capture.json"
            invalid = run(
                "canonicalize",
                "--input",
                str(source),
                "--raw-output",
                str(raw),
                "--canonical-output",
                str(canonical),
                "--provenance-output",
                str(provenance),
                "--capture-state",
                str(state_path),
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertFalse(raw.exists())
            self.assertFalse(canonical.exists())
            self.assertFalse(provenance.exists())

            alias = run(
                "canonicalize",
                "--input",
                str(source),
                "--raw-output",
                str(source),
                "--canonical-output",
                str(work / "alias-canonical.png"),
                "--provenance-output",
                str(work / "alias.json"),
            )
            self.assertEqual(alias.returncode, 2)
            self.assertFalse((work / "alias-canonical.png").exists())
            self.assertFalse((work / "alias.json").exists())


if __name__ == "__main__":
    unittest.main()
