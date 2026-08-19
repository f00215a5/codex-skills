# ui-diagrams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立獨立 `ui-diagrams` 外掛，讓兩個 UI 操作說明書技能在明確圖表需求下，安全地檢核、安裝並使用上游 drawio-skill。

**Architecture:** 新外掛以 `$ui-diagrams` 提供條件式路由、使用者同意與交棒規則；唯讀 Python helper 回傳可測試的 JSON readiness report，避免把環境猜測散落在提示詞。環境 ready 後，wrapper 立即交棒給上游 `$drawio-skill`；只有上游 skill 負責 `.drawio` 生成、preview、review、export 與檔案修改。兩個既有 UI 技能只加入窄範圍的路由規則。

**Tech Stack:** Codex plugin manifest、Markdown Agent Skill、Python 3 standard library、`unittest`、Git、draw.io Desktop CLI、上游 Agents365-ai/drawio-skill。

## Global Constraints

- `ui-diagrams` 是獨立 plugin 與唯一 `$ui-diagrams` skill，不能在兩個 UI plugin 內複製同名 skill。
- `ui-diagrams` 不得建立、預覽、匯出或修改 `.drawio`／PNG；在 `ready` 後必須立即交棒給 `$drawio-skill`。
- 僅在使用者明確要求流程圖、關係圖、架構圖、狀態圖或泳道圖等非截圖圖表時路由；截圖紅框不路由。
- 不得未經本次任務的明確同意下載、clone、執行套件安裝或啟動 GUI。
- 拒絕、安裝失敗或環境不可用時，只停止 draw.io 圖表分支；UI 手冊主流程必須繼續。
- 預設交付同名 `.drawio` 原檔與 PNG；使用者可以覆寫格式。
- Windows 安裝使用 `winget install --id JGraph.Draw --exact --source winget`；macOS 使用 `brew install --cask drawio`；Linux 只從上游 drawio-desktop release 的 `.deb`／`.rpm` 或已設定套件管理器安裝，且需要系統核可。
- 新 plugin 起始 base version 為 `0.1.0`；`ui-ops-manual` 與 `ui-ops-manual-lite` 的 base version 升為 `0.3.0`。每一份 manifest 都由 cachebuster helper 產生新的單一 `+codex.` 時間戳 suffix。

---

### Task 1: 建立無技能控制組並記錄行為基準

**Files:**
- Create: `docs/superpowers/evidence/2026-08-19-ui-diagrams-baseline.md`

**Interfaces:**
- Consumes: 已確認的設計規格與三個無 `$ui-diagrams` skill 的獨立 agent 情境。
- Produces: 可用於確認 skill 規則是否填補真實缺口的基準紀錄。

- [ ] **Step 1: 執行三個 fresh-context 控制組情境，不提供新 skill**

使用三個互不共享上下文的 agent，逐一送出下列使用者請求，並完整保存其行動判斷與理由：

```text
A. 請用 ui-ops-manual 做登入後台的操作流程圖；這台機器沒有 draw.io，先直接幫我完成。
B. 請在操作手冊的截圖上替儲存按鈕畫紅框；不用其他圖表。
C. 請為審核流程畫關係圖。缺少工具時不要問我安裝，我不同意任何安裝；但 DOCX 操作手冊仍要完成。
```

- [ ] **Step 2: 寫入基準紀錄並列出每個不符合需求的行為**

在 evidence 檔記錄每個控制組的原始結論，並依下列欄位分類：`scenario`、`diagram_routing`、`install_consent`、`manual_continues`、`rationale`。只有實際觀察到的錯誤才列為要修正的缺口。

- [ ] **Step 3: 確認基準包含至少一個可改善缺口**

若三個控制組都已完全符合規格，停止實作並向使用者說明新 skill 無法證明必要性；否則繼續後續 tasks。

- [ ] **Step 4: Commit**

```powershell
git add docs/superpowers/evidence/2026-08-19-ui-diagrams-baseline.md
git commit -m "Record ui-diagrams baseline behavior"
```

### Task 2: 實作可測試的唯讀 readiness helper

**Files:**
- Create: `plugins/ui-diagrams/skills/ui-diagrams/scripts/check_readiness.py`
- Create: `plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py`

**Interfaces:**
- Consumes: `--home` 指定的使用者目錄、`--platform` 指定的 `win32`、`darwin` 或 `linux`，以及目前的 PATH／常見 app 路徑。
- Produces: stdout JSON：`{"status":"ready|needs-install|unavailable","missing":[...],"drawioSkill":{"state":"available|missing","path":"..."},"drawioCli":{"state":"available|missing|unavailable","command":[...],"detail":"..."}}`。
- Exported functions: `find_drawio_skill(home: Path) -> Path | None`、`resolve_drawio_command(platform: str, which: Callable[[str], str | None], exists: Callable[[Path], bool]) -> list[str] | None`、`classify_readiness(skill_path: Path | None, probe: ProbeResult | None) -> str`。

- [ ] **Step 1: Write the failing tests**

```python
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_readiness.py"

def load_module() -> object | None:
    if not SCRIPT.is_file():
        return None
    spec = importlib.util.spec_from_file_location("check_readiness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def test_reports_needs_install_when_skill_and_cli_are_missing(self) -> None:
    check_readiness = load_module()
    self.assertIsNotNone(check_readiness)
    if check_readiness is None:
        return
    self.assertTrue(hasattr(check_readiness, "inspect_environment"))
    if not hasattr(check_readiness, "inspect_environment"):
        return
    report = check_readiness.inspect_environment(
        home=self.temp_path,
        platform="win32",
        which=lambda _: None,
        exists=lambda _: False,
        probe=lambda _: None,
    )
    self.assertEqual(report["status"], "needs-install")
    self.assertEqual(report["missing"], ["drawio-skill", "drawio-desktop"])

def test_reports_ready_for_a_codex_skill_and_successful_cli_probe(self) -> None:
    check_readiness = load_module()
    self.assertIsNotNone(check_readiness)
    if check_readiness is None:
        return
    self.assertTrue(hasattr(check_readiness, "ProbeResult"))
    if not hasattr(check_readiness, "ProbeResult"):
        return
    skill = self.temp_path / ".codex/skills/drawio-skill/skills/drawio-skill/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: drawio-skill\n---\n", encoding="utf-8")
    report = check_readiness.inspect_environment(
        home=self.temp_path,
        platform="win32",
        which=lambda name: "C:/Program Files/draw.io/draw.io.exe" if name == "drawio" else None,
        exists=lambda _: False,
        probe=lambda _: check_readiness.ProbeResult(0, "29.0.0", ""),
    )
    self.assertEqual(report["status"], "ready")

def test_reports_unavailable_when_present_cli_fails_probe(self) -> None:
    check_readiness = load_module()
    self.assertIsNotNone(check_readiness)
    if check_readiness is None:
        return
    self.assertTrue(hasattr(check_readiness, "ProbeResult"))
    if not hasattr(check_readiness, "ProbeResult"):
        return
    report = check_readiness.inspect_environment(
        home=self.temp_path,
        platform="darwin",
        which=lambda name: "/Applications/draw.io.app/Contents/MacOS/draw.io" if name == "drawio" else None,
        exists=lambda _: False,
        probe=lambda _: check_readiness.ProbeResult(1, "", "Electron failed"),
    )
    self.assertEqual(report["status"], "unavailable")
    self.assertEqual(report["drawioCli"]["state"], "unavailable")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py
```

Expected: FAIL at `assertIsNotNone(check_readiness)` because `check_readiness.py` does not exist; it must not fail as an import error.

- [ ] **Step 3: Implement the minimal helper**

Implement only the declared functions plus a `main()` that parses `--home` and `--platform`, probes the resolved draw.io command with `--version` once with a 15-second timeout, and serializes the report as UTF-8 JSON. Search paths must be:

```python
SKILL_RELATIVE_PATHS = (
    Path(".codex/skills/drawio-skill/skills/drawio-skill/SKILL.md"),
    Path(".agents/skills/drawio-skill/skills/drawio-skill/SKILL.md"),
)
```

Resolve CLI in this order: `drawio`, `draw.io`, Windows `%ProgramFiles%/draw.io/draw.io.exe`, Windows `%ProgramFiles(x86)%/draw.io/draw.io.exe`, macOS `/Applications/draw.io.app/Contents/MacOS/draw.io`. A missing item yields `needs-install`; a discovered command with timeout, non-zero exit, or no usable process result yields `unavailable` and does not retry.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```powershell
python plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py
```

Expected: all three readiness classifications PASS without downloading or installing software.

- [ ] **Step 5: Commit**

```powershell
git add plugins/ui-diagrams/skills/ui-diagrams/scripts/check_readiness.py plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py
git commit -m "Add draw.io readiness checks"
```

### Task 3: 建立 ui-diagrams plugin 與安全安裝／交付 skill

**Files:**
- Create: `plugins/ui-diagrams/.codex-plugin/plugin.json`
- Create: `plugins/ui-diagrams/skills/ui-diagrams/SKILL.md`
- Create: `plugins/ui-diagrams/skills/ui-diagrams/agents/openai.yaml`
- Create: `plugins/ui-diagrams/skills/ui-diagrams/references/dependency-and-install-policy.md`
- Create: `plugins/ui-diagrams/skills/ui-diagrams/tests/skill_contract.tests.py`
- Modify: `.agents/plugins/marketplace.json`

**Interfaces:**
- Consumes: `check_readiness.py` JSON and an explicit current-task user decision of `approve` or `decline`.
- Produces: a draw.io execution handoff to upstream `$drawio-skill`, or a chat-only `declined`／`unavailable` report that preserves the parent manual workflow.

- [ ] **Step 1: Write failing plugin/skill contract tests**

```python
def test_plugin_exposes_the_only_ui_diagrams_skill(self) -> None:
    manifest_path = PLUGIN_ROOT / ".codex-plugin/plugin.json"
    skill_path = PLUGIN_ROOT / "skills/ui-diagrams/SKILL.md"
    self.assertTrue(manifest_path.is_file())
    self.assertTrue(skill_path.is_file())
    if not manifest_path.is_file() or not skill_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill = skill_path.read_text(encoding="utf-8")
    self.assertEqual(manifest["name"], "ui-diagrams")
    self.assertRegex(skill, r"(?m)^name: ui-diagrams$")
    self.assertIn("$drawio-skill", skill)

def test_skill_requires_consent_and_preserves_the_manual_when_diagrams_stop(self) -> None:
    self.assertTrue(SKILL_MD.is_file())
    self.assertTrue(POLICY_MD.is_file())
    if not SKILL_MD.is_file() or not POLICY_MD.is_file():
        return
    guidance = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SKILL_MD, POLICY_MD)
    )
    self.assertIn("明確同意", guidance)
    self.assertIn("只停止圖表分支", guidance)
    self.assertIn("立即交棒給 $drawio-skill", guidance)
    self.assertIn("不自行建立、預覽、匯出或修改", guidance)
    self.assertIn(".drawio", guidance)
    self.assertIn("PNG", guidance)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python plugins/ui-diagrams/skills/ui-diagrams/tests/skill_contract.tests.py
```

Expected: FAIL at the file-existence assertions because the plugin, skill and policy files do not exist.

- [ ] **Step 3: Implement the plugin and skill**

Create a valid plugin manifest with base version `0.1.0`, one `skills` root, and interface prompts that call `$ui-diagrams`. Append a marketplace entry with source `./plugins/ui-diagrams`, `AVAILABLE`, `ON_INSTALL`, and category `Productivity`.

Write concise skill instructions with the following observable recipe:

1. Confirm the request is a non-screenshot diagram; otherwise return control to the caller without invoking draw.io.
2. Run `check_readiness.py` and classify `ready`／`needs-install`／`unavailable`.
3. For `needs-install`, present missing components, the exact platform command, the upstream source URL, install scope, and the question `是否同意為本次任務安裝？`; do not execute an installer until an affirmative answer.
4. On approval, clone `https://github.com/Agents365-ai/drawio-skill.git` to the current user's `.codex/skills/drawio-skill` when missing; execute only the platform-specific draw.io installer supported by the policy; re-run readiness. Explain that a new Codex task provides normal discovery after installation.
5. For `decline` or `unavailable`, report the status only in chat and explicitly return the caller to the continuing UI manual workflow.
6. For `ready`, immediately hand off to `$drawio-skill` without generating, previewing, exporting, or modifying any diagram file. The downstream delivery default is `diagram.drawio` plus `diagram.drawio.png`, with an explicit user override allowed before generation.

The policy reference must include the exact commands below and state that each external action still requires the runtime's permission mechanism:

```text
Windows: winget install --id JGraph.Draw --exact --source winget --accept-package-agreements --accept-source-agreements
macOS: brew install --cask drawio
Linux Debian: download the selected official .deb from https://github.com/jgraph/drawio-desktop/releases as ./drawio-release.deb and run sudo apt-get install -y ./drawio-release.deb
Linux RPM: download the selected official .rpm from the same release as ./drawio-release.rpm and run sudo dnf install -y ./drawio-release.rpm
```

- [ ] **Step 4: Run focused tests and structural validation**

Run:

```powershell
python plugins/ui-diagrams/skills/ui-diagrams/tests/skill_contract.tests.py
python C:/Users/derick.chang/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/ui-diagrams/skills/ui-diagrams
python C:/Users/derick.chang/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/ui-diagrams
```

Expected: contract tests and both validators PASS.

- [ ] **Step 5: Commit**

```powershell
git add .agents/plugins/marketplace.json plugins/ui-diagrams
git commit -m "Add ui-diagrams plugin"
```

### Task 4: 將兩個 UI 手冊技能路由到共用圖表 skill

**Files:**
- Modify: `plugins/ui-ops-manual/skills/ui-guide/SKILL.md`
- Modify: `plugins/ui-ops-manual-lite/skills/ui-guide-lite/SKILL.md`
- Create: `plugins/ui-ops-manual/skills/ui-guide/tests/diagram_routing.tests.py`
- Create: `plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/diagram_routing.tests.py`

**Interfaces:**
- Consumes: 使用者需求中是否明確包含非截圖圖表意圖。
- Produces: 明確意圖時呼叫 `$ui-diagrams`；純截圖／紅框需求時繼續原本操作說明書流程。

- [ ] **Step 1: Write failing routing tests**

Full and lite test files use相同的合同：

```python
def test_routes_explicit_non_screenshot_diagrams_to_the_shared_skill(self) -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    self.assertIn("$ui-diagrams", skill_text)
    self.assertIn("流程圖、關係圖、架構圖、狀態圖或泳道圖", skill_text)
    self.assertIn("明確要求", skill_text)

def test_keeps_screenshot_annotations_in_the_ui_manual_workflow(self) -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    self.assertIn("截圖、紅框、游標", skill_text)
    self.assertIn("不呼叫 $ui-diagrams", skill_text)
```

- [ ] **Step 2: Run routing tests to verify they fail**

Run:

```powershell
python plugins/ui-ops-manual/skills/ui-guide/tests/diagram_routing.tests.py
python plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/diagram_routing.tests.py
```

Expected: both FAIL because neither guide currently names `$ui-diagrams`.

- [ ] **Step 3: Add the minimal conditional routing sections**

Add one `## 操作圖表（條件式）` section to each core skill after screenshot/annotation guidance. It must state: call `$ui-diagrams` only for explicit flow/relationship/architecture/state/swimlane diagrams; do not call it for screenshots, red boxes or cursor annotations; if the diagram skill reports decline/unavailable, continue the manual without the diagram and report that limitation in chat rather than DOCX.

- [ ] **Step 4: Run routing and existing regression tests**

Run:

```powershell
python plugins/ui-ops-manual/skills/ui-guide/tests/diagram_routing.tests.py
python plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/diagram_routing.tests.py
python plugins/ui-ops-manual/skills/ui-guide/tests/core_skill_naming.tests.py
python plugins/ui-ops-manual/skills/ui-guide/tests/conversation_reporting.tests.py
python plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/core_skill_naming.tests.py
python plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/conversation_reporting.tests.py
```

Expected: all PASS; no core skill name or chat-only runtime reporting regression.

- [ ] **Step 5: Commit**

```powershell
git add plugins/ui-ops-manual/skills/ui-guide plugins/ui-ops-manual-lite/skills/ui-guide-lite
git commit -m "Route UI manual diagrams through ui-diagrams"
```

### Task 5: 版本、跨外掛驗證與 skill 行為驗收

**Files:**
- Modify: `plugins/ui-ops-manual/.codex-plugin/plugin.json`
- Modify: `plugins/ui-ops-manual-lite/.codex-plugin/plugin.json`
- Modify: `plugins/ui-diagrams/.codex-plugin/plugin.json`

**Interfaces:**
- Consumes: 完成的三個 plugin roots。
- Produces: 可被 Codex 快取辨識的三個版本 manifest 與完整驗證證據。

- [ ] **Step 1: Write failing version/marketplace contract test**

Add `plugins/ui-diagrams/skills/ui-diagrams/tests/marketplace_contract.tests.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python plugins/ui-diagrams/skills/ui-diagrams/tests/marketplace_contract.tests.py
```

Expected: FAIL at the existing UI plugin version assertions because their base versions are still `0.2.0`.

- [ ] **Step 3: Set base versions and run the cachebuster helper**

Set manifests to raw base values first, then run once per plugin:

```powershell
python C:/Users/derick.chang/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py plugins/ui-diagrams
python C:/Users/derick.chang/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py plugins/ui-ops-manual
python C:/Users/derick.chang/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py plugins/ui-ops-manual-lite
```

- [ ] **Step 4: Run all regression tests and validators**

Run the entire existing full and lite test suites, then run the new `ui-diagrams` tests. Run `quick_validate.py` for all three skills and `validate_plugin.py` for all three plugins with `PYTHONUTF8=1`, then run `git diff --check`.

Expected: every test and validator PASS; no whitespace errors.

- [ ] **Step 5: Forward-test the completed skill and commit**

Run the three Task 1 scenarios with `$ui-diagrams` available. Verify: A asks for consent before any install; B stays in screenshot workflow; C reports only diagram skip while continuing the manual; every ready scenario ends by handing work to `$drawio-skill` without the wrapper generating or exporting files. Record observed outcomes in `docs/superpowers/evidence/2026-08-19-ui-diagrams-forward-test.md`.

```powershell
git add docs/superpowers/evidence/2026-08-19-ui-diagrams-forward-test.md plugins/ui-diagrams/.codex-plugin/plugin.json plugins/ui-ops-manual/.codex-plugin/plugin.json plugins/ui-ops-manual-lite/.codex-plugin/plugin.json
git commit -m "Release ui-diagrams integration"
```

### Task 6: 發布分支與草稿 PR

**Files:**
- Modify: none beyond prior tasks.

**Interfaces:**
- Consumes: clean branch, committed implementation and passing validation evidence.
- Produces: pushed `agent/add-ui-diagrams-plugin` branch and a draft PR targeting current `main`.

- [ ] **Step 1: Inspect publication scope**

```powershell
git status -sb
git diff origin/main...HEAD --check
git log --oneline origin/main..HEAD
gh auth status
```

Expected: only the six task deliverables appear and the active GitHub account is `f00215a5`.

- [ ] **Step 2: Push branch and create draft PR**

```powershell
git push -u origin agent/add-ui-diagrams-plugin
gh pr create --repo f00215a5/codex-skills --base main --head agent/add-ui-diagrams-plugin --draft --title "Add shared UI diagrams plugin"
```

Expected: draft PR URL is returned and contains the commits created by Tasks 1–5.

- [ ] **Step 3: Verify remote state**

```powershell
gh pr view --repo f00215a5/codex-skills --json number,state,isDraft,baseRefName,headRefName,headRefOid,url
git status --short
```

Expected: PR is OPEN, draft, targets `main`, and local worktree is clean.
