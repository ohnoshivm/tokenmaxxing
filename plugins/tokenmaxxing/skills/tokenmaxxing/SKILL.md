---
name: tokenmaxxing
description: Plan and execute software work using token-efficient context retrieval, bounded agent loops, complete requirements and verified outcomes; invoke for coding, debugging, repository analysis, handoffs and optimizer evaluation, and usage-reset scheduling.
---
# TOKENMAXXING — Quality-adjusted execution

1. **Finish the whole request.** Confirm acceptance criteria, feature completeness, tests, accessibility, security and design fidelity before simplifying any implementation.
2. **Select the fewest capable agents.** Use Opus Medium for consequential thinking when available under the user's routing policy, GPT execution for concrete implementation, and scripts for deterministic checks. Never switch models merely for appearances.
3. **Acquire context precisely.** Start with relevant paths and error traces. Use scoped text search; escalate to AST/LSP and symbols for complex relationships. Avoid unnecessary whole-repository dumps and rereading unchanged context.
4. **Use one coding-behavior profile.** Balanced (Ponytail candidate), Deep reasoning (Occam candidate), Full product (Whittle candidate), Minimal patch, Large repository. These are **candidates**, not preinstalled active plugins. Never stack overlapping hook-based optimizers.
5. **Reuse working code.** Prefer existing utilities, documented dependencies and minimal correct changes. Do not sacrifice animations, responsive layout, required interactions or test coverage to save tokens.
6. **Preserve error evidence.** Filter repetitive *successful* output only when needed, and retain exact failing diagnostics, stack traces and patch context.
7. **Cache and handoff thoughtfully.** Prefer stable instructions and concise checkpoints over repeated re-exploration. Only compact at meaningful boundaries, preserving open issues and approved decisions.
8. **Verify every completion.** Run relevant tests and record real results. Report what changed, what passed, what was not checked and what remains unresolved.
9. **Measure end-to-end.** Record pass/fail, actual fresh/cache/output tokens where available, time, retries and cost. Output shortening alone is not proven task savings.
10. **Reset-window scheduling.** When the task concerns provider quotas, distinguish first-request-anchored windows from fixed weekly windows. Use the notification-first reset watcher under `scripts/reset_watcher.py`; do not auto-ping unknown/fixed pools. Opt-in to a minimal provider CLI call only after verifying the reset time, correct subscription account, low-cost model and user approval. See `policy/reset-activation.md`.
11. **No silent installation.** Never change auth, billing/provider routes, MCP/hook settings or T3 configuration. Ask before enabling a third-party optimizer that executes hooks or installs globally.

Read `profiles/` and `policy/optimizer-registry.json` for tools and profiles. CLAUDE Code plugin commands are not guaranteed to work in T3 Chat.
