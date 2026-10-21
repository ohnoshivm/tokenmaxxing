# Primary Quota Activation Policy

**TOKENMAXXING · Shivam Kumawat (@ohnoshivm) × AgentKind Labs**

## Objective

Prevent accidental delays in starting verified first-request-anchored subscription quota windows, without consuming usage unnecessarily or sending through the wrong provider, account or billing path. This is part of TOKENMAXXING's primary subscription-efficiency pillar.

## Mandatory rules

1. Identify provider **instance/account ID**, not just the provider brand or an email; track every session, weekly and model-specific limit independently.
2. Record timezone-aware reset timestamps from a supported provider usage display. Data with unknown or outdated provenance is not sufficient for automatic requests.
3. Classify each window as `first_request`, `fixed`, or `unverified`. **Only `first_request` is eligible** to initiate a new window.
4. Do not trigger any request before reset. Never buy credits, purchase quota resets, use API-billed fallback or change existing OAuth/CLI login on behalf of the user.
5. Use *one* user-configured, verified cheapest **eligible subscription model** with a tiny context-free prompt. No arbitrary changes to routing. Never assume all models on an account share the same pool.
6. Require explicit authorization in the per-account config and at runtime. Reserve a window in persisted state **before** dispatch. Never automatically retry ambiguous failures.
7. A successful command exit is only *sent-pending-verification*. A later provider observation or explicit user-confirmed timestamp is required before setting a new reset.
8. Notify for fixed and unknown semantics, stale observations, ambiguous account identity, missing integrations, missed grace windows, failed attempts and Mac sleep.
9. Preserve secrets, separate T3 Code quota *visibility* from automated *control*, and use documented interfaces only.
10. Benchmark success-adjusted quota availability—not raw count of `yo` messages. Early activation sometimes reduces flexibility rather than adding usable allowance.

## Implementation

[`scripts/quota_engine.py`](../scripts/quota_engine.py), [`config/quota-windows.example.json`](../config/quota-windows.example.json), and [operator guide](../docs/quota-engine.md). This is opt-in local CLI automation, not a T3 plugin or unattended account integration.
