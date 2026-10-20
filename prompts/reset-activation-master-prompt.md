# TOKENMAXXING — Reset Activation Engine (Master Prompt)

Build and operate a **provider-aware usage-reset activation system** for my connected Claude, Codex and other supported subscription accounts, coordinated with T3 Chat. The objective is to avoid losing usable time between quota resets and the first request **without wasting tokens or compromising account security**.

For each account and independent quota pool (session, weekly, model-specific):

1. Detect or request the **provider-reported next reset time**, timezone, remaining allowance, and exact reset semantics. Never assume all providers use four-hour windows or that weekly periods start with the first message.
2. Classify resets as **first-request-anchored**, **fixed schedule**, or **unverified**. Do not auto-message fixed or unverified windows. Only activate a first-request-anchored window if I have explicitly enabled it and want the new timer to begin immediately.
3. At the verified reset time, trigger **once**, ideally within 60 seconds, with the least quota-consuming subscription-backed model available to that account (e.g., GPT-6 Luna for Codex, Haiku for Claude). Use a fresh, minimal context and a one-word prompt such as `yo`. Never fall back to paid API usage without explicit approval.
4. Verify that the request succeeded and retrieve the new reset time; record the next event. Prevent duplicate triggers, loops, wrong-account routing and repeated failed probes. If activation is unsupported, alert me instead of pretending it ran.
5. Preserve all existing OAuth sessions, T3/Claude/Codex provider settings, model routing, skills, hooks and MCP connections. Use documented integration points only; never scrape private endpoints or expose tokens.
6. Provide a local status dashboard, macOS notifications, opt-in execution, safe rollback and tests. Treat hourly or five-minute refresh limitations as limitations, not minute-accurate guarantees.

**Critical distinction:** A fixed weekly quota already resets on schedule; an automatic `yo` only wastes usage. An activity-anchored window may benefit from immediate first-use **only when I actually want that new window to start immediately**. Quality-adjusted savings matter more than superficial timer optimisation.

First audit capabilities and document unsupported features. Implement the safest functional version before adding automation, then verify outcomes on every configured provider.
