# Premium Multi-Model Delegation — Project Instructions

**Created by [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

This file describes **policy**, not automatic model switching. Use only models, effort settings, tools, subscriptions and delegation mechanisms actually supported and authorized in the current environment. Do not change authentication, provider routes, billing or destructive permissions without approval.

## Objective
Deliver the highest verified task quality with minimal *total* wasted reasoning, token use, retries, tool calls, subscription allowance, API charges and human review. Correctness, security, originality and acceptance criteria take precedence over raw token savings.

## First-class token-efficiency policy

See [policy/token-efficiency.md](policy/token-efficiency.md) and the [full Claude Code token-maxxing research](research/claude-code-token-maxxing-2026.md). Token optimisation is a **primary operating objective**, not an optional afterthought:

- Keep permanent instructions brief; load specialist skills and documentation only when relevant.
- Search for precise paths, names and strings with scoped `rg`; use LSP/AST navigation when symbol semantics or diagnostics matter; use semantic retrieval only when justified.
- Preserve cache-friendly stable context; compact or clear only at meaningful boundaries, retaining approved decisions and errors.
- Do not compress failing tests, stack traces, patch anchors or security-critical output beyond what can be safely retrieved.
- Prefer deterministic scripts and existing utilities to model calls; resist needless abstractions and dependencies.
- Never add multiple overlapping MCP search, memory or output-compression layers without separate A/B tests.
- Measure **verified task success, total actual resource usage, retries and time**; per-tool output shrinkage is not proof of session-level savings.
- Keep Claude Code CLI-specific hooks and settings separate from T3 Chat unless the active runtime explicitly supports them.

## Model responsibilities
- **Claude Opus 5.5 Medium — default high-level intelligence.** Problem framing, strategy, creative direction, architecture, UI/UX, important research synthesis, implementation specifications and acceptance criteria.
- **Claude Opus 5.5 High — important escalation.** Major creative decisions, difficult reasoning, high-impact architecture and flagship critical reviews. Xhigh is exceptional; Max requires explicit approval. No automatic Max.
- **GPT-6 Luna High — default bounded code executor.** Implement specified features, routine development, code modifications, tests and corrections. Xhigh/Max only for exceptional coding work if explicitly approved; consider Sol High first for complex autonomous tasks.
- **GPT-6.1 Sol High — advanced engineering.** Complex implementation, architecture-sensitive refactoring, difficult multi-file debugging and failures outside Luna's capability.
- **GPT-5.6 Luna Medium/High — primary repetitive intelligent executor.** Classification, structured extraction, small routine changes, approved bulk workflows and simple research.
- **Claude Haiku 5.5 Low/Medium — secondary repetitive executor.** Fallback for structured and lightweight tasks.
- **Claude Sonnet 5.5 Medium — optional specialist.** Research synthesis, conventional planning or targeted second opinion when justified. Sonnet High is not the default.
- **DeepSeek V4.1 Flash 1017 — inactive.** Do not route to DeepSeek until explicitly provisioned, authorized and benchmarked.
- **Local scripts/tools — zero model calls.** Prefer for deterministic formatting, searching, linting, checking, compiling, tests and data validation.

## Execution rules
1. Before acting, identify objective, non-goals, affected files, constraints, tests, failure risk and expected deliverable. For straightforward tasks do this implicitly and execute directly.
2. Do not force every task through a planner and a reviewer. Invoke Opus when judgment is genuinely needed.
3. Choose one accountable model per unit of work. Delegate only for independent parallel work, specialist improvement or bounded context isolation.
4. Never open an entire repository when a targeted search or few files suffice. Load only relevant skills and tools.
5. Use versioned brief/handoff/receipt files instead of copying full conversations. Preserve crucial unresolved decisions and evidence.
6. Avoid large terminal logs; summarize successful commands, retain full error details and full logs when needed.
7. Prefer objective verification: formatter, type-checker, build, unit/integration tests, diff and accessibility/performance checks when relevant.
8. After two unproductive attempts, stop guessing. Produce a concise failure dossier and escalate to Sol High for engineering or Opus High for intellectual/architectural decisions. Escalate sooner for high risk.
9. Review proportionally to risk. Only demand Opus High review for flagship creative changes, consequential architecture or important decisions.
10. Do not claim a test passed unless executed. Do not claim installed configuration changes unless performed and verified.
11. Do not treat OpenCode radar fallback values as independent benchmark measurements. Use Artificial Analysis as the benchmark reference and project tests as the final arbiter.
12. Keep API billing and subscription quota separate; never switch from included subscription access to separately billable API access without consent.
13. Protect secrets, user data, repository content and provider credentials. Respect least privilege and permission prompts.

## Handoff and completion
For significant cross-model tasks, use `templates/TASK_BRIEF.md` and `templates/HANDOFF.md`. On completion, report changed files, exact tests and results, known limitations, and what remains. Reviewers use `templates/REVIEW.md` and return APPROVE / REQUEST_CHANGES / BLOCK with evidence.

## Platform-specific caveat
T3 Chat is a conversational interface; T3 Code is a coding-agent control surface. Cross-provider handoff and native delegation depend on the installed app version and provider adapter. These project instructions do not themselves enable tools or routing. The routing YAML is **reference only**, not official T3 configuration.
