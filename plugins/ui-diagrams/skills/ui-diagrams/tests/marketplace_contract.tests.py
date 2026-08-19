"""Cross-plugin marketplace and release-version contract tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]


def load_version(plugin_name: str) -> str:
    manifest_path = REPO_ROOT / "plugins" / plugin_name / ".codex-plugin/plugin.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))["version"]


class MarketplaceContractTests(unittest.TestCase):
    def test_marketplace_exposes_all_three_ui_plugins_with_expected_base_versions(self) -> None:
        manifest_path = REPO_ROOT / "plugins/ui-diagrams/.codex-plugin/plugin.json"
        self.assertTrue(manifest_path.is_file())
        if not manifest_path.is_file():
            return
        marketplace = json.loads((REPO_ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        names = {plugin["name"] for plugin in marketplace["plugins"]}
        self.assertTrue({"ui-diagrams", "ui-ops-manual", "ui-ops-manual-lite"} <= names)
        self.assertTrue(load_version("ui-diagrams").startswith("0.1.0+codex."))
        self.assertTrue(load_version("ui-ops-manual").startswith("0.3.0+codex."))
        self.assertTrue(load_version("ui-ops-manual-lite").startswith("0.3.0+codex."))


if __name__ == "__main__":
    unittest.main()
