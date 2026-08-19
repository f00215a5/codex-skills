---
name: ui-diagrams
description: Safely prepare non-screenshot diagrams for a UI manual by checking draw.io readiness, obtaining task-specific install consent, and handing execution to the upstream draw.io skill.
---

# UI diagrams

This skill is an orchestration boundary for a parent UI-manual workflow. It never creates, previews, exports, or changes diagram artifacts.

## Route the request

1. Confirm that the requested visual is a diagram rather than a screenshot. For a screenshot request, return control to the caller without invoking draw.io.
2. Run `scripts/check_readiness.py` and read its JSON `status`: `ready`, `needs-install`, or `unavailable`.

## When dependencies need installation

For `needs-install`, read [dependency-and-install-policy.md](references/dependency-and-install-policy.md). Present the missing components, exact platform command, upstream source URL, install scope, and this exact question: `是否同意為本次任務安裝？` Do not run an installer unless the user gives 明確同意 in this current task and the runtime grants the required approval.

On an approved install, clone `https://github.com/Agents365-ai/drawio-skill.git` into the current user's `.codex/skills/drawio-skill` only when it is missing. Run only the policy-supported platform installer, then re-run readiness. If it is ready, use the policy's current-task direct-load procedure and immediately hand off; never generate output while loading the downstream skill.

If clone, desktop installation, or the recheck fails, follow the policy's terminal failure path. Do not restart the consent or installation flow.

If the user declines, or readiness is `unavailable`, report that status only in chat, explicitly return the caller to the continuing UI manual workflow, and 只停止圖表分支. Do not attempt another installer, diagram tool, artifact operation, or workaround.

## Handoff boundary

When readiness is `ready`, 立即交棒給 $drawio-skill. Do not wait to generate anything and 不自行建立、預覽、匯出或修改 `.drawio` or PNG files. Downstream owns every generation and delivery decision; its default delivery is `diagram.drawio` plus `diagram.drawio.png`, which the user may explicitly override before downstream generation.
