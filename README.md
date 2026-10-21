# TOKENMAXXING

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
python3 tokenmaxxing.py doctor
python3 tokenmaxxing.py statusline --install
./install.sh
```

`audit` and `doctor` are offline and read-only. `statusline --install` prints a Claude Code `settings.json` snippet; it never edits the file. The installer stages eight pinned optimizer sources and installs the portable skill. No upstream optimizer hooks are activated automatically.

A sample from the author's machine (`audit --since 30d`, 21 October 2026; one machine, not a benchmark or a promise of savings; excerpt). The Work block counts tool calls, so it is a proxy for work done, not a quality judgement:

```text
TOKENMAXXING audit — last 30d
Claude Code: 49 sessions, 192 subagent runs, 10923 API turns
  fresh input 383.0k · cache read 2.9B · cache write 77.1M · output 6.5M
  cache hit rate 97% · weighted cost units 446.5M
  cost share: cache_write_5m 12% · cache_write_1h 16% · cache_read 65% · output 7%
  starting context per session: median 59.8k, p90 94.7k, max 103.7k
  cache rebuilds: 139 (35.3M tokens)

Work (proxy — counted from tool calls, not a quality judgement)
  edits 223 · checks 236 (200 passed, 36 failed) · commits 87
  rework rate 15% · verified-edit sessions 7/22 (32%)
  usage per passing check 2.4M units
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
| `python3 tokenmaxxing.py statusline [--install]` | Show live context/cache status, or print the install snippet. |
| `python3 tokenmaxxing.py fix [--since 30d] [--keep NAME] [--apply] [--undo [RUN_ID]] [--list] [--json]` | Archive unused skills with a manifest and undo; dry run by default. |
| `python3 tokenmaxxing.py guard [--print-hook\|--hook] [--min-context N] [--grace SECONDS]` | Opt-in hook that warns once when the prompt cache is cold. |
| `python3 tokenmaxxing.py reset SUBCOMMAND` | Inspect or configure reset-window notifications; see [reset guide](docs/reset-activation.md). |

`audit` reports fresh input, cache reads/writes, output, cache hit rate and weighted cost (cache read 0.1×, 5-minute write 1.25×, 1-hour write 2×, output 5×). It breaks down cost by class, model and project; reports median/p90 starting context, full-prefix rebuilds, tool output entering context with estimated carry cost (`tokens × later turns × 0.1`), largest results, files reread 3+ times per session, subagent share, Codex totals/latest 5-hour and weekly rate-limit usage, and ranked findings. `audit --compare` compares equal windows per turn with compact numbers, percentage changes and better/worse labels; output per turn stays neutral. JSON retains numeric values.

`doctor` inventories the CLAUDE.md chain and `@` imports, skill descriptions, enabled plugin skills/agents/commands/hooks, subagent descriptions, MCP server names and transports, and SessionStart/UserPromptSubmit hooks. It detects optimizer stacking against the one-optimizer rule in `policy/optimizer-registry.json` and compares findings with measured starting context. It never prints MCP secrets.

`statusline` shows context size against the model window, cache warm countdowns (5m/1h TTL), hit ratio and `/compact` hints. See [statusline setup](docs/statusline.md).

`fix` turns those findings into actions, and applies only the safe one: user skills with zero invocations in the window move into `<config>/tokenmaxxing-archive/<run>/skills`, with a manifest written before the first move. Every other finding (duplicate copies, stacked optimizers, oversized instruction files) is a suggestion with the exact command or section to change. Dry run by default; `--undo` restores; nothing is ever deleted. See [fix guide](docs/fix.md).

`guard` is an opt-in `UserPromptSubmit` hook. When a session idles past its prompt-cache TTL with a large context, it blocks the prompt once with a short message and a marker keyed by session id; a re-send inside `--grace` passes, so you choose between rebuilding, `/compact`, or `/clear`. Errors exit 0 silently, and it never adds tokens to model context. See [guard setup](docs/guard.md).

## Measure → Fix → Guard → Prove

1. **Measure** — `audit` for token, cache and work baselines; `doctor` for what loads before the first prompt.
2. **Fix** — `fix` to archive unused skills reversibly, then work through its manual suggestions.
3. **Guard** — `guard` so idling past the cache TTL stops costing a silent full-prefix rebuild.
4. **Prove** — `audit --compare` on equal windows, per turn, plus rework rate and verified-edit share.

Previously, the project recommended measuring end-to-end usage without shipping a measurement tool. The local audit closes that gap; results describe the machine's available local logs and usage data.

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

**Safety guarantees:** audit and doctor are local, offline and read-only; nothing is uploaded. Audit does not include transcript content in its report. The toolkit does not change authentication, provider routing, MCP servers, hooks or settings. `statusline --install` and `guard --print-hook` only print snippets; the guard writes only its own marker files. `fix` never deletes: it moves skill directories into a dated archive with a manifest and an undo. Reset notifications are inactive by default.

## Read the research

- [Delegation paper and original long-form README content](research/delegation-paper-2026.md)
- [Claude Code token-maxxing research](research/claude-code-token-maxxing-2026.md)
- [Optimizer behavior comparison](research/optimizer-behavior-comparison-2026.md)
- [Policies](policy/)
- [Profiles](profiles/)
- [Templates](templates/)
- [Statusline setup](docs/statusline.md)
- [Fix guide](docs/fix.md)
- [Guard setup](docs/guard.md)
- [Installation guide](docs/installation.md)
- [Quick start](QUICK_START.md)

## Attribution

Research and implementation by **[Shivam Kumawat](https://github.com/ohnoshivm)** (@ohnoshivm), AgentKind Labs. See [CREDITS.md](CREDITS.md) and [CITATION.cff](CITATION.cff).
