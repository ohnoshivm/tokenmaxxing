# Cache guard

The guard is an opt-in `UserPromptSubmit` command hook. It estimates cache warmth from the last real assistant usage, using statusline's bounded 256 KiB transcript tail reader and inferred 5-minute or 1-hour TTL. Missing or invalid data silently allows the prompt.

```bash
python3 tokenmaxxing.py guard --print-hook
```

Review the printed JSON and manually merge its `hooks.UserPromptSubmit` entry into your Claude Code settings. The command only prints; it writes no files and never installs hooks or edits settings. It quotes the current Python executable and checkout path. Regenerate the snippet if either moves. Remove this hook entry manually to disable the guard.

The hook reads `session_id`, `transcript_path` and `prompt` from stdin. Slash commands pass immediately. If idle exceeds the inferred TTL and context is at least 50,000 tokens, the hook writes a private marker and blocks once:

```text
Cache cold (estimate; idle 14m). Sending re-sends ~129k tokens. Re-send to continue, /compact to keep going lighter, or /clear for a new task.
```

Re-send within 120 seconds to proceed, or choose `/compact` or `/clear`. A later submission after the grace interval can block again if the cache is still cold. Override thresholds when generating the snippet with `--min-context 50000 --grace 120`.

Markers live in `<config_dir>/tokenmaxxing-guard/`, where the config comes from `CLAUDE_CONFIG_DIR` or `~/.claude`. Names are hashes of session IDs; markers contain only timestamps. Markers older than a day are pruned when checking a cold, large context. The guard never reads credentials or modifies settings. A marker failure allows the prompt; it cannot strand a session. Allow paths emit no stdout or stderr and add zero model-context tokens. The test suite measures the whole CLI subprocess against a 50 MB synthetic transcript with a 200 ms limit.

The [official hooks reference](https://code.claude.com/docs/en/hooks#userpromptsubmit) was checked on 2026-10-21 (the requested `docs.claude.com` URL redirects there): `UserPromptSubmit` receives the submitted prompt plus common session/transcript fields; JSON `decision: "block"` stops submission and `reason` is shown to the user without entering model context. Skill and custom slash commands reach this hook as typed, before expansion. Local built-in commands may be handled by Claude Code directly; any slash prompt delivered to the guard bypasses it. The block output also requests `suppressOriginalPrompt` so the hook does not echo the submitted prompt in its block message. The grace marker implements block-once; warn-only fallback is unnecessary under this contract.
