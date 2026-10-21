# Mission and measurement notes

TOKENMAXXING aims to save AI usage while delivering the highest quality and quantity of verified work. Correctness, security, originality and acceptance criteria take priority over raw token savings. The useful measure is verified work per unit of usage, alongside retries, time and review effort.

## Product status

This repository contains a Python CLI for local measurement and reversible cleanup, plus operating guidance. Delegation and optimizer policies are references; the project does not configure a host's model routing or automatically dispatch tasks.

## What `audit` measures

`audit` reads locally available Claude Code transcripts and Codex rollouts. It reports fresh input, cache reads and writes, output, cache hit rate and weighted cost units. Cost weights are documented as 0.1× for cache reads, 1.25× for five-minute cache writes, 2× for one-hour cache writes and 5× for output.

The report can also include starting-context percentiles, full-prefix cache rebuilds, model and project totals, tool output entering context with an estimated later-turn carry cost, repeated file reads, subagent share, Codex rate-limit usage and ranked findings. These values describe the logs available on that machine and period.

The Work block counts edits, checks and commits from tool calls. It derives failed-check rework, edit sessions with a passing check after their final edit, usage per passing check and model-tier mix. This is a work-activity proxy, not a measure of correctness or quality. The underlying counts can be incomplete when a host does not record an event.

## Setup overhead

`doctor` inventories instruction files and imports, skill metadata, enabled plugin skills/agents/commands/hooks, subagent descriptions, MCP names and transports, and session/prompt hooks. It estimates always-loaded overhead from available instruction and skill metadata; it does not claim to measure every token sent to a model. MCP secrets are not printed.

## Boundaries

- `audit` and `doctor` are local, offline and read-only. They do not upload transcripts or include transcript text in the report.
- A single machine's output is a sample, not a benchmark or a promised savings rate.
- A lower usage-per-check figure can reflect repeated checks; interpret it with the work counts and task quality.
- Optimizer comparisons require the same task, model, tools and acceptance checks in separate runs. Do not add savings claims from different tools together.

## Research notes

- [Delegation research and implementation reference](../research/delegation-paper-2026.md)
- [Claude Code token-efficiency research](../research/claude-code-token-maxxing-2026.md)
- [Optimizer behavior comparison](../research/optimizer-behavior-comparison-2026.md)
- [Delegation routing policy](../policy/routing-policy.yaml)
- [Token-efficiency policy](../policy/token-efficiency.md)
