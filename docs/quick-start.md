# Quick Start — Safely Operating Premium Mode

**Created by [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

This repository pairs a stdlib-only measurement and cleanup CLI with operating guidance. It does not contain a live auto-router or an official T3 configuration file.

## Measure, inspect and watch

```bash
python3 tokenmaxxing.py audit --since 7d
python3 tokenmaxxing.py doctor
python3 tokenmaxxing.py fix            # dry run; --apply then --undo if you agree
python3 tokenmaxxing.py guard --print-hook
python3 tokenmaxxing.py statusline --install
```

`audit` reads local Claude Code transcript and Codex rollout usage offline; `doctor` inspects always-loaded context and optimizer stacking. Both are read-only. `fix` moves unused skills into a dated archive with a manifest (`--undo` restores; nothing is deleted). `guard --print-hook` and `statusline --install` print a Claude Code settings snippet and never write it. After making a change, compare equal windows with `python3 tokenmaxxing.py audit --since 7d --compare`. See [fix](fix.md), [guard](guard.md) and [statusline setup](statusline.md).

## Reset-window activation — integrated feature

```bash
python3 tokenmaxxing.py reset setup
# Edit the generated private config with your real provider/account reset times.
python3 tokenmaxxing.py reset status
python3 tokenmaxxing.py reset check --dry-run
python3 tokenmaxxing.py reset check
# Optional on macOS: python3 tokenmaxxing.py reset install-macos
```

The main installer also supports `./install.sh --with-reset-config` to create the **inactive** example configuration. The default watcher only notifies; a paid or subscription-backed request cannot be assumed safe or automated without verifying the actual provider/window. See [the reset guide](reset-activation.md).


## One-command TOKENMAXXING install

```bash
git clone https://github.com/ohnoshivm/tokenmaxxing.git
cd tokenmaxxing
./install.sh
```

Requires Git and Python 3.9+. This installs our portable skill and stages eight pinned optimizer sources. No conflicting upstream hooks, proxies or provider settings are enabled. See [installation details](installation.md) and [T3 Chat guide](t3-chat.md).

## Core foundation: Claude Code token-maxxing

Model selection alone cannot eliminate wasted context or agent steps. Before installing extra plugins, read the [token-efficiency policy](../policy/token-efficiency.md) and [2026 research report](../research/claude-code-token-maxxing-2026.md). Establish a baseline with native caching, concise instructions, on-demand skills, scoped code search, tests and per-task measurements.

The research includes **optional Claude Code CLI commands**; these do not automatically install into T3 Chat. Avoid changing working authentication, cache settings or MCP configurations merely to match the report.

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
