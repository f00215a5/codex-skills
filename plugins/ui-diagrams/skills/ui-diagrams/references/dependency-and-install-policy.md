# draw.io dependency and install policy

Read this reference only when `check_readiness.py` reports `needs-install` or `unavailable`.

## Consent, scope, and runtime approval

An install is allowed only after the user gives **明確同意** for the **current task** by affirmatively answering `是否同意為本次任務安裝？`. A prior-task approval, a general request to make a diagram, or silence is not consent. Before requesting it, disclose every missing component, the selected platform command below, the upstream source URL, and scope:

- Upstream drawio-skill source: `https://github.com/Agents365-ai/drawio-skill.git`; clone it only when missing into the current user's `.codex/skills/drawio-skill`.
- draw.io Desktop is installed for the current user's normal platform package-manager scope, except the documented Linux package command may request administrator privileges.
- Each external action (clone, download, installer, and privileged package operation) still requires the runtime's permission mechanism. Explicit user consent does not bypass runtime approval.

Do not run any clone, download, installer, or package command before both current-task affirmative consent and the applicable runtime approval are present. If either is declined or unavailable, report it in chat and stop the diagram branch only.

## Supported platform commands

Choose only the command for the current platform. The release file for Linux must be the selected official release asset from `https://github.com/jgraph/drawio-desktop/releases`.

```text
Windows: winget install --id JGraph.Draw --exact --source winget --accept-package-agreements --accept-source-agreements
macOS: brew install --cask drawio
Linux Debian: download the selected official .deb from https://github.com/jgraph/drawio-desktop/releases as ./drawio-release.deb and run sudo apt-get install -y ./drawio-release.deb
Linux RPM: download the selected official .rpm from the same release as ./drawio-release.rpm and run sudo dnf install -y ./drawio-release.rpm
```

After an approved install, re-run `check_readiness.py`. If its status is `ready`, the 目前任務直接載入並閱讀 `.codex/skills/drawio-skill/skills/drawio-skill/SKILL.md` when the skill was newly cloned; when it already existed, directly read the ready report's `drawioSkill.path` instead. 直接讀取後立即交棒給 $drawio-skill. This direct load supplies the downstream instructions to the current task only; it does not create, preview, export, or modify any output.

新的 Codex 任務仍可能需要才能以正常自動發現（normal automatic discovery）方式找到新安裝的 skill. Do not claim that automatic discovery has refreshed in the already-running task.

## Terminal install or handoff failure

If clone、desktop 安裝或重新檢查失敗, or if downstream SKILL.md 讀取、解析、載入或交棒失敗 after readiness (including content that is unreadable or malformed), report the failed action and relevant status 僅在對話中, 分類為 `unavailable` 的終止狀態, and 不得重新進入同意或安裝迴圈. 只停止圖表分支 and return control so the parent can 繼續 UI 手冊流程. 不得進行任何圖表產出, preview, export, or modify any diagram artifact in this failure path.
