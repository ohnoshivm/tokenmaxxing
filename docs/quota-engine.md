# TOKENMAXXING — Provider Quota Activation Engine (v2)

**Shivam Kumawat (@ohnoshivm) × AgentKind Labs**

This is a **working local quota scheduler** with a conservative bridge for manual, normalized quota data from T3 Code or a provider usage display. It does not claim T3 Chat or T3 Code expose an approved unattended message API. It does not connect to any user account until **you separately configure and opt into** an existing, legitimate subscription-backed CLI command.

## Supported behaviour

- **Per-account and per-window** tracking: each provider instance may have session, weekly, model-specific and other windows, each with its own reset timestamp and timezone.
- **Window semantics:** `first_request` is eligible for optional activation, `fixed` needs no artificial message, and `unverified` alerts only.
- **One attempt per window:** a persisted reservation is made before a command runs; timeouts, exit errors and crashes cannot result in an automatic resend. Related session/weekly windows share one activation within two minutes by default.
- **True state verification:** process exit zero means **sent—pending provider confirmation**, not successful reset. Import the next observed quota snapshot or confirm the new reset timestamp directly from the provider UI. No speculative countdown advancement.
- **Private state:** permissions 0600 for settings, state, logs and lock files; serialized operations prevent overlapping scheduler ticks. No API tokens, prompt transcripts, CLI stdout or stderr are stored.
- **Best effort timing:** one-minute checks on an awake Mac; sleep and provider UI delays mean it is not a 60-second delivery guarantee.

## Quick start

```bash
# Clone or update TOKENMAXXING. Python 3.9+ and macOS/Linux.
python3 tokenmaxxing.py quota setup
# Edit ~/.config/tokenmaxxing/quota-windows.json and replace ALL example dates and IDs.
python3 tokenmaxxing.py quota status
python3 tokenmaxxing.py quota check --dry-run
python3 tokenmaxxing.py quota check             # Notifications only
python3 tokenmaxxing.py quota watch             # Foreground checks every 60 s

# macOS user LaunchAgent: run every minute when Mac is awake
./scripts/install-quota-macos.sh
```

You can run the engine directly using `python3 scripts/quota_engine.py <action>`. To disable the agent, unload and remove its plist as printed by the installer. No global settings, authentication, T3 app data, or provider access is modified by setup.

## Monitor via T3 or a provider's usage panel

T3 Code's **Usage → Limits** can show individual provider account windows with reset times. An active adapter may use provider sessions to refresh limits. This is useful information but **not evidence of an externally supported T3 JSON export or unattended prompt-sending API**. There is no scraping of T3 databases or undocumented private RPC calls here.

Where the user has reliable quota observations, copy *only* non-secret fields into a normalized file matching [`config/usage-snapshot.example.json`](../config/usage-snapshot.example.json), with `provider`, `instance_id`, `observed_at`, `windows[].id`, `windows[].resets_at`, and optional `used_percent`.

```bash
python3 tokenmaxxing.py quota sync --snapshot ~/usage-snapshot.json
python3 tokenmaxxing.py quota status
```

The importer rejects unrecognized instance IDs, requires timezone-aware dates, never merges accounts by display email, and discards unmatched quota windows. It does not infer a window's first-request semantics from the data. Treat manually copied data as trusted only after verifying it against the provider display.

## Auto-activation: only after explicit per-account authorisation

1. Confirm the provider actually starts this particular allowance timer on its first request. For OpenAI's normal five-hour Work/Codex allowance, this behaviour is documented. Do **not** classify Claude or other pools as first-request-anchored based on guesswork. Ordinary fixed weekly resets need no message.
2. Confirm the correct subscription-backed account or T3 provider instance, your provider CLI's supported noninteractive syntax, and the least resource-consuming **eligible** model. Explicitly authorize each supported quota window in `eligible_windows`; unrelated model-specific pools are never activated by the same command. The tool does not auto-rank prices or silently choose another provider.
3. For an eligible account only, set `activation.mode` to `command`, add a verified `activation.argv` array and set `activation.subscription_verified` to `true` and `activation.confirmed_instance_id` equal to the corresponding account's `instance_id`. Example (pseudocode only; not a verified provider command):

```json
"activation": {
  "mode": "command",
  "confirmed_instance_id": "T3_OR_PROVIDER_INSTANCE_ID_FROM_ACCOUNT_SETTINGS",
  "subscription_verified": true,
  "eligible_windows": ["session"],
  "verified_model_id": "VERIFIED_SUBSCRIPTION_MODEL_ID",
  "grace_seconds": 90,
  "argv": ["/absolute/path/to/VERIFIED_SUBSCRIPTION_CLI", "VERIFIED_MODEL_FLAG", "VERIFIED_MODEL_ID", "yo"]
}
```

4. **Opt in again at execution time** with `python3 tokenmaxxing.py quota check --allow-dispatch`, or, for unattended Mac scheduling, deliberately reinstall the scheduler with `./scripts/install-quota-macos.sh --enable-activation`.
5. Keep your Mac awake across the reset. If the command exits zero, status remains **sent-pending-verification**. Verify in the real provider usage panel and sync a later snapshot, or manually record a verified next reset:

```bash
python3 tokenmaxxing.py quota confirm --account codex-personal --window session \
  --next-reset 2026-10-22T14:00:00+05:30
```

Nothing dispatches through paid API fallback. The scheduler strips common API-key and base-URL environment overrides; nevertheless, **it cannot attest to the actual authentication or charging path of arbitrary user-configured CLI commands**. Only enable it after you have verified the CLI's subscription use. For paid resets, never purchase or apply a reset automatically; first activate only after the purchase has already been made and confirmed.

## Limits and safety

- A one-word request may still incur full system-context processing and subscription allowance.
- Without a supported provider usage export, observed reset times must be entered or updated manually. There is **no continuous authenticated polling through T3** in this release.
- Unresponsive providers, CLI timeouts, stale snapshots and missing account identity cannot be interpreted as successful activation.
- Requests are never made for `fixed` or `unverified` windows.
- First-request activation is not always the best decision; intentionally starting a window early may make its next expiry earlier too.
- JSON configuration and log files are stored outside the repository, under your local user account, and should never be committed.

## References

- [OpenAI: Managing usage with GPT-6 Astra in Work and Codex](https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex)
- [OpenAI: Paid weekly Work/Codex rate-limit resets](https://help.openai.com/en/articles/20001507-paid-weekly-work-and-codex-rate-limit-resets)
- [T3 Code: provider quota headroom proposal](https://github.com/pingdotgg/t3code/discussions/8148)
- [T3 Code: user documentation about limited threads and resuming at reset](https://github.com/pingdotgg/t3code/blob/main/docs/user/thread-sidebar.md)
