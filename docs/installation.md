# Installation and verification

## Quota Activation Engine (v2, recommended)

From the checkout, run `python3 tokenmaxxing.py quota setup` to create a private sample configuration; edit it with verified provider identities and real reset timestamps. Then use `python3 tokenmaxxing.py quota check --dry-run` and `quota status`. Optional `python3 tokenmaxxing.py quota install-macos` enables notification-only periodic checks on macOS. See [complete operator guide](quota-engine.md). The earlier `reset` engine is still supported.


## Measure before changing your setup

From the repository directory, run the local read-only tools:

```bash
python3 tokenmaxxing.py audit --since 7d
python3 tokenmaxxing.py doctor
python3 tokenmaxxing.py statusline --install
```

`audit` analyzes local Claude Code transcripts and Codex rollouts without uploading data. `doctor` reports always-loaded context and optimizer stacking; it prints MCP names and transports, never secrets. `statusline --install` prints a settings snippet without writing settings. After a change, use `python3 tokenmaxxing.py audit --since 7d --compare` to compare equal windows per turn. See [statusline setup](statusline.md).

## First-class Reset Activation Engine (opt-in)

TOKENMAXXING includes the reset window watcher in its main CLI. After cloning:

```bash
python3 tokenmaxxing.py reset setup
# Enter actual account-specific timestamps in ~/.config/tokenmaxxing/reset-watcher.json
python3 tokenmaxxing.py reset status
python3 tokenmaxxing.py reset check --dry-run
python3 tokenmaxxing.py reset check
python3 tokenmaxxing.py reset install-macos    # optional, macOS notification-only
```

For a combined install run `./install.sh --with-reset-config`: this creates an **inactive** private config and stages the toolkit but does not start a background process or send a request. For a faster offline feature-only setup, run `./install.sh --no-fetch --with-reset-config`.

For first-request-anchored windows, optional provider CLI dispatch requires a reviewed, verified command in the config plus explicit `--allow-dispatch`; the macOS LaunchAgent remains notification-only. See [Reset Activation Engine](reset-activation.md).


## Quick install

```bash
git clone https://github.com/ohnoshivm/tokenmaxxing.git
cd tokenmaxxing
./install.sh
```

Requires Git and Python 3.9+. The launcher uses Python's standard library only. This stages 8 pinned Git repositories under `~/.tokenmaxxing/vendor/` and installs **one reusable local TOKENMAXXING skill** to `~/.claude/skills/tokenmaxxing`. It does not install their dependencies or execute arbitrary upstream code. The resulting installation is intentionally passive until a task or approved plugin invokes it.

Dry-run without changes: `./install.sh --dry-run`.
Only install the portable skill (offline): `./install.sh --no-fetch`.
Project-scoped skill instead of user-scoped: `./install.sh --scope project --no-fetch`.
Inspect pinned sources and skill: `python3 tokenmaxxing.py status`.
List profiles: `python3 tokenmaxxing.py profiles`.
Show the native plugin installation commands for one candidate: `python3 tokenmaxxing.py plugin-commands occam`.

## Native Claude Code plugin installation (no checkout needed)

TOKENMAXXING includes its own minimal Claude Code plugin, containing the **TOKENMAXXING skill only**, with **no hooks, MCP proxies or bundled authentication changes**:

```bash
claude plugin marketplace add ohnoshivm/tokenmaxxing
claude plugin install tokenmaxxing@tokenmaxxing --scope user
```

The plugin approach installs the core skill but **does not stage the external dependency repositories**. For those, use the full Git/CLI bootstrap above. See the CLI version's `claude plugin ... --help` if flags differ. Do not install the same skill twice at the same scope; choose either marketplace plugin or file-based installation.

## What this installer does not do

- It never activates Ponytail, Occam, Chisle or any conflicting external optimization rules automatically.
- It never overwrites `CLAUDE.md`, `.claude/settings.json`, other skills, hooks, MCP servers, OAuth tokens, API keys, T3 Chat or Codex settings.
- It never silently installs `bun`, `uv`, npm packages or other dependencies. Candidate projects may need their own reviewed setup.
- It does not imply official support for any third-party tool or prove benchmark savings.

## Activate one native Claude plugin after reviewing source

Example for a Ponytail trial:

```bash
claude plugin marketplace add DietrichGebert/ponytail
claude plugin install ponytail@ponytail --scope user
```

Before doing this, ensure any active **Occam or Chisle hooks** and similar optimizers are disabled. Use `claude plugin list` and the host's plugin manager to inspect the current state. Native CLI command support depends on your installed Claude Code version. Do not install native Claude plugins into T3 automatically.

## Update strategy

Upstream commits are deliberately pinned in `policy/optimizer-registry.json`. Users should review proposed dependency updates as pull requests to the registry rather than silently pulling arbitrary new code. Already-staged checkouts at a different commit are **not reset or overwritten**.

## Uninstall

Remove the one installed TOKENMAXXING skill `~/.claude/skills/tokenmaxxing` only after confirming it is ours. Optional pinned source checkouts live at `~/.tokenmaxxing/vendor/` and can be removed individually. Existing Claude plugins are independent and are **not** managed or deleted by this installer.

## Quality guarantee boundary

This repository installs an instruction skill and stages upstream projects. It does **not** promise automatic cross-model delegation, guaranteed 20%-50% token savings, or a ready-to-run compatibility matrix for third-party optimizer hooks. Test on disposable benchmark tasks and verify actual outcomes before wider activation.

## GitHub submodule links

The eight upstream repositories are also represented by GitHub submodule links under `third_party/` at pinned commits. This makes dependencies inspectable directly on GitHub while preserving their original repositories and licenses. A normal `git clone` fetches only this project's files; `git submodule update --init --recursive` fetches the linked repos as well. The `./install.sh` bootstrap stages separate user-cache copies for portability, so fetching both is optional and duplicates downloads.
