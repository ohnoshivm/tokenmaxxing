# TOKENMAXXING 2.0

[![CI](https://github.com/ohnoshivm/tokenmaxxing/actions/workflows/ci.yml/badge.svg)](https://github.com/ohnoshivm/tokenmaxxing/actions/workflows/ci.yml)

**The Premium Model Delegation & Token-Efficiency System** — a toolkit for getting more and better AI-agent work done per unit of token usage or subscription allowance.

**Created by [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

**Version:** 2.0.0 · **Research date:** 21 October 2026
**Status:** CLI toolkit with local measurement and operating guidance. Routing policies are references, not a claim that the author's applications are configured or automatically routed.

> **Thesis:** The most useful multi-model system maximizes *verified outcome quality per unit of scarce resource*: subscription allowance, API spend, token consumption, execution time, and human review attention.

## Install and use TOKENMAXXING — now an actual toolkit

### 30-second quickstart

```bash
git clone https://github.com/ohnoshivm/tokenmaxxing.git
cd tokenmaxxing
python3 tokenmaxxing.py audit
python3 tokenmaxxing.py fix
python3 tokenmaxxing.py guard --print-hook
./install.sh
```

`audit`, `doctor`, and `fix` dry runs are offline and read-only. `guard --print-hook` and `statusline --install` print snippets for manual installation; they never edit settings. The installer stages eight pinned optimizer sources and installs the portable skill. No upstream optimizer hooks are activated automatically.

A sample from the author's machine (`audit --since 30d`, 21 October 2026; one machine, work counts are proxies, not a quality judgement or a benchmark; excerpt):

```text
TOKENMAXXING audit — last 30d
Claude Code: 49 sessions, 193 subagent runs, 10916 API turns
  fresh input 383.0k · cache read 2.9B · cache write 77.1M · output 6.5M
  cache hit rate 97% · weighted cost units 446.4M
  cache rebuilds: 139 (35.3M tokens)
Work (proxy — counted from tool calls, not a quality judgement)
  edits 1044 · checks 25 (24 passed, 1 failed) · commits 79
  rework rate 4% · verified-edit sessions 2/111 (2%)
  usage per passing check 20.0M units (distinct commands per session: 24)
  model mix: premium 87% · standard 12% · economy 0% · unknown 1%
```

Doctor on the same machine estimated ~19.5k always-loaded tokens: ~4.7k of instructions, ~14.1k of skill metadata (173 skills), and ~686 of subagent descriptions. Example fixes (home path abbreviated):

```text
Fixes (highest impact first)
  1. [HIGH] 2 coding-behavior optimizers are active: occam, whittle. Keep one at a time; profiles: balanced=ponytail, deep-reasoning=occam, full-product=whittle.
  2. [MEDIUM] ~/.claude/CLAUDE.md is ~4.7k tokens; move rarely-needed sections into a referenced file.
```

Example statusline with a cold cache:

```text
Opus 5.5 · ctx 129k/200k ▓▓▓░░ · cache cold — next turn rewrites ~129k · hit 100% · consider /compact
```

### Command reference

| Command | Purpose |
| --- | --- |
| `./install.sh [--dry-run] [--no-fetch]` | Install the skill and stage pinned optimizer sources. |
| `python3 tokenmaxxing.py install [--dry-run] [--no-fetch]` | Run the installer directly from the CLI. |
| `python3 tokenmaxxing.py status` | Inspect installed sources and current state. |
| `python3 tokenmaxxing.py profiles` | List available task profiles. |
| `python3 tokenmaxxing.py plugin-commands NAME` | Print native plugin commands for a candidate. |
| `python3 tokenmaxxing.py audit [--since 30d\|7d\|24h\|all\|ISO] [--compare] [--project TEXT] [--path DIR] [--top N] [--json]` | Offline analysis of local Claude Code transcripts and Codex rollouts. |
| `python3 tokenmaxxing.py doctor [--project-dir PATH] [--config-dir PATH] [--no-measure] [--json]` | Read-only audit of always-loaded instruction and tool overhead. |
| `python3 tokenmaxxing.py fix [--since 30d] [--config-dir PATH] [--keep NAME ...] [--apply] [--json]` | Preview reversible archives; [apply, undo, and list](docs/fix.md). |
| `python3 tokenmaxxing.py guard --print-hook` / `guard --hook` | Opt-in cold-cache prompt guard; [setup and safety](docs/guard.md). |
| `python3 tokenmaxxing.py statusline [--install]` | Show live context/cache status, or print the install snippet. |
| `python3 tokenmaxxing.py reset SUBCOMMAND` | Inspect or configure reset-window notifications; see [reset guide](docs/reset-activation.md). |

`audit` reports usage, cache rebuilds, model/project cost, starting context, tool-output estimates and findings. Its Work ledger counts successful edits, checks, commits and skill invocations (including user slash commands). The headline usage/check metric divides weighted usage by distinct normalized passing shell commands per session; JSON also exposes the raw passing-check divisor. Rework and verified-edit shares are proxies for workflow feedback, not output quality. Model tiers come from [model-tiers.json](policy/model-tiers.json); premium share is informational: lower usually = cheaper, check quality. Unknown models are listed. `audit --compare` compares equal windows; Work rows need at least five passing checks in each window. JSON keys are additive.

`doctor` inventories the CLAUDE.md chain and `@` imports, skill descriptions, enabled plugin skills/agents/commands/hooks, subagent descriptions, MCP server names and transports, and SessionStart/UserPromptSubmit hooks. It detects optimizer stacking against the one-optimizer rule in `policy/optimizer-registry.json` and compares findings with measured starting context. It never prints MCP secrets.

`statusline` shows context size against the model window, cache warm countdowns (5m/1h TTL), hit ratio and `/compact` hints. See [statusline setup](docs/statusline.md).

## Measure → Fix → Guard → Prove

1. **Measure** — run `audit --since 30d` and `doctor` for usage, delivered-work proxies and fixed overhead.
2. **Fix** — review `fix`, preserve skills with `--keep`, then use `--apply`; restore with `fix --undo`.
3. **Guard** — review `guard --print-hook` and opt in manually; cold, large contexts block once, then a re-send within 120 seconds proceeds.
4. **Prove** — run `audit --since 7d --compare`; compare usage per distinct passing check, rework and verified-edit share, and assess actual output quality.

## Two core pillars of TOKENMAXXING

| Pillar | What it does | Guide |
| --- | --- | --- |
| **Intelligent delegation** | Match task risk and quality needs to a capable model, bounded handoff and verification. | [Routing policy](policy/routing-policy.yaml) · [Delegation research](research/delegation-paper-2026.md) |
| **Token efficiency** | Reduce wasted context, cache rebuilds, redundant tools, oversized outputs and agent loops. | [Token-efficiency policy](policy/token-efficiency.md) · [Claude Code research](research/claude-code-token-maxxing-2026.md) |

## Third primary pillar — Provider Reset Activation Engine

Track provider reset windows and optionally receive notifications. Sending messages is off by default; see [setup and safety](docs/reset-activation.md) and [reset policy](policy/reset-activation.md).

## Optimizer candidates

These are third-party candidates, not endorsed or automatically activated. Review source, attribution and compatibility before a trial:

[Ponytail](https://github.com/DietrichGebert/ponytail) · [Occam](https://github.com/quisbaum-prog/occam) · [Whittle](https://github.com/Obed0101/whittle) · [Chisle](https://github.com/JayPokale/Chisle) · [Master of Tokens](https://github.com/devrudals/master-of) · [Claude Token Saver](https://github.com/AllenSwift/claude-token-saver) · [Simple Man](https://github.com/Maksim-Burtsev/simple-man) · [Simpler Token Saver](https://github.com/tim-hub/cc-simpler-token-saver) · [Credits](CREDITS.md)

**One-optimizer rule:** activate at most one coding-behavior optimizer at a time. “All-in-one” is one selection interface, not permission to stack overlapping rules or hooks.

**Safety guarantees:** audit and doctor are local, offline and read-only; nothing is uploaded. Audit does not include transcript content in its report. `fix --apply` moves eligible user skills into a manifest-backed archive; it never deletes skills. Guard writes only private session markers. Neither feature edits authentication, provider routing, MCP servers, hooks or settings. `statusline --install` only prints a snippet. Reset notifications are inactive by default.

## Read the research

- [Delegation paper and original long-form README content](research/delegation-paper-2026.md)
- [Claude Code token-maxxing research](research/claude-code-token-maxxing-2026.md)
- [Optimizer behavior comparison](research/optimizer-behavior-comparison-2026.md)
- [Policies](policy/)
- [Profiles](profiles/)
- [Templates](templates/)
- [Statusline setup](docs/statusline.md)
- [Installation guide](docs/installation.md)
- [Quick start](QUICK_START.md)

## Attribution

Research and implementation by **[Shivam Kumawat](https://github.com/ohnoshivm)** (@ohnoshivm), AgentKind Labs. See [CREDITS.md](CREDITS.md) and [CITATION.cff](CITATION.cff).
