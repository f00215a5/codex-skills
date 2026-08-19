# ui-diagrams forward behavior evidence

Date: 2026-08-19
Plan: [ui-diagrams implementation plan](../plans/2026-08-19-ui-diagrams.md)

## Reproducible, no-install controls

This correction deliberately does **not** invoke the normal readiness CLI for
the missing-desktop scenario. That CLI may discover a developer's local
draw.io installation, so it cannot prove a missing-desktop result.

The tracked empty fixture is
`plugins/ui-diagrams/skills/ui-diagrams/tests/fixtures/no-dependencies-home/.gitkeep`.
It represents a Codex home with no `drawio-skill`. The forward control calls
the real `inspect_environment` function directly, with the following injected
inputs:

| control | `which` | `exists` / Program Files | `probe` | expected result |
| --- | --- | --- | --- | --- |
| A/C missing both | always `None` | always `False`; `ProgramFiles` and `ProgramFiles(x86)` are patched to `X:/controlled-*` | fails the test if called | `needs-install`; `missing` is exactly `['drawio-skill', 'drawio-desktop']`; CLI is `missing` with `command: []` |
| comparison: missing skill only | `drawio` returns `X:/controlled-drawio/draw.io.exe` | fails the test if searched | injected successful `ProbeResult(0, '29.0.0', '')` | `needs-install`; `missing` is exactly `['drawio-skill']`; CLI is `available` |
| ready handoff | injected controlled drawio path | no Program Files search | injected successful `ProbeResult(0, '29.0.0', '')` plus the tracked `ready-home` skill fixture | `ready` |

The first control also asserts that the resolver tried only `drawio` and
`draw.io`, inspected only the two `X:/controlled-*` paths, and never called
the probe. It therefore cannot read PATH, `C:\Program Files`, or execute the
locally installed draw.io binary. The comparison control is intentionally not
used for A or C; it exists to distinguish *missing skill only* from *missing
skill plus desktop*.

Exact replay commands, all run in UTF-8 mode:

```powershell
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py CheckReadinessTests.test_forward_control_proves_both_dependencies_missing_without_host_discovery
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py CheckReadinessTests.test_forward_control_distinguishes_a_missing_skill_from_missing_both_dependencies
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py CheckReadinessTests.test_reports_ready_for_a_codex_skill_and_successful_cli_probe
python -X utf8 plugins/ui-ops-manual/skills/ui-guide/tests/diagram_routing.tests.py
python -X utf8 plugins/ui-ops-manual-lite/skills/ui-guide-lite/tests/diagram_routing.tests.py
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/skill_contract.tests.py
```

All six commands passed. The controls use only local tracked fixtures, injected
functions, and read-only in-process inspection. No clone, download,
package-manager, installer, GUI launch, artifact generation, preview, export,
or system configuration change occurred. System draw.io was neither disabled
nor uninstalled.

## Forward scenarios

The following are the exact scenario inputs reviewed against the passing
controls and parent/skill contracts above. They describe the observed branch
selected by those controls; no installer branch was executed.

### A — non-screenshot flowchart, both dependencies missing

```text
請為登入後台畫操作流程圖。目前沒有 draw.io。
```

The explicit flowchart routes from the parent to `$ui-diagrams`. The A/C
missing-both control returns `needs-install` with both components listed. The
skill's tested install policy requires disclosure of those components, the
platform command, source URL, and scope, then asks exactly
`是否同意為本次任務安裝？`. The control supplies neither current-task consent
nor runtime approval, so no clone or installer occurs. This is an approval gate
before any external installation action.

### B — screenshot red-box annotation

```text
請在操作手冊的截圖上替儲存按鈕畫紅框；不用其他圖表。
```

Both parent routing contract suites select the existing screenshot/red-box/
cursor workflow and explicitly do not call `$ui-diagrams`. No readiness
control, consent prompt, or draw.io action is reached.

### C — relation diagram declined while the DOCX manual continues

```text
請為審核流程畫關係圖。缺少工具時不要問我安裝，我不同意任何安裝；但 DOCX 操作手冊仍要完成。
```

The same A/C missing-both control is used, not the missing-skill-only
comparison. The explicit refusal means the skill reports the limitation in
chat and stops **only the diagram branch**; the parent contract keeps the DOCX
manual workflow continuing and excludes runtime-warning content from the DOCX.
No consent question, clone, or installer is attempted after the refusal.

### Ready handoff boundary

The injected-ready control returns `ready`. The skill contract confirms the
wrapper's next action is `立即交棒給 $drawio-skill`; the wrapper does not
generate, preview, export, or modify `.drawio` or PNG files. No wrapper
artifact was created by this test; downstream owns any generation and delivery
decision.

## Result

The forward test has a replayable no-desktop control independent of the local
draw.io installation, distinguishes it from a controlled missing-skill-only
state, and verifies A/B/C plus the ready handoff boundary without external
installation or artifact operations.
