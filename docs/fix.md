# `tokenmaxxing fix` — reversible context cleanup

`fix` turns `audit` and `doctor` findings into actions. Exactly one kind is applied automatically; everything else is a suggestion you run yourself.

```text
python3 tokenmaxxing.py fix                          # dry run: print the plan
python3 tokenmaxxing.py fix --apply                  # move unused skills to the archive
python3 tokenmaxxing.py fix --list                   # past runs
python3 tokenmaxxing.py fix --undo                   # restore the most recent run
python3 tokenmaxxing.py fix --undo 20261021T065028Z  # restore a specific run
```

Options: `--since 30d|7d|24h|all|ISO` (usage window), `--config-dir PATH`, `--project-dir PATH`, `--keep NAME` (repeatable), `--json`.

## What is applied

User skills directly under `<config_dir>/skills/` with **zero** invocations in the window move to:

```text
<config_dir>/tokenmaxxing-archive/<run_id>/skills/<skill-name>/
```

Invocation evidence comes from `audit`'s `skills_used`, which counts both `Skill` tool calls and skills you invoke by hand as slash commands. The action is skipped entirely when the window has fewer than 10 Claude sessions, because zero uses is not evidence at that sample size. `--keep` exempts a name.

Symlinked skills move as links; the target is never touched.

## What is only suggested

| Finding | Why it is manual |
| --- | --- |
| Duplicate skill copies | Which copy Claude Code loads is not determinable from disk, so `fix` names the copies instead of guessing. |
| Stacked optimizers | Prints the `/plugin disable` command for all but the first active optimizer, plus the profile map. |
| Large instruction files | Prints the largest sections by estimated tokens and points at moving them into a referenced file. |
| Doctor findings | Printed with their measured or estimated impact, priority order preserved. |

## Safety and undo

- Dry run is the default. `--apply` executes only actions marked `auto`.
- `manifest.json` is written **before** the first move and updated after each one, so a crash still leaves an undoable record.
- `--undo` moves files back and reports conflicts (for example, a new directory reusing the old path) instead of overwriting them; it then prints what it refused and leaves the run open. Running the same `--undo` again after you resolve the path retries.
- A second `--undo` on a finished run reports `already undone` and changes nothing.
- Nothing is deleted. `settings.json`, authentication and provider configuration are never written.

Token estimates are `doctor`'s metadata estimate (name + description), not a measured per-session reduction.
