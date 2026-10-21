![TOKENMAXXING — Spend less usage. Ship more verified work.](docs/assets/banner.svg)

TOKENMAXXING measures local Claude Code and Codex usage against verified work,
then offers reversible setup cleanup and an opt-in cold-cache guard.

[![CI](https://github.com/ohnoshivm/tokenmaxxing/actions/workflows/ci.yml/badge.svg)](https://github.com/ohnoshivm/tokenmaxxing/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/ohnoshivm/tokenmaxxing?display_name=tag&color=3DDC84)](https://github.com/ohnoshivm/tokenmaxxing/releases/latest)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3DDC84?labelColor=30363D)](docs/installation.md)
[![stdlib only · offline](https://img.shields.io/badge/stdlib%20only-offline-3DDC84?labelColor=30363D)](docs/installation.md)

## Why this exists

> **One machine · 30-day sample:** 140 cache rebuilds accounted for about 35M tokens.
> Rework was 9%; 17% of edit sessions had a passing check after the final edit.
> These local logs are a measurement sample, not a benchmark or a savings claim.

## Quickstart

Clone the repository and run the local measurements directly:

```bash
git clone https://github.com/ohnoshivm/tokenmaxxing.git
cd tokenmaxxing
python3 tokenmaxxing.py audit --since 7d
python3 tokenmaxxing.py doctor
```

The CLI requires Python 3.9+ and uses only the standard library. No install
step is needed for these measurements.

## Sample audit

![Rounded TOKENMAXXING audit output from one machine; the work ledger is a tool-call proxy.](docs/assets/audit.svg)

Rounded output from one machine's local 30-day logs. The Work block is a
tool-call proxy, not a quality score; this sample is not a benchmark.

## Measure → Fix → Guard → Prove

Run these commands from the repository checkout with `python3 tokenmaxxing.py`.

![Measure with audit, review reversible fixes, guard against a cold cache, and prove change with audit comparison.](docs/assets/loop.svg)

## Commands

| Command | What it does | Writes anything? |
| --- | --- | --- |
| `audit` | Measure local Claude Code and Codex usage plus the work ledger. | No; offline and read-only. |
| `doctor` | Inspect instruction, skill, plugin, hook and MCP overhead. | No; offline and read-only. |
| `fix` | Plan a reversible archive of unused skills; use `--undo` to restore. | Dry run by default; `--apply` moves files and writes a manifest. |
| `guard` | Opt-in `UserPromptSubmit` hook that holds a cold-cache prompt once. | The active hook writes its own marker files; `--print-hook` only prints. |
| `statusline` | Show context size, cache warmth and hit ratio. | No; `--install` only prints a settings snippet. |
| `reset` | Configure and inspect reset windows; check or watch for notifications. | Setup writes a private config and checks update local state. |
| `install` | Install the portable skill and stage eight pinned optimizer sources. | Yes; writes local files and can fetch sources unless `--no-fetch` is used. |
| `status` | Inspect staged source revisions and the installed skill. | No. |
| `profiles` | List task profiles. | No. |
| `plugin-commands NAME` | Print candidate plugin commands without running them. | No. |

## Safety guarantees

The measurement path is offline and read-only by default. Commands that write
are explicit and their effects are listed above.

- `audit` and `doctor` read local data. Nothing is uploaded; audit reports
  exclude transcript text, and doctor never prints MCP secrets.
- `fix` defaults to a dry run. With `--apply`, it only moves skill files,
  writes a manifest before moving, and supports `--undo`; it never deletes.
- TOKENMAXXING never edits `settings.json`, authentication files or provider
  configuration.
- `statusline --install` and `guard --print-hook` print snippets for you to
  review and apply yourself.
- Pinned optimizer sources are not enabled automatically. The installer does
  not install their dependencies or execute their code.
- Reset notifications are inactive until configured. Provider dispatch
  requires an explicit opt-in and a verified account-specific command.

## Operating pillars

- **Delegation:** task-fit guidance, handoffs and verification live in the
  [routing policy](policy/routing-policy.yaml) and
  [delegation research](research/delegation-paper-2026.md). The policy is
  reference material; it does not configure automatic routing.
- **Usage efficiency:** measure cache, setup overhead and work, then compare
  equal windows using the [token-efficiency policy](policy/token-efficiency.md)
  and [measurement notes](docs/measurement.md).

## Documentation

### Start and measure

- [Installation and verification](docs/installation.md) — install options,
  offline measurement and scope.
- [Extended quickstart](docs/quick-start.md) — safe manual setup and
  verification workflow.
- [Mission and measurement notes](docs/measurement.md) — metric definitions,
  limits and research map.

### Commands and setup

- [Reversible cleanup](docs/fix.md) — dry run, archive manifest and undo.
- [Cold-cache guard](docs/guard.md) — hook behavior, setup and safety.
- [Status line](docs/statusline.md) — context and cache display, install snippet and limits.
- [Reset windows](docs/reset-activation.md) — inactive setup, notifications and
  explicit dispatch rules.
- [Optimizer profiles](docs/optimizer-profiles.md) — controlled comparison and
  candidate evidence.
- [T3 Chat guide](docs/t3-chat.md) — portable policy without assumed native
  automation.

### Policies and research

- [Delegation routing policy](policy/routing-policy.yaml)
- [Token-efficiency policy](policy/token-efficiency.md)
- [Delegation research](research/delegation-paper-2026.md)
- [Claude Code token-efficiency research](research/claude-code-token-maxxing-2026.md)
- [Optimizer behavior comparison](research/optimizer-behavior-comparison-2026.md)

### Project records

- [Changelog](CHANGELOG.md)
- [Third-party credits](CREDITS.md)
- [Citation metadata](CITATION.cff)

## Attribution

**Created by Shivam Kumawat (@ohnoshivm) · AgentKind Labs**
([profile](https://github.com/ohnoshivm)). See [credits](CREDITS.md) and
[citation](CITATION.cff).
