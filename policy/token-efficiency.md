# Token Efficiency — Primary Operating Pillar

**TOKENMAXXING v1.1** · **[Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

The [full 2026 Claude Code report](../research/claude-code-token-maxxing-2026.md) provides the extensive source analysis. This document translates it into a **minimal default operating policy** that complements [model routing](routing-policy.yaml).

## Optimisation objective

Maximise **verified successful work** per unit of total resources: fresh input, cached reads/writes, reasoning/output, tool steps, subscription allowance, API charges, elapsed time and corrective rework. Token or log compression alone is not a reliable proxy for success-adjusted cost.

## Default order of operations

1. **Native capabilities first.** Use the active runtime's supported prompt caching, selective/deferred tools, context inspection, compaction and usage reports. Avoid alternate API proxies or authentication changes for speculative gains.
2. **Lean always-loaded context.** Keep global/project instruction files short and nonduplicative. Put UI/UX, 3D, SEO and other specialist material in **on-demand** skills. Include only the relevant files and approved decisions in handoffs.
3. **Adaptive code retrieval.** Start with known paths, scoped `rg` and selective reads. Use ast-grep for structural matches, LSP for definitions/references/diagnostics, and semantic/symbol indexers only when simpler methods are insufficient.
4. **Bounded execution.** Prefer one accountable executor. Use deterministic tools for formatting, tests and validation; limit agent loops, retries, redundant re-reading and unnecessary parallel agents.
5. **Safe tool output.** Condense large successful logs only when the full content is preserved or readily recoverable. Never lose compiler failures, stack traces, test errors, patch context or security findings.
6. **Cache-friendly sessions.** Keep stable prefixes/model settings during coherent tasks. Compact at meaningful boundaries, preserving unresolved requirements, decision history and test evidence. Differentiate API cache economics from subscription quotas.
7. **Measure and retain only proven additions.** Use representative paired tasks and equal acceptance criteria. Track verified quality, cost/usage, output tokens, fresh and cached input, tool calls, time and rework. Avoid multiplying headline percentage savings from different tools.

## Tool adoption tiers

| Tier | Candidate | Policy |
| --- | --- | --- |
| Default | Native context/cache, concise instructions, on-demand skills, `rg`, tests | **Core**; verify runtime support |
| Bounded candidate | [Ponytail](https://github.com/DietrichGebert/ponytail) | Test code quality, complexity and end-to-end cost on your projects; don't assume guaranteed savings |
| Need-specific | [ast-grep](https://github.com/ast-grep/ast-grep), official LSP, [Context7](https://github.com/upstash/context7) | Install only for matching code-navigation or documentation needs |
| Large repositories | [Serena](https://github.com/oraios/serena), [Cartog](https://github.com/jrollin/cartog) | Evaluate **one retrieval layer** against `rg`/LSP baseline |
| Experiments | [LeanCTX](https://github.com/yvgude/lean-ctx), [RTK](https://github.com/rtk-ai/rtk), [Headroom](https://github.com/headroomlabs-ai/headroom) | Isolated trials only; never stack compressors/proxies by default |
| Not a baseline | Aggressive history rewrites, whole-repo dumps, duplicate memory engines, unverified multi-proxy routing | Avoid unless there is task-specific evidence and rollback |

## Evidence and limitations

In [JetBrains' 80 paired-task Ponytail test](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/), typical measured cost fell 10.3% and code written fell about 15%, **without a statistically detected quality difference**. This is not a guarantee of unchanged quality or the same savings elsewhere.

In [JetBrains' RTK test](https://blog.jetbrains.com/ai/2026/07/rtk-claude-code-token-savings/), typical low-effort cost **increased** 7.6%, while high-effort cost showed no meaningful improvement. This demonstrates why per-command compression is not whole-session savings.

The full supplied research contains additional tools, candidate rankings, setup commands, study links and caveats. The **rankings are research assessments, not a validated universal league table**. Recheck current versions and source evidence before deploying.

## Important: T3 Chat versus Claude Code

The overall TOKENMAXXING delegation policy is operated from **T3 Chat** when its actual model/tool capabilities permit. The report's `~/.claude/settings.json`, `/context`, `/compact`, `/plugin`, LSP plugins, prompt-cache TTL settings and shell hooks are specific to Claude Code runtimes. Do not claim they automatically work or are installed inside T3 Chat.

Never alter working subscription OAuth, Token Harbor configuration, API billing, credentials or repository permissions as part of a token-efficiency experiment without explicit approval.

## Before/after trial

1. Select 10–20 representative tasks with known verification and clean starting commits.
2. Establish unmodified native-tool baseline with repeated runs.
3. Add **one** candidate treatment.
4. Compare verified pass rate, rework, API/allowance usage where observable, cache mix, steps and elapsed time.
5. Keep only improvements that survive repetition and preserve important quality, security and accessibility criteria.
6. Document the exact setup, version, model and effort in [the scorecard](../evaluation/scorecard.csv).

**Permanent rule:** Optimise the full problem-solving trajectory, not merely the apparent size of a single model response.
