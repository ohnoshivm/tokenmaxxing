# Reversible fixes

`python3 tokenmaxxing.py fix` reviews local `doctor` and `audit` findings and plans safe changes. It is a dry run by default. Unused user skills are considered only after the window contains at least 10 Claude sessions; `--keep NAME` exempts a skill. Plugin and project skills are not archived. Same-scope duplicates that cannot be resolved safely, optimizer stacking, and large instruction or configuration overhead are suggestions only.

```bash
python3 tokenmaxxing.py fix --since 30d
python3 tokenmaxxing.py fix --since 30d --apply
python3 tokenmaxxing.py fix --list
python3 tokenmaxxing.py fix --undo                 # restore the latest run
python3 tokenmaxxing.py fix --undo 20261021T120000Z
```

Apply moves eligible skill directories under `~/.claude/tokenmaxxing-archive/<RUN_ID>/skills/` and writes a manifest before moving anything. Undo moves completed entries back and refuses to overwrite a skill that has reappeared. A second undo is a no-op. Symlinked skills are moved as links; their targets are left alone.

`fix` never deletes files or writes `settings.json`, credentials, or provider configuration. Read the dry-run plan before using `--apply`; the archive and manifest remain available until you choose to remove them yourself.
