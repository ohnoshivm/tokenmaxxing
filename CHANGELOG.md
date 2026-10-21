# Changelog

**Created by [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

## 1.5.0 — 2026-10-21

- Added offline, read-only `audit`, `doctor` and `statusline` commands for local usage measurement, fixed-overhead inspection and live cache/context awareness.
- Added equal-window `audit --compare` with compact values, signed changes and direction-aware labels; fixed doctor's tilde/relative config-path resolution and covered CLI section totals.
- Replaced the research-wall README with a scannable toolkit guide and moved the original long-form research into `research/delegation-paper-2026.md`.
- Updated skill guidance, installation and quick-start docs, release metadata and CI coverage.
- No transcript content is uploaded; audit and doctor do not modify provider authentication, MCP servers, hooks or settings.

## 1.4 — 2026-10-21

- Integrated Reset Activation Engine directly into `tokenmaxxing.py reset` (setup/status/check/watch/ack/install-macos).
- Added opt-in `./install.sh --with-reset-config` to create a private, notification-only configuration safely.
- Added integrated CLI usage to the README, skill, quick-start, installation guide and reset guide.
- Added 7 CLI integration tests; 23 total local unit tests passed.
- No provider authentication, T3 configuration or paid API routing was modified. No background scheduler was installed on the user's machine.

## 1.3 — 2026-10-21

- Added **Reset Activation Engine** as the third primary TOKENMAXXING pillar.
- Added a provider-aware, notification-first reset watcher, ISO timezone handling, fixed vs first-request anchored rules, deduplication, bounded opt-in CLI dispatch, manual acknowledgments, and minute-level macOS LaunchAgent support.
- Published a concise master prompt, reset-activation policy, example configuration and operator manual.
- Passed 11 local unit tests covering timing, state protection, auto-dispatch safeguards, fixed reset behaviour and duplicate prevention.
- **No provider has been contacted and no T3/Claude/Codex authentication, subscriptions or global settings have been modified.**

## 1.2 — 2026-10-21

- Added one-command `./install.sh` bootstrap and a Python standard-library-only installer with read-only dry runs, pinned upstream checkouts, status and profile discovery.
- Added native Claude Code marketplace plugin packaging for the project's token-efficiency skill.
- Added eight third-party optimizer sources as pinned GitHub submodules with an attribution-preserving dependency registry; external source code is not vendored or relicensed.
- Added five task-specific optimizer profiles, T3 Chat host-compatibility instructions, reusable skill, feature-completeness research, installation/verification instructions and automated installer tests.
- Promoted **Ponytail vs Occam vs Whittle vs Chisle** to a controlled optimizer-comparison track, with skill-discovery gating via Master of Tokens as an optional experiment.
- No external optimizer auto-activation, API routing changes, auth changes, MCP replacement or user-device installation is claimed. Local unit tests passed before publication.

## 1.1 — 2026-10-21

- Promoted Claude Code token-maxxing to an equal primary pillar alongside model delegation.
- Added the full 2026 Claude Code optimization research under `research/`.
- Added `policy/token-efficiency.md` with safe default workflow, evidence tiers, provider/platform distinctions and controlled trials.
- Linked the research from the top of the README, project instructions and quick-start guide.
- Preserved all prior model-routing choices and existing files.

**Verification status:** These additions document research and operating policy; they do not imply plugins have been installed or benchmarked on the user's T3/Claude environments.

## 1.0 — 2026-10-21

- Collected and rechecked benchmark comparisons using Artificial Analysis as the primary source.
- Documented the full five-effort Claude Sonnet/Opus comparison including output tokens, reasoning tokens and weighted API cost/task.
- Set Claude Opus 5.5 Medium as default high-level intelligence instead of Sonnet High.
- Selected GPT-6 Luna High as bounded implementation default, GPT-6.1 Sol High as advanced engineering escalation, GPT-5.6 Luna and Haiku as repetitive executors.
- Kept DeepSeek V4.1 Flash 1017 inactive pending legitimate provider access and testing.
- Added T3 Chat versus T3 Code capability caveat and manual handoff baseline.
- Created reference routing YAML, compact project instructions, task/handoff/review contracts and blank evaluation scorecard.
- Added LinkedIn and X publication drafts.

**Installation status:** no changes made to the user's device, subscriptions, credentials or T3 configuration.

## Publication credits

- Added creator credit for [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) and project credit for AgentKind Labs.
- Added `CREDITS.md` and `CITATION.cff`.
