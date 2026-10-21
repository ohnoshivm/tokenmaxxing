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

`audit` and `doctor` are offline and read-only. `fix` previews reversible skill moves; `--apply` archives with a manifest and `--undo` restores. `guard --print-hook` prints an opt-in Claude Code hook snippet; it never edits settings. The installer stages eight pinned optimizer sources and installs the portable skill. No upstream optimizer hooks are activated automatically.

A sample from the author's machine (`audit --since 30d`, 21 October 2026; one machine, not a benchmark or a promise of savings; excerpt):

```text
TOKENMAXXING audit — last 30d
Claude Code: 47 sessions, 191 subagent runs, 10816 API turns
  fresh input 382.8k · cache read 2.9B · cache write 76.5M · output 6.4M
  cache hit rate 97% · weighted cost units 443.3M
  cost share: cache_write_5m 12% · cache_write_1h 16% · cache_read 65% · output 7%
  starting context per session: median 59.8k, p90 94.7k, max 103.7k
  cache rebuilds: 137 (35.1M tokens)

Work (proxy, one machine; tool calls, not a quality judgement)
  edits 0 · checks 22 (21 passed, 1 failed) · commits 76
  rework rate 5% · verified-edit sessions 0/0 (n/a)
  usage per passing check 23.0M units
  usage per distinct passing check 43.8M units
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
| `python3 tokenmaxxing.py fix [--since 30d] [--keep NAME] [--apply] [--undo [RUN_ID]] [--list]` | Preview unused user-skill archives; moves are reversible. See [fix guide](docs/fix.md). |
| `python3 tokenmaxxing.py guard --print-hook` | Print the opt-in cold-cache hook snippet; see [guard guide](docs/guard.md). |
| `python3 tokenmaxxing.py reset SUBCOMMAND` | Inspect or configure reset-window notifications; see [reset guide](docs/reset-activation.md). |

`audit` reports fresh input, cache reads/writes, output, cache hit rate and weighted cost (cache read 0.1×, 5-minute write 1.25×, 1-hour write 2×, output 5×). It breaks down cost by class, model and project; reports median/p90 starting context, full-prefix rebuilds, tool output entering context with estimated carry cost (`tokens × later turns × 0.1`), largest results, files reread 3+ times per session, subagent share, Codex totals/latest 5-hour and weekly rate-limit usage, and ranked findings. `audit --compare` compares equal windows per turn with compact numbers, percentage changes and better/worse labels; output per turn stays neutral. JSON retains numeric values.

`doctor` inventories the CLAUDE.md chain and `@` imports, skill descriptions, enabled plugin skills/agents/commands/hooks, subagent descriptions, MCP server names and transports, and SessionStart/UserPromptSubmit hooks. It detects optimizer stacking against the one-optimizer rule in `policy/optimizer-registry.json` and compares findings with measured starting context. It never prints MCP secrets.

`statusline` shows context size against the model window, cache warm countdowns (5m/1h TTL), hit ratio and `/compact` hints. See [statusline setup](docs/statusline.md).

## Measure → Fix → Guard → Prove

1. **Measure** — `audit` reports token spend and a work proxy counted from tool calls.
2. **Fix** — use `doctor` and `fix`; review the dry run, then apply or undo an archive.
3. **Guard** — optionally add `guard --print-hook` to stop a large prompt after its cache expires.
4. **Prove** — compare equal windows with `audit --compare` after each workflow change.

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

**Safety guarantees:** audit and doctor are local, offline and read-only; nothing is uploaded. Audit does not include transcript content in its report. `fix` defaults to a dry run and only moves files with a manifest and undo. `guard` is opt-in; its snippet printer never edits settings. The toolkit does not change authentication, provider routing or MCP servers. Reset notifications are inactive by default.

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
