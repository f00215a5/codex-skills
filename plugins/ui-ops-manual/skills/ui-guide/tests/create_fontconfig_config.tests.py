from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "create_fontconfig_config.py"
PROBE_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "create_cjk_probe.py"


class CreateFontconfigConfigTests(unittest.TestCase):
    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_creates_isolated_config_for_explicit_font_directories(self) -> None:
        """A per-job config must expose only supplied fonts and a job-local cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            font_dir_one = workspace / "fonts-one"
            font_dir_two = workspace / "fonts-two"
            cache_dir = workspace / "font-cache"
            output_path = workspace / "fontconfig-cjk.xml"
            font_dir_one.mkdir()
            font_dir_two.mkdir()

            result = self.run_tool(
                "--font-dir",
                str(font_dir_one),
                "--font-dir",
                str(font_dir_two),
                "--cache-dir",
                str(cache_dir),
                "--output",
                str(output_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            config = ET.parse(output_path).getroot()
            self.assertEqual(
                [node.text for node in config.findall("dir")],
                [str(font_dir_one.resolve()), str(font_dir_two.resolve())],
            )
            self.assertEqual(
                [node.text for node in config.findall("cachedir")],
                [str(cache_dir.resolve())],
            )
            self.assertTrue(cache_dir.is_dir())

    def test_rejects_a_missing_font_directory(self) -> None:
        """A typo must fail before a renderer can silently use an unrelated fallback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            output_path = workspace / "fontconfig-cjk.xml"

            result = self.run_tool(
                "--font-dir",
                str(workspace / "not-a-font-directory"),
                "--cache-dir",
                str(workspace / "font-cache"),
                "--output",
                str(output_path),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not exist or is not a directory", result.stderr)
            self.assertFalse(output_path.exists())


class CreateCjkProbeTests(unittest.TestCase):
    def test_creates_a_zh_tw_probe_with_the_requested_east_asian_font(self) -> None:
        """The renderer probe must contain live CJK text, not a screenshot substitute."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "traditional-chinese-probe.docx"
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROBE_SCRIPT_PATH),
                    "--font-name",
                    "PingFang TC",
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with ZipFile(output_path) as document:
                document_xml = document.read("word/document.xml")

            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            root = ET.fromstring(document_xml)
            fonts = root.find(".//w:rFonts", namespaces)
            language = root.find(".//w:lang", namespaces)
            text = "".join(node.text or "" for node in root.findall(".//w:t", namespaces))
            self.assertIsNotNone(fonts)
            self.assertEqual(
                fonts.attrib["{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia"],
                "PingFang TC",
            )
            self.assertIsNotNone(language)
            self.assertEqual(
                language.attrib["{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia"],
                "zh-TW",
            )
            self.assertIn("繁體中文", text)
            self.assertIn("臺灣", text)
            self.assertIn("龜麵", text)


if __name__ == "__main__":
    unittest.main()
