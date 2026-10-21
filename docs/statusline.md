# Claude Code status line

`tokenmaxxing statusline` reads Claude Code's status JSON from stdin and the tail
of its transcript. It displays the latest assistant turn's context size, cache
warmth, cache-read hit ratio, and a `/compact` prompt when the context is large.

Example:

```text
Opus 5.5 · ctx 84k/200k ▓▓░░░ · cache warm 3:12 · hit 97%
Opus 5.5 · ctx 129k/200k ▓▓▓░░ · cache cold — next turn rewrites ~129k · hit 100% · consider /compact
```

## Fields

- **ctx** adds `input_tokens`, `cache_read_input_tokens`, and
  `cache_creation_input_tokens` from the latest real assistant usage record.
- **Cache warm** counts down from the assistant message timestamp. The TTL is
  60 minutes when the latest recent cache write used the 1-hour TTL; otherwise
  it is 5 minutes. When cold, the line estimates how many tokens the next turn
  may need to rewrite.
- **hit** is the share of that context served from the prompt cache.
- At 60% of the context window, the line suggests `/compact`; at 85%, it says
  `/compact now`. Window size comes from stdin when available, otherwise it is
  1,000,000 for model IDs containing `[1m]` and 200,000 for other models.

Prompt-cache warmth matters because an idle session can outlive its cache TTL.
The next turn may then pay to write the full prompt prefix again. The countdown
makes that idle window visible; it is a timing estimate, not a cache guarantee.

## Install

Run `python3 /path/to/tokenmaxxing.py statusline --install` to print the
settings snippet. It does not edit settings files. Add the printed object to
`~/.claude/settings.json`:

```json
{"statusLine": {"type": "command", "command": "python3 /path/to/tokenmaxxing.py statusline"}}
```

Only one status line can be active in Claude Code. If one is already configured,
`--install` reports and displays it. Use `--ttl 5m` or `--ttl 1h` to override the
inferred TTL, `--window N` to override the window size, and `--no-color` (or the
`NO_COLOR` environment variable) to disable ANSI colors.

## Limitations

This is an estimate based on the latest assistant usage record found in the
last 256 KiB of the transcript. The display refreshes on conversation events,
so its countdown is as of the last refresh and does not tick continuously.
