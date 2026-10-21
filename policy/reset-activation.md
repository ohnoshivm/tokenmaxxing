# Reset Activation Policy — Third TOKENMAXXING Pillar

> **Recommended implementation:** [Provider Quota Activation Engine v2](../docs/quota-engine.md) and [v2 policy](quota-activation.md) provide distinct account/model pools and provider-confirmed activation. The original `reset` engine remains supported for compatibility.


**Shivam Kumawat (@ohnoshivm) · AgentKind Labs**

## Built-in operator interface

Use `python3 tokenmaxxing.py reset setup` to create an inactive private configuration; `reset status`, `reset check --dry-run`, `reset check`, `reset watch`, `reset ack`, and `reset install-macos` expose the feature without separate installer scripts. Only eligible accounts with intentionally configured `dispatch: command` and the explicit `--allow-dispatch` flag may send a CLI request; the installed macOS scheduler remains notification-only.

## Policy objective

Avoid unnecessarily delayed use of **activity-anchored** provider allowances while spending as little quota as practical. This is distinct from ordinary token-compression and model-routing policies. Activation consumes some allowance and is not automatically beneficial for every user or every quota window.

## Required checks

1. Read **account-specific** provider quota and next-reset timestamps; never assume a universal four-hour window. Distinguish session, weekly and separate model pools.
2. Classify each window as `first_request`, `fixed` or `unverified`. No ping for fixed resets; no auto-ping for unverified resets.
3. Decide if the user **wants an immediate new window**. Starting a window early can make its expiry sooner. Default to notifying, not sending.
4. For explicitly authorised activity-anchored windows, wait until verified reset time, then send at most one tiny request with the least quota-consuming supported model, using the intended subscription account and no paid API fallback.
5. Require provider adapter proof, a fresh clean context, idempotent state and a bounded grace period. A one-word prompt can still load system context.
6. Check provider acceptance and the refreshed next-reset timestamp. On failure, alert instead of inventing success. Do not keep sending repeated probes.
7. Preserve provider OAuth/API configuration; never use undocumented private endpoints or arbitrary UI automation.
8. If monitoring is not reliable to the requested minute, say so. Use provider UI notifications or manual confirmations rather than pretending an hourly task has minute precision.

## Model suggestions (not guaranteed plan entitlements)

| Provider | Lightweight candidate | Verification |
| --- | --- | --- |
| OpenAI Codex | GPT-6 Luna | Verify CLI account is subscription-backed and supports the exact model ID |
| Anthropic Claude | Haiku | Verify CLI account and model before enabling; Claude weekly limit is fixed |
| Other | Actual cheapest eligible model | Confirm provider and semantics before activation |

## Invocation contract

Use `scripts/reset_watcher.py` in **notification mode** by default. CLI dispatch requires `dispatch=command` on an eligible account **and** the explicit `--allow-dispatch` flag. The module does not claim native T3 Chat messaging support or an already-running background automation.

**Never claim that a pool was activated until a successful provider request is observed.**
