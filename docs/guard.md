# `tokenmaxxing guard` — stop paying for a cold cache

A prompt cache entry expires after 5 minutes of inactivity (or 1 hour, when the session writes 1h cache). If you come back later and type, the whole prefix is re-sent and rewritten before the model answers. The guard asks once whether that is what you meant.

```text
python3 tokenmaxxing.py guard --print-hook   # print the settings.json snippet
python3 tokenmaxxing.py guard --hook         # hook entry point; reads hook JSON on stdin
```

## Install

`--print-hook` writes nothing. Paste its output into `~/.claude/settings.json` yourself:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command",
        "command": "python3 /path/to/tokenmaxxing.py guard --hook --min-context 50000 --grace 120" } ] }
    ]
  }
}
```

## Behaviour

On every prompt the hook reads the payload (`transcript_path`, `session_id`, `prompt`) and tails the transcript the same way `statusline` does. It allows silently when:

- the prompt starts with `/` (slash commands, including `/compact` and `/clear`);
- there is no assistant turn yet, or the transcript cannot be read;
- the context is below `--min-context` (default 50000 tokens);
- the inferred cache TTL has not expired;
- a warning was already shown for this session less than `--grace` seconds ago (default 120).

Otherwise it writes a marker and blocks once:

```text
Cache cold (idle 14m). Sending re-sends ~129k tokens. Re-send to continue,
/compact to keep going lighter, or /clear for a new task.
```

Re-sending the same prompt inside the grace window passes, which is what makes the rebuild deliberate rather than accidental. The message is shown to you; it is not added to the model's context.

## Safety

- Any parse or read error exits 0 with no output. A guard must never break a session.
- The allow path prints nothing, so it adds zero tokens to model context.
- Only tail-reads: the last 256 KB. Budget is well under 200 ms on a 50 MB transcript (covered by a test).
- Markers live in `<config_dir>/tokenmaxxing-guard/<session_id>.json`, contain only a timestamp, and are pruned after a day.
- `settings.json` is never modified by the toolkit; you paste the snippet.

## Limits

- TTL is inferred from the transcript's cache-write fields; if a session never recorded one, the guard assumes 5 minutes.
- The guard warns; it cannot measure what the rebuild actually costs. `audit` reports cache rebuilds after the fact.
- Hook contract used: `UserPromptSubmit` receives `session_id`, `transcript_path`, `cwd`, `prompt`, `hook_event_name`; exit 0 with `{"decision":"block","reason":...}` blocks the prompt and shows the reason to the user. Slash commands do fire this event, so the guard lets them through explicitly.
