# Reset Activation Engine

**TOKENMAXXING — Shivam Kumawat (@ohnoshivm) · AgentKind Labs**

This optional module watches known subscription allowance reset times and helps you begin a **new activity-anchored window** promptly with the cheapest supported subscription-backed model. Its default action is a macOS notification, **not a model call**.

## Integrated TOKENMAXXING CLI (recommended)

Reset activation is a **first-class optional TOKENMAXXING feature**. The CLI
wraps the same audited watcher; no provider requests or daemons start by default.

```bash
# From the checked-out TOKENMAXXING repository:
python3 tokenmaxxing.py reset setup               # Create private example configuration, no overwrite
# Edit ~/.config/tokenmaxxing/reset-watcher.json with real provider/account windows.
python3 tokenmaxxing.py reset status              # Show known windows
python3 tokenmaxxing.py reset check --dry-run    # Preview eligibility without marking windows consumed
python3 tokenmaxxing.py reset check              # Notification-first one-time check
python3 tokenmaxxing.py reset watch              # Poll while this foreground process runs (>=60s)
python3 tokenmaxxing.py reset install-macos      # Optional 60s notification-only LaunchAgent
# After sending the real first request yourself:
python3 tokenmaxxing.py reset ack --account codex-main-session
```

During the normal toolkit install, `./install.sh --with-reset-config` will also
create the **inactive** example config without registering background services.
It deliberately does **not** read T3 quota timestamps automatically, send `yo`,
install a CLI provider, or alter existing authentication. Automatic model calls
are only possible after configuring a verified account-specific command **and**
passing `--allow-dispatch` to a manually run watcher/check; the bundled macOS
LaunchAgent never uses that flag. See the security requirements below.

## Why not ping every reset?

Providers use different clocks. A fixed weekly reset does not need any activation, and a gratuitous message will simply consume allowance. Only an **activity-anchored** window can benefit from a timely first request, and even then a premature request may start its usable window earlier than you need. A message containing `yo` can still incur agent startup, system prompt, tooling and cache overhead: prefer a fresh, lightweight conversation with no unnecessary tools.

### Documented behaviour as of 21 October 2026

| Pool | Reset semantics | Decision |
| --- | --- | --- |
| Work/Codex session (normally 5 hours when applicable) | OpenAI documents that the next 5-hour window starts on the first request after the previous window ends | Candidate for activation when user explicitly wants it |
| Work/Codex weekly following a **purchased reset** | OpenAI documents that next weekly period begins with first subsequent request; next reset follows 7 days after that request | Configure separately only for eligible purchased resets |
| Ordinary Claude weekly | Anthropic states fixed reset day/time independent of when you use the product | **Never auto-prime just to start the clock** |
| Claude 5-hour session | Anthropic documents 5-hour reset; verify precise start behaviour and next reset on the specific account | Notification until verified |
| T3 or another 4-hour plan | Provider-specific, not an automatic T3-wide feature | Notification until verified |

Sources:
- [OpenAI: Managing GPT-6 Astra in Work/Codex](https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex)
- [OpenAI: Paid weekly Work/Codex resets](https://help.openai.com/en/articles/20001507-paid-weekly-work-and-codex-rate-limit-resets)
- [Anthropic: Claude Pro reset schedule](https://support.claude.com/en/articles/8325606-what-is-the-pro-plan)
- [T3 Code: Usage → Limits and refresh frequency](https://github.com/pingdotgg/t3code/blob/main/docs/user/usage.md)

T3 Code documents **Usage → Limits**, plus `/usage-limits`. Its automatic provider checks are throttled for at least five minutes per connected environment. Neither the research nor this module proves there is a public T3 Chat messaging API that can initiate a provider request to the desired account. This module doesn't scrape private T3 endpoints or silently control its UI.

## Install and configure (macOS; Python 3.9+)

From the cloned TOKENMAXXING repository:

```bash
mkdir -p ~/.config/tokenmaxxing
cp config/reset-watcher.example.json ~/.config/tokenmaxxing/reset-watcher.json
${EDITOR:-nano} ~/.config/tokenmaxxing/reset-watcher.json
python3 scripts/reset_watcher.py status
python3 scripts/reset_watcher.py check --dry-run
python3 scripts/reset_watcher.py watch
```

**Replace the example dates with confirmed next-reset times** from your provider's Usage page or T3 Code Usage → Limits view. Include an ISO8601 timezone offset. Use the actual provider-reported reset duration; do not hardcode 4 or 5 hours for every account.

Once ready, on macOS, you can create a per-user LaunchAgent that checks every 60 seconds:

```bash
./scripts/install-reset-watcher-macos.sh
```

This is **notification-only**. It does not grant a model allowance, automatically change the reset clock, modify T3/Claude/Codex credentials, or spend API credits. It runs only while the user's macOS session is active; sleep, offline time and application/provider outages may delay it.

## Explicit opt-in CLI activation

**No auto-message is enabled by default.** Set one eligible account to `"semantics": "first_request"` and `"dispatch": "command"`, supply the **tested** command as an argv array, and run:

```bash
python3 scripts/reset_watcher.py check --dry-run --allow-dispatch
python3 scripts/reset_watcher.py watch --allow-dispatch
```

- Choose the cheapest **actually available under the intended subscription** (`gpt-6-luna` for eligible Codex usage, Haiku for eligible Claude accounts) and a tiny prompt such as `yo`.
- The command must select the **specific account**, model and billing method; test this outside the watcher first. A provider CLI can be signed into the wrong account or use API billing. Never assume a model name or effort level is supported.
- The command is executed as an argument array with **no shell expansion**. Never paste untrusted commands into the config.
- This module cannot guarantee T3 Chat conversation creation. A CLI request may activate provider usage but will not automatically appear as a T3 Chat conversation.
- Keep `--allow-dispatch` out of the LaunchAgent until you deliberately opt in and independently verify the provider CLI works as intended.
- If reset time is missed by more than `grace_seconds` (default 120 seconds), the engine **will not automatically ping late**. It will alert you for a manual decision.

When **you** send the first request manually after a scheduled reset, acknowledge it so the *estimated* next activity-anchored window can be scheduled:

```bash
python3 scripts/reset_watcher.py ack --account codex-main-session
```

You may give `--at 2026-10-22T09:01:00+05:30` for the actual first-request timestamp. The next estimated reset is computed from that time plus `window_hours`; confirm it from the provider UI whenever possible.

## Safety and reliability

- Separate providers/accounts/windows. Do not trigger multiple accounts just because one reset.
- Deduplicate every reset event using a local 0600-permission state file at `~/.local/state/tokenmaxxing/reset-watcher-state.json`.
- User confirmation, not agent improvisation, is required before automatic model calls.
- No polling of undocumented APIs, cookies, OAuth session secrets or T3 internals.
- No paid API fallback; if the account and subscription cannot be verified, stick to notification mode.
- In ordinary usage, activating an unused five-hour window earlier is not necessarily optimal. It is appropriate only when you want the five-hour cadence to begin immediately.
- Report the actual first message and updated provider reset timestamp, not an assumed success.

## Limitations

The watcher currently requires manual reset timestamps. It does not continuously discover changes to provider limits. It can auto-advance **activity-anchored** windows after a CLI command exits successfully, but an exit code alone does **not** verify that the provider started the intended quota window; fixed weekly schedules advance by seven days. The user must refresh dates after provider policy/account changes. Exactly-once dispatch cannot be guaranteed if the process crashes between a successful provider request and writing the state file; provider deduplication is not exposed. A real minute-accurate live reset-detection integration requires a stable, authorised provider interface and provider-specific adapter.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_reset_watcher.py' -v
```

For more about Claude Code / T3 token efficiency, see [token-efficiency policy](../policy/token-efficiency.md) and [routing policy](../policy/routing-policy.yaml).
