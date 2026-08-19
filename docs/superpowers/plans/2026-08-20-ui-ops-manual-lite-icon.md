# UI Operations Manual Lite Icon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the UI Operations Manual Lite icon with the approved compact checklist design and make the updated marketplace plugin ready for local Codex validation.

**Architecture:** Keep the plugin's existing SVG-first icon contract: the small and large SVGs remain under `skills/ui-guide-lite/assets/`, and the manifest continues to point to those files. A focused contract test will verify the three manifest paths resolve, the SVGs declare the compact-guide semantics, and the former full-window/red-frame motif is absent.

**Tech Stack:** SVG, JSON, Python `unittest`, Codex plugin validation scripts, Codex CLI.

## Global Constraints

- Work only on branch `feature/ui-ops-manual-lite-icon`; do not alter `ui-ops-manual`, `ui-diagrams`, or marketplace ordering.
- Keep plugin ID `ui-ops-manual-lite`, skill name `ui-guide-lite`, and existing marketplace source path unchanged.
- Preserve the existing `0.2.0` base version; update only its single `+codex.<UTC timestamp>` cachebuster once after source edits are final.
- Retain editable SVG assets and write PNG preview counterparts; do not use a raster-only or text-bearing logo.
- Validate embedded skill structure, plugin manifest, and icon paths before reinstalling from the already configured `codex-skills` marketplace.

---

### Task 1: Add the compact checklist icon assets and their contract

**Files:**
- Modify: `plugins/ui-ops-manual-lite/skills/ui-guide-lite/assets/ui-ops-manual-lite-small.svg`
- Modify: `plugins/ui-ops-manual-lite/skills/ui-guide-lite/assets/ui-ops-manual-lite-large.svg`
- Create: `plugins/ui-ops-manual-lite/skills/ui-guide-lite/assets/ui-ops-manual-lite-small.png`
- Create: `plugins/ui-ops-manual-lite/skills/ui-guide-lite/assets/ui-ops-manual-lite-large.png`
- Create: `plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/icon_assets.tests.py`

**Interfaces:**
- Consumes: manifest interface icon paths `./skills/ui-guide-lite/assets/ui-ops-manual-lite-small.svg` and `./skills/ui-guide-lite/assets/ui-ops-manual-lite-large.svg`.
- Produces: matching SVG and PNG assets where the small icon uses a `0 0 96 96` view box and the large icon uses a `0 0 512 512` view box.

- [x] **Step 1: Write the failing icon contract test**

```python
class LiteIconAssetTests(unittest.TestCase):
    def test_manifest_icon_paths_exist_and_use_compact_guide_artwork(self) -> None:
        interface = load_manifest()["interface"]
        for key in ("composerIcon", "logo", "logoDark"):
            self.assertTrue((PLUGIN_ROOT / interface[key].removeprefix("./")).is_file())
        for svg_name, view_box in (("ui-ops-manual-lite-small.svg", "0 0 96 96"),
                                   ("ui-ops-manual-lite-large.svg", "0 0 512 512")):
            svg = (ASSET_ROOT / svg_name).read_text(encoding="utf-8")
            self.assertIn(f'viewBox="{view_box}"', svg)
            self.assertIn("compact operation guide", svg)
            self.assertNotIn("#D64545", svg)
```

- [x] **Step 2: Run the new test to verify it fails**

Run:

```powershell
python -X utf8 plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/icon_assets.tests.py
```

Expected: FAIL because the current SVG descriptions do not contain `compact operation guide` and retain the red-frame colour.

- [x] **Step 3: Replace the SVGs and create matching PNG previews**

Use the approved design in both SVGs: an indigo-teal rounded background, a white folded single-page guide, three teal checked lines, and a mint speed spark. Keep the large SVG at 512 × 512 and simplify the same visual language for the 96 × 96 small SVG. Rasterize the SVGs to identically named PNG files using local headless Chrome; retain SVG as the manifest-referenced source.

- [x] **Step 4: Run the icon contract test to verify it passes**

Run:

```powershell
python -X utf8 plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/icon_assets.tests.py
```

Expected: PASS; all three manifest paths exist, both SVG view boxes are correct, compact-guide language is present, and no old red-frame colour remains.

- [x] **Step 5: Commit the asset and test change**

```powershell
git add plugins/ui-ops-manual-lite/skills/ui-guide-lite/assets plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/icon_assets.tests.py
git commit -m "feat: refresh lite manual icon"
```

### Task 2: Version, validate, reinstall, and record the delivered plugin

**Files:**
- Modify: `plugins/ui-ops-manual-lite/.codex-plugin/plugin.json`
- Modify: `docs/superpowers/plans/2026-08-20-ui-ops-manual-lite-icon.md`

**Interfaces:**
- Consumes: the existing `codex-skills` marketplace entry, which still maps `ui-ops-manual-lite` to `./plugins/ui-ops-manual-lite`.
- Produces: a single cachebuster form `0.2.0+codex.<UTC timestamp>` and a locally installed `ui-ops-manual-lite@codex-skills` matching the branch source.

- [x] **Step 1: Confirm the source-only change has not changed plugin identity or icon path contracts**

Run:

```powershell
python -X utf8 plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/core_skill_naming.tests.py
```

Expected: PASS; plugin ID stays `ui-ops-manual-lite`, default prompts retain `$ui-guide-lite`, and all three icon fields remain under `./skills/ui-guide-lite/assets/`.

- [x] **Step 2: Apply one cachebuster update after all source edits are final**

Run:

```powershell
python -X utf8 C:/Users/derick.chang/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py D:/codex-skills/plugins/ui-ops-manual-lite
```

Expected: only the `+codex.<timestamp>` suffix changes; the `0.2.0` base version is preserved.

- [x] **Step 3: Validate the embedded skill, plugin, and icon contract**

Run:

```powershell
python -X utf8 C:/Users/derick.chang/.codex/skills/.system/skill-creator/scripts/quick_validate.py D:/codex-skills/plugins/ui-ops-manual-lite/skills/ui-guide-lite
python -X utf8 C:/Users/derick.chang/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py D:/codex-skills/plugins/ui-ops-manual-lite
python -X utf8 plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/icon_assets.tests.py
git diff --check origin/main..HEAD
```

Expected: every command exits 0; no marketplace file is changed.

- [x] **Step 4: Reinstall the updated plugin from the configured marketplace**

Run:

```powershell
codex plugin add ui-ops-manual-lite@codex-skills
codex plugin list
```

Expected: `ui-ops-manual-lite` is enabled and reports the cachebusted version produced in Step 2. Ask the user to test it from a new task so Codex reloads the skill metadata.

- [x] **Step 5: Mark completed plan tasks and commit delivery metadata**

```powershell
git add plugins/ui-ops-manual-lite/.codex-plugin/plugin.json docs/superpowers/plans/2026-08-20-ui-ops-manual-lite-icon.md
git commit -m "chore: release lite manual icon update"
```

## Execution Record

- The icon contract was first observed failing because the former red-frame SVGs and PNG counterparts did not exist; after the approved assets were added it passed (2 tests).
- `quick_validate.py`, `validate_plugin.py`, and the existing core skill naming contract all passed.
- The installed plugin is `ui-ops-manual-lite@codex-skills` version `0.2.0+codex.20260819161307` at `C:\Users\derick.chang\.codex\plugins\cache\codex-skills\ui-ops-manual-lite\0.2.0+codex.20260819161307`.
