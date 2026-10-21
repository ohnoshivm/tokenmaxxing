# Reversible fixes

Run `python3 tokenmaxxing.py fix` to preview a plan. It changes nothing. Use `--config-dir PATH` (or `CLAUDE_CONFIG_DIR`) to select a config; usage is measured only from that config's `projects/` transcripts.

```bash
python3 tokenmaxxing.py fix --since 30d --keep review deploy
python3 tokenmaxxing.py fix --since 30d --keep review deploy --apply
python3 tokenmaxxing.py fix --list
python3 tokenmaxxing.py fix --undo           # most recent run
python3 tokenmaxxing.py fix --undo RUN_ID    # a particular run
```

Only unused user skill directories directly under the config's `skills/` directory are automatically archived. At least ten measured Claude sessions are required. Usage includes `Skill` calls and user slash commands; names and directory names in `--keep` are protected. Plugin and project skills are never moved. A skill symlink moves as a link; its target is untouched. An entirely symlinked skills root is skipped.

Duplicate names with ambiguous load precedence stay suggestions. Stacked optimizer suggestions show disable commands and profile mappings; large instruction files show their largest heading sections. Plugin, hook and MCP advice reuses doctor findings. All savings are per-session token estimates from skill metadata; no quality improvement or guaranteed savings is implied.

Archives live at `<config_dir>/tokenmaxxing-archive/YYYYMMDDTHHMMSSZ/skills/<name>`. Before the first move, fix writes a manifest with the source/destination pairs, version and timestamp; it marks each completed move. Undo also recovers a move interrupted before its completion flag was written. A second apply in the same second refuses the existing run rather than overwriting it.

Undo refuses a source that already exists, preserves both copies, and reports the conflict. Move the conflicting new skill somewhere safe and retry undo. Repeated undo is a no-op once complete. Archive directories and the manifest remain as history after restoration; the original skill tree and settings bytes are restored.

Restart Claude Code sessions after apply or undo. `--json` is available for plans, apply, list and undo. No command edits settings, authentication or provider configuration; fix never deletes skills or runs its suggested commands. Historical usage is only a proxy: keep skills needed for infrequent work even when the measured window shows no invocations.
