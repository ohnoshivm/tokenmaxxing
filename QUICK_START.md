# Quick Start — Safely Operating Premium Mode

**Created by [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

**This repository is an operating protocol, not installed software.** It does not contain a live auto-router or an official T3 configuration file.

## 1. Verify the host

Check whether your active interface is **T3 Chat** (multi-model conversation) or **T3 Code** (code-agent workspaces). Confirm that its version and connected provider actually expose the model names, effort options, delegation features and file/terminal tools you intend to use. In T3 Code, see [official project documentation](https://github.com/pingdotgg/t3code) and [portable handoffs](https://github.com/pingdotgg/t3code/blob/main/docs/user/portable-handoffs.md).

## 2. Audit safely

1. Record the exact model IDs offered in the picker; do not assume display names are API IDs.
2. Record authentication type and whether each route is covered by a subscription or separately billed API.
3. Back up existing instruction files and settings before altering them.
4. Do not touch working credentials, Token Harbor/provider routing, MCP servers or permissions unless independently necessary and approved.
5. Identify repository instructions already in place; merge rather than overwrite.

## 3. Run a manual pilot

1. For an important new project, manually select **Opus 5.5 Medium** and create `templates/TASK_BRIEF.md` with exact constraints and acceptance criteria.
2. Transfer the brief into the supported project context/handoff mechanism.
3. Select **GPT-6 Luna High** for a bounded feature or component; use **GPT-6.1 Sol High** for complicated engineering tasks.
4. Run deterministic tests, type checking and build validation as applicable.
5. Create `templates/HANDOFF.md` with actual outcomes. Use Opus High only if a major creative or architectural issue remains.
6. Record task tokens/usage and results in `evaluation/scorecard.csv` where the platform exposes them.

## 4. Repetitive pilot

Run a small, clear batch through **GPT-5.6 Luna Medium**, then test **Haiku Low/Medium** on the same batch with the same acceptance criteria. Scripts handle schema validation and deduplication.

## 5. Decide automation from evidence

Native delegation and custom-agent features may vary by T3 version and provider. Verify each feature before enabling it. `policy/routing-policy.yaml` is portable specification data, **not** something T3 necessarily reads.

## 6. Definition of success

A successful pilot ends with: a reviewed task brief, a correct code or content artifact, objective validation, a concise receipt, preserved subscription authentication, no unexpected API billing and a reproducible task record.
