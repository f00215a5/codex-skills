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

After an approved install, re-run `check_readiness.py`. A new Codex task provides normal skill discovery after installation; do not claim the newly cloned skill is automatically discovered in the already-running task.
