# ui-diagrams forward behavior acceptance

Date: 2026-08-19
Plan: [ui-diagrams implementation plan](../plans/2026-08-19-ui-diagrams.md)

## Raw, durable acceptance records

The acceptance records are four separate, committed transcripts plus a
[provenance index](transcripts/2026-08-19-ui-diagrams-acceptance-index.md).
Each transcript contains its exact neutral setup message and setup completion.
A records the unchanged original raw prompt, its actual first response, a
normal user scope-grant continuation, and its actual second response. B, C,
and ready retain their capture directive separated from the raw user prompt
and completed user-facing response. The index names the fresh agent task and
records the pre-commit SHA-256 for each artifact.

| scenario | raw transcript |
| --- | --- |
| A: original flowchart prompt | [A](transcripts/2026-08-19-ui-diagrams-acceptance-a.md) |
| B: original screenshot red-box prompt | [B](transcripts/2026-08-19-ui-diagrams-acceptance-b.md) |
| C: original declined-install prompt | [C](transcripts/2026-08-19-ui-diagrams-acceptance-c.md) |
| ready: explicit diagram request | [ready](transcripts/2026-08-19-ui-diagrams-acceptance-ready.md) |

## Isolation and source loading

The sessions were sequential fresh contexts (`fork_turns: none`), in the order
A, B, C, then ready. Setup made the local source tree authoritative and told
each agent to follow—rather than summarize—the relevant local `SKILL.md`,
dependency policy, and readiness source. It gave no scenario conclusion,
expected phrasing, or review rubric. The original user prompt was subsequently
delivered unchanged as a distinct final message. A additionally records a
second normal user message because the source's mandatory scope-confirmation
form requires a user continuation.

The no-desktop/missing-skill controls inject a state without consulting host
PATH or Program Files; the ready control points to a local downstream
acceptance fixture. These controls establish available dependency state only.
They are not presented as agent behavior evidence.

No session authorized an external clone, installer, package operation, or
artifact generation. No local or global plugin was installed; system draw.io
was neither disabled nor uninstalled.

## Observed completed behavior

### A

The first completed response in
[A](transcripts/2026-08-19-ui-diagrams-acceptance-a.md) begins with the
mandatory default-scope confirmation form. It also discloses the missing skill
and Desktop, gives the source and Windows install command, and asks
`是否同意為本次任務安裝？`; it does not act on the prompt's `先直接幫我完成`.
The next recorded message is a normal scope grant, not installation consent.
Its actual response adopts the default scope, identifies remaining target and
delivery inputs, and repeats the explicit installation-consent question. No
installation action appears in either response.

### B

The completed response in [B](transcripts/2026-08-19-ui-diagrams-acceptance-b.md)
remains a UI-manual scope confirmation for an uploaded screenshot, says it will
red-box the Save button, and says it will not create other diagrams. It contains
no draw.io, readiness, or installation interaction.

### C

The completed response in [C](transcripts/2026-08-19-ui-diagrams-acceptance-c.md)
reports the relationship-diagram branch unavailable, does not ask or perform an
install because of the user's refusal, stops only that relationship diagram,
and continues the DOCX manual after scope confirmation. No substitute diagram
or artifact is emitted in the response.

### Ready handoff

The ready setup intentionally does not preload the downstream fixture. Its
controlled readiness report supplies the local downstream path; the wrapper and
policy instruct the agent to read it for the same-task ready handoff. The final
response in [ready](transcripts/2026-08-19-ui-diagrams-acceptance-ready.md) is
the unique no-artifact confirmation defined in that downstream fixture:
`$drawio-skill 已接手此操作流程圖需求；本次驗收不產生或匯出任何圖表檔案。`
This is an observed downstream delegated confirmation, not the wrapper saying
it will hand off.

## Replay checks

```powershell
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/check_readiness.tests.py
python -X utf8 plugins/ui-diagrams/skills/ui-diagrams/tests/skill_contract.tests.py
python -X utf8 C:/Users/derick.chang/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/ui-diagrams/skills/ui-diagrams
python -X utf8 C:/Users/derick.chang/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/ui-diagrams
Get-FileHash -Algorithm SHA256 docs/superpowers/evidence/transcripts/2026-08-19-ui-diagrams-acceptance-a.md,docs/superpowers/evidence/transcripts/2026-08-19-ui-diagrams-acceptance-b.md,docs/superpowers/evidence/transcripts/2026-08-19-ui-diagrams-acceptance-c.md,docs/superpowers/evidence/transcripts/2026-08-19-ui-diagrams-acceptance-ready.md
git diff --check
```

The test and validation commands pass in UTF-8 mode. Recomputing the transcript
hashes must match the index before a reviewer relies on the records.
