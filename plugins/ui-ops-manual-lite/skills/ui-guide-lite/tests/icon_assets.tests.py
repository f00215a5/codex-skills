"""Contract tests for UI Operations Manual Lite icon assets."""

from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
ASSET_ROOT = SKILL_ROOT / "assets"


def load_manifest() -> dict:
    return json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )


class LiteIconAssetTests(unittest.TestCase):
    def test_manifest_paths_resolve_to_compact_guide_svg_artwork(self) -> None:
        interface = load_manifest()["interface"]
        expected_paths = {
            "composerIcon": "./skills/ui-guide-lite/assets/ui-ops-manual-lite-small.svg",
            "logo": "./skills/ui-guide-lite/assets/ui-ops-manual-lite-large.svg",
            "logoDark": "./skills/ui-guide-lite/assets/ui-ops-manual-lite-large.svg",
        }
        self.assertEqual(
            {key: interface[key] for key in expected_paths}, expected_paths
        )
        for path in expected_paths.values():
            self.assertTrue((PLUGIN_ROOT / path.removeprefix("./")).is_file())

        for svg_name, view_box in (
            ("ui-ops-manual-lite-small.svg", "0 0 96 96"),
            ("ui-ops-manual-lite-large.svg", "0 0 512 512"),
        ):
            svg = (ASSET_ROOT / svg_name).read_text(encoding="utf-8")
            self.assertIn(f'viewBox="{view_box}"', svg)
            self.assertIn("compact operation guide", svg)
            self.assertNotIn("#D64545", svg)

    def test_png_previews_match_the_svg_icon_sizes(self) -> None:
        for png_name, expected_size in (
            ("ui-ops-manual-lite-small.png", (96, 96)),
            ("ui-ops-manual-lite-large.png", (512, 512)),
        ):
            png = ASSET_ROOT / png_name
            header = png.read_bytes()[:24]
            self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", header[16:24]), expected_size)


if __name__ == "__main__":
    unittest.main()
