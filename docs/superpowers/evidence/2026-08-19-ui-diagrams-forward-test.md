# ui-diagrams forward behavior evidence

Date: 2026-08-19
Plan: [ui-diagrams implementation plan](../plans/2026-08-19-ui-diagrams.md)

## Controls

This is a controlled, no-install forward test. `$ui-diagrams` is available from
the completed local plugin source. No clone, download, package-manager,
installer, GUI launch, diagram generation, preview, export, or artifact write
was requested or performed. The unavailable path uses the committed
`empty-home` fixture; the ready path uses the existing unit test's injected
Codex-skill path and successful CLI-probe result, rather than an installation.

Commands run with UTF-8 mode:

```powershell
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/scripts/check_readiness.py --home plugins/ui-diagrams/skills/ui-diagrams/tests/fixtures/empty-home --platform win32
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py CheckReadinessTests.test_reports_ready_for_a_codex_skill_and_successful_cli_probe
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/skill_contract.tests.py
```

The unavailable control reported `status: needs-install` and
`missing: ["drawio-skill"]`; the injected-ready test and the handoff contract
both passed. The local draw.io version probe is read-only and no follow-up
installer was invoked.

## Scenarios and observed routing

### A — non-screenshot flowchart with dependency missing

Prompt:

```text
請為登入後台畫操作流程圖。目前沒有 draw.io。
```

Observed controlled route: this is an explicit non-screenshot diagram, so the
parent calls `$ui-diagrams`. The controlled readiness result is `needs-install`.
Before any external action, the skill presents the missing component, platform
command, upstream URL, and install scope, then asks exactly `是否同意為本次任務安裝？`.
The control grants no consent and no runtime approval, so no clone or installer
is executed. This satisfies the required consent gate before any install.

### B — screenshot red-box annotation

Prompt:

```text
請在操作手冊的截圖上替儲存按鈕畫紅框；不用其他圖表。
```

Observed controlled route: this remains the parent UI-manual screenshot and
annotation workflow. The parent routing contracts pass for screenshots, red
boxes, and cursor annotations not to call `$ui-diagrams`; consequently no
readiness check, consent request, or draw.io action occurs.

### C — diagram declined while the DOCX manual continues

Prompt:

```text
請為審核流程畫關係圖。缺少工具時不要問我安裝，我不同意任何安裝；但 DOCX 操作手冊仍要完成。
```

Observed controlled route: with the same `needs-install` control and an
explicit refusal, no consent question, clone, or installer is attempted. The
skill reports the limitation in chat, returns to the caller's continuing manual
workflow, and **only the diagram branch stops**. The DOCX manual remains in
scope and does not receive a runtime-warning entry.

### Ready handoff boundary

The injected-ready control returns `ready`. The completed skill's next and
terminal wrapper action is `立即交棒給 $drawio-skill`. It does not generate,
preview, export, or modify `.drawio` or PNG files; those actions and any
delivery choice belong solely to the downstream skill. No wrapper artifact was
created by this test.

## Result

All four assertions hold under controlled, no-install conditions: A requires
current-task consent before installation, B stays in the screenshot workflow,
C stops only the diagram while the manual continues, and a ready result hands
off without wrapper generation or export.
