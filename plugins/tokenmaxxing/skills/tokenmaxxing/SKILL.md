---
name: tokenmaxxing
description: Improve verified AI-agent work per token or subscription allowance through precise context, bounded delegation, local usage measurement, one optimizer, and safe verification.
---
# TOKENMAXXING — Quality-adjusted execution

1. **Finish the request.** Confirm acceptance criteria, correctness, tests, accessibility, security and design fidelity before simplifying.
2. **Use the fewest capable agents.** Delegate only when task boundaries and verification are clear; use scripts for deterministic work.
3. **Acquire context precisely.** Start with relevant paths, symbols and error traces; avoid dumping unchanged files or full transcripts.
4. **Use one coding-behavior optimizer.** Treat profiles and upstream tools as candidates. Never stack overlapping rules or hooks.
5. **Reuse working code.** Prefer existing utilities and dependencies; preserve required behavior and quality.
6. **Keep useful evidence.** Filter repetitive successful output when helpful; retain exact failures, diagnostics and patch context.
7. **Cache and hand off thoughtfully.** Keep stable instructions concise; checkpoint decisions, open issues and acceptance evidence.
8. **Verify the result.** Run relevant checks and report actual outcomes, gaps and unresolved issues.
9. **Measure first.** For questions about token use, cost, limits or expense, run `python3 <repo>/tokenmaxxing.py audit --since 7d` and `python3 <repo>/tokenmaxxing.py doctor`. Read findings, propose the top three fixes, and after changes run `audit --compare`. Never paste transcript content.
10. **No silent installation.** Do not change auth, billing/provider routes, MCP, hooks or settings; get explicit opt-in before enabling an optimizer that executes hooks.

## Reset-window requests

For account-level quota reset optimization, use `python3 tokenmaxxing.py reset` and read `docs/reset-activation.md` plus `policy/reset-activation.md`. Notifications are the default. Never invent reset times, send provider requests, auto-ping fixed weekly windows, or alter auth/routing without verified semantics and explicit opt-in.

Read `profiles/` and `policy/optimizer-registry.json` for candidates. Claude Code plugin commands may not work in T3 Chat.
