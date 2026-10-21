# Cache-cold guard

`guard` is an optional Claude Code `UserPromptSubmit` hook. It reads the latest assistant usage record from the transcript tail using the same cache TTL inference as `statusline`. If the cache has expired and context is at least 50,000 tokens, it blocks that prompt once with a message explaining the estimated resend cost. Re-sending within 120 seconds passes. Slash commands such as `/compact` and `/clear` pass immediately.

Print a hook snippet, then review and merge it into `~/.claude/settings.json` yourself:

```bash
python3 tokenmaxxing.py guard --print-hook
```

The command never edits settings. Configure `--min-context` and `--grace` on the printed command if needed. On a block, Claude Code shows the hook's `reason` to the user; the prompt is not submitted to Claude. UserPromptSubmit also runs for typed slash commands, which is why TOKENMAXXING explicitly lets prompts starting with `/` through.

The hook fails open on malformed input, missing transcripts, or read/write errors. It reads only the transcript tail, adds no output to the allow path, and stores short-lived per-session markers under `~/.claude/tokenmaxxing-guard/`, pruning marker files older than a day. It does not change settings or provider credentials.
