# Claude Code Token-Maxxing: 2026 Research Report

> **Primary TOKENMAXXING research pillar — Claude Code token efficiency.**
>
> **Curated for publication by [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs.**
> This is a research snapshot supplied on 21 October 2026. Referenced projects and third-party benchmarks retain their own authorship; specific tool versions, quoted statistics and compatibility claims should be rechecked before adoption. This document is **not** a report of completed installation or independent replication by TOKENMAXXING.
>
> **Operational summary:** Prefer native caching, targeted context retrieval, concise project instructions, on-demand skills and task-level measurements. Evaluate Ponytail, LSP, ast-grep, Serena, Context7 and context compressors only when justified by your repository. A smaller tool response is not necessarily a cheaper successful task. **CLI-specific Claude Code settings do not automatically apply to T3 Chat.**
>
> [Return to the main research](../README.md) · [Token-efficiency policy](../policy/token-efficiency.md)


Research cut-off: 21 October 2026 · Focus: capability retained per token, not just smaller model outputs

## Executive verdict

The best way to reduce Claude Code's token consumption is not to install every optimization plugin. It is to reduce how much irrelevant information Claude receives, preserve reusable prompt-cache prefixes, and prevent unnecessary agent steps without removing the information required to solve the problem.

My recommended architecture is:

Claude Code — current release

Native caching, compaction, deferred MCP tools

Short CLAUDE.md + on-demand skills

Minimal permanent instructions

Native LSP code intelligence

Precise navigation and diagnostics

One selected optimization tool

RTK or LeanCTX

Do not combine until measured separately

Optional Serena + Context7

Only when codebase size or documentation work justifies them

Measurement + correctness checks

Cost, cache misses, steps, latency, tests

The central research finding is that Claude Code itself now provides several functions that older token-saving tools attempted to add: deferred MCP tool loading, explicit cache controls and observability, native LSP plugins, hooks capable of replacing tool outputs, and idle-session compaction. Extra tools must outperform this native baseline to justify their overhead. 

## 1. What the actual evidence says

One of the most relevant findings is an October 2026 independent testing project, [token-optimization-research](https://github.com/merlinhu1/token-optimization-research).

It tested 15 optimizers across Claude Code, Codex and OpenCode, using real bug-fixing tasks in JavaScript and Python repositories, with 121 provider-side sessions overall. Its results measure weighted token cost, not simply raw token counts. The weights account for fresh input, cheaper cached input and more expensive output. 

Measured Claude Code savings on the Fastify JavaScript fixture

Reduction in weighted token cost against the matched control; two treatment runs each. These are not independently guaranteed savings for other repositories.

*The pasted chart labels were not machine-readable; consult the linked source for its measured values.*

Source: independent repeat-run screening. The figures describe one repository/runtime combination, not average performance across all coding tasks. 

The researchers found no optimizer that cleared their confirmation threshold on the Python fixture. Moreover, two runs per treatment are too few to establish general reliability; the untreated Python runs showed substantial variability. This is useful comparative evidence, but it does not justify promising a universal 25%, 50%, or 90% reduction. 

Three conclusions follow:

1. Output compression works, but per-command compression should never be confused with whole-session savings.
2. Symbol-aware retrieval can help substantially, particularly on tasks that would otherwise require broad file reads.
3. Reducing agent steps matters as much as reducing context per step. A tool that saves input tokens but causes retries, missed dependencies, or debugging mistakes can increase total consumption.

The rest of the report evaluates tools against those distinctions.

## 2. The strongest independent research changes the rankings

Before choosing any plugin, I would give greater weight to the following studies than to GitHub marketing claims.

# 2,848

runs analyzed

[Token Reduction Is Not Cost Reduction](https://arxiv.org/abs/2607.12161) — July 2026

Across seven repositories and three models, a compression treatment removed 38.4% of estimated raw tool-output tokens but increased paired cost by 6.8%. The study also documented failures caused by altering exact text needed for edits. This is a research preprint, not a universal benchmark of every optimizer. 

# +7.6%

cost with RTK

[JetBrains RTK evaluation](https://blog.jetbrains.com/ai/2026/07/rtk-claude-code-token-savings/) — July 20, 2026

In the low-effort benchmark, RTK increased cost and agent steps despite reducing many individual command outputs. The high-effort evaluation found no meaningful cost improvement. JetBrains tested an older pinned RTK version, so later improvements remain possible but unproven by this test. 

# −10.3%

cost with Ponytail

[JetBrains Ponytail evaluation](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/) — July 28, 2026

In 80 paired tasks, Ponytail reduced the median cost by 10.3% and generated code by about 15%, with no statistically detectable change in task score. The study explicitly could not establish equivalent security or accessibility outcomes. The current Ponytail 5 version is newer than the tested release. 

# +6–118%

LSP token range

[Does a Language Server Save Tokens?](https://arxiv.org/abs/2608.13568) — 2026 preliminary study

For straightforward symbol localization, LSP consumed more tokens than lexical search in the tested cases. It offered more precise references for other tasks, but not guaranteed savings. The right policy is adaptive retrieval, not always forcing semantic search. 

This also resolves an important conflict between the smaller October optimizer study and the larger JetBrains results: RTK's positive result in two Fastify runs is real for those runs, but the broader independent evidence is less favorable. I would not make RTK part of the default stack.

For community evidence, I also examined the [r/ClaudeCode discussion of the JetBrains tests](https://www.reddit.com/r/ClaudeCode/comments/1v3b81w/jetbrains_analyzed_the_caveman_and_rtk_token/), [r/ClaudeAI discussion of cache and context costs](https://www.reddit.com/r/ClaudeAI/comments/1r6buxo/how_do_you_guys_keep_token_consumption_down_in/), and [Hacker News discussion of persistent context](https://news.ycombinator.com/item?id=47500715&utm_source=chatgpt.com). They reveal practical concerns about compaction, repeated reads and unreliable saving claims, but not controlled measurements. I did not find a sufficiently verifiable X-only benchmark that deserves equal weight to the studies above.

## 3. Ranked shortlist: 18 candidates

### Scoring methodology

Each candidate receives nine ratings from 1 to 10. A higher score always means better.

| Code | Criterion                                | Weight |
| ---- | ---------------------------------------- | ------ |
| S    | Actual or plausible total token savings  | 21%    |
| P    | Capability preserved                     | 18%    |
| R    | Reliability                              | 11%    |
| M    | Maturity                                 | 7%     |
| U    | Maintenance/activity                     | 6%     |
| I    | Ease of installation                     | 9%     |
| E    | Evidence quality                         | 14%    |
| C    | Current Claude Code compatibility        | 9%     |
| O    | Low additional overhead or conflict risk | 5%     |

These are my evidence-weighted assessments, not published benchmark scores. An evidence score can be high even when a study finds negative savings. Rankings also factor in practical suitability, not just the mathematical total.

Score groups: S/P/R · M/U/I · E/C/O. Overall is the weighted average out of 10.

| Rank | Tool / method                                                                                            | S/P/R   | M/U/I    | E/C/O   | Overall |
| ---- | -------------------------------------------------------------------------------------------------------- | ------- | -------- | ------- | ------- |
| 1    | Claude native caching/context                                                                            | 9/10/10 | 10/10/10 | 9/10/10 | 9.7     |
| 2    | Minimal CLAUDE.md + skills                                                                               | 8/9/10  | 10/10/10 | 7/10/10 | 9.0     |
| 3    | [Ponytail](https://github.com/DietrichGebert/ponytail)                            | 7/9/8   | 8/10/9   | 9/10/7  | 8.4     |
| 4    | [ast-grep](https://github.com/ast-grep/ast-grep)                                  | 6/9/10  | 10/9/9   | 6/10/9  | 8.2     |
| 5    | [Official LSP plugins](https://code.claude.com/docs/en/plugins/code-intelligence) | 5/9/9   | 9/9/9    | 8/10/8  | 8.1     |
| 6    | [Serena](https://github.com/oraios/serena)                                        | 8/9/7   | 9/9/7    | 7/9/5   | 7.9     |
| 7    | [Context7](https://github.com/upstash/context7)                                   | 6/9/8   | 9/9/9    | 5/10/7  | 7.7     |
| 8    | [LeanCTX](https://github.com/yvgude/lean-ctx)                                     | 9/8/6   | 6/8/7    | 6/9/5   | 7.4     |
| 9    | [Cartog](https://github.com/jrollin/cartog)                                       | 8/9/7   | 4/8/7    | 6/9/5   | 7.4     |
| 10   | Caveman                                                                                                  | 4/7/9   | 6/8/9    | 9/9/8   | 7.3     |
| 11   | [RTK](https://github.com/rtk-ai/rtk)                                              | 2/7/7   | 9/10/9   | 10/10/8 | 7.2     |
| 12   | [Muvon Octocode](https://github.com/Muvon/octocode)                               | 7/8/7   | 5/8/7    | 5/9/5   | 6.9     |
| 13   | [Repomix](https://github.com/yamadashy/repomix)                                   | 4/8/9   | 10/10/9  | 3/10/4  | 6.9     |
| 14   | [Token Savior](https://github.com/mibayy/token-savior)                            | 8/7/6   | 6/7/6    | 5/9/4   | 6.7     |
| 15   | [grepai](https://github.com/yoanbernabeu/grepai)                                  | 7/8/7   | 6/7/6    | 3/9/5   | 6.5     |
| 16   | [Headroom](https://github.com/headroomlabs-ai/headroom)                           | 8/7/5   | 7/9/6    | 4/8/3   | 6.5     |
| 17   | [claude-mem](https://github.com/thedotmack/claude-mem)                            | 5/8/6   | 9/10/7   | 3/9/4   | 6.4     |
| 18   | [Cozempic](https://github.com/Ruya-AI/cozempic)                                   | 7/4/3   | 4/7/5    | 2/7/3   | 4.7     |

My practical deployment order differs slightly from the table: use native features, short instructions and Ponytail first. Add ast-grep or LSP only when a task calls for them. Evaluate Serena and LeanCTX in separate experiments.

### High-confidence: genuine mechanisms, limited promises

[Ponytail（马尾辫）：给AI编程助手装上"老司机"思维，代码量直减80%，成本低47%，速度快3到6倍-AI工具推荐-AI工具导航](https://images.openai.com/static-rsc-4/2ZjKXPQdu7CKHoqFAH051EWfwA934GwFLWb_XPq2viq-opGRvZ6NI68rmX20xnh3v3CJQJfWMBOsQlEbCmVC-ndOlZi7__45UDRC6p2qNyNw2r6rfv2MdfGgjURc1YGORXtQnBUAeA0dfal0qiv9QkZiPZKMLOlt3dpMiq8Vwbs?purpose=inline)

1\. [Ponytail](https://github.com/DietrichGebert/ponytail) — best independently tested behavior optimizer

It reduces unnecessary implementation complexity: redundant abstractions, duplicate helpers, needless dependencies and oversized solutions. Saves generated code, output tokens and potentially future read/rework tokens. Around 169k GitHub stars and continued 2026 development at the time checked. Latest project claims exceed what independent testing proves. Overhead: an always-on ruleset and lifecycle hooks; risk: oversimplifying where complexity is justified.

Install: yes, but evaluate on complex UI/engineering work separately. 

2\. [ast-grep](https://github.com/ast-grep/ast-grep) — safest structural-search utility

Tree-sitter-based AST pattern matching. Targets actual code structures rather than dumping broad regex results. Saves tool-result tokens when queries are structurally precise. It is mature, maintained and requires no MCP server. There is no convincing universal end-to-end cost benchmark. Overhead: little model context, but Claude must know when to call the CLI.

Install: yes for code-heavy work, without a second AST-search MCP layer. 

3\. [Official LSP code intelligence](https://code.claude.com/docs/en/plugins/code-intelligence) — capability upgrade, conditional token saver

Provides go-to-definition, references and diagnostics using a real language server. Saves exploration when the relevant symbol is known and improves type-error feedback. Can consume more tokens for simple searches. No separate MCP server is necessary; official plugins support terminal Claude Code.

Install: yes for the main project language, but keep `rg` available and never mandate LSP for every search. 

Native `/clear`, `/compact`, `/rewind`, deferred MCP tools, caching and selective skills rank even higher than these external projects because they introduce almost no additional operational risk.

### Promising: substantial upside, insufficient proof of general savings

| Project                                                                       | Token-saving mechanism                                                   | Evidence, maturity and trade-offs                                                                                                                                                                                               | Verdict                               |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| [LeanCTX](https://github.com/yvgude/lean-ctx)          | Context gateway, selective retrieval, shell-output compression, indexing | Independent −35.4% weighted cost on the Fastify Claude fixture (n=2); no established win on Python. Multiple interacting mechanisms and optional proxy increase complexity.                                                     | Top experimental optimizer            |
| [Serena](https://github.com/oraios/serena)             | LSP-backed symbol-level reads and edits; avoids whole-file loads         | Independent −24.4% on one fixture (n=2). Established project with roughly 30k stars. Additional MCP tools and onboarding context; GitHub issues report integration and tool-adoption friction.                                  | Best large-codebase candidate         |
| [Context7](https://github.com/upstash/context7)        | Retrieves bounded, relevant library docs                                 | Mature, current and officially documented Claude integration. No strong measured total-session saving. External service and an extra retrieval step.                                                                            | Use for unfamiliar/changing APIs      |
| [Cartog](https://github.com/jrollin/cartog)            | Local AST/dependency graph and compact code-location results             | Independent −23.5% on one fixture (n=2); vendor's compact-payload claims concern returned text, not total cost. Smaller community and indexing maintenance.                                                                     | Test instead of Serena                |
| [Muvon Octocode](https://github.com/Muvon/octocode)    | Local semantic search, AST graph, hybrid search and optional LSP         | Reproducible repository-retrieval benchmarks, including 127 annotated code queries, but these are self-evaluations of retrieval accuracy, not token cost. Around 500 stars and active October development.                      | Worth an advanced trial               |
| [Token Savior](https://github.com/mibayy/token-savior) | Symbol navigation, stored memory and Bash command rewriting              | Independent −25.6% on one fixture (n=2). Vendor's much larger savings benchmark isn't publicly reproducible; its README acknowledges a withdrawn measurement where MCP tools were almost never called. Overlaps Serena and RTK. | Test alone, not in default stack      |
| [grepai](https://github.com/yoanbernabeu/grepai)       | Local embeddings and semantic retrieval                                  | Useful for concept queries, but requires index/embedding infrastructure; no compelling independent end-to-end token study located.                                                                                              | Only for semantically difficult repos |

Evidence: 

### Experimental or low-value for token-maxxing

| Project                                                                        | What it actually does                        | Why it is not in my default stack                                                                                                                         |
| ------------------------------------------------------------------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [RTK](https://github.com/rtk-ai/rtk)                    | Condenses common shell command output        | High tool-output compression, but larger independent evaluation found no total-task saving and some regressions.                                          |
| [Headroom](https://github.com/headroomlabs-ai/headroom) | Compression library, MCP and API proxy       | Potentially powerful for massive JSON/log retrieval, but proxying changes the request path, carries cache/compatibility risk and needs independent proof. |
| [claude-mem](https://github.com/thedotmack/claude-mem)  | AI-generated persistent session memory       | Valuable for recurring projects; its storage, summarization and re-injection introduce extra calls and context. Not proven as a token saver.              |
| [Repomix](https://github.com/yamadashy/repomix)         | Packs repository content into one output     | Excellent for deliberate context exports; default whole-repo packing can be an enormous context expense.                                                  |
| [Cozempic](https://github.com/Ruya-AI/cozempic)         | Aggressive pruning of Claude session history | Direct history modification creates correctness, cache and compatibility risks.                                                                           |
| Caveman                                                                        | Forces unusually short language              | JetBrains measured only 8.5% lower output tokens, not the advertised 65%, under forced activation. Can reduce useful explanations.                        |

Additional sources: 

## 4. The recommended stack

I would deploy it in three tiers.

## Tier 1 — Essential

Deploy first

Current Claude Code, native prompt caching and deferred MCP tools, a compact CLAUDE.md, on-demand skills, Ponytail in normal mode, and built-in usage measurement.

No custom API proxy. No permanent memory daemon. No forced semantic-search policy.

## Tier 2 — Workflow dependent

Official LSP for TypeScript/Python/Rust or the relevant language; ast-grep for structural patterns; Context7 for current third-party APIs; Serena for genuinely large symbol-heavy codebases.

Start with LSP and CLI search. Introduce Serena only if the baseline is spending excessive calls finding code.

## Tier 3 — Controlled experiments

LeanCTX, Cartog, Token Savior, Muvon Octocode, RTK and Headroom.

Evaluate each as a single treatment. Keep only a tool that improves cost per verified successful task on your actual repository.

### Architecture and retrieval routing

The essential change here is query-dependent retrieval. A symbol rename should not be handled like an architectural concept search. A stack that forces every task through semantic embeddings, dependency graphs and an LSP usually adds tool calls instead of eliminating them.

## 5. Exact installation: minimal recommended build

Commands below target macOS with Homebrew, with Claude Code running in a terminal. Execute them on your Mac; this research did not install or modify anything on your machine.

### Step 1 — Baseline and backup

Before installing optimization layers, record the current version and MCP setup.

```
claude --version
claude doctor
claude mcp list

mkdir -p "$HOME/.claude"

if [ -f "$HOME/.claude/settings.json" ]; then
  cp "$HOME/.claude/settings.json" \
    "$HOME/.claude/settings.json.backup.$(date +%Y%m%d-%H%M%S)"
fi
```

The official release feed listed Claude Code v2.1.304 on October 19, 2026. Use `claude update` if your installation is behind, then recheck the version. Newer versions have important changes to caching, MCP deferred loading and hooks. 

Inside Claude Code run:

```
/context
/usage
/mcp
```

Record how much of the context is consumed by instructions, tool definitions and conversation history.

### Step 2 — Install Ponytail

GitHub: [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)

Inside Claude Code, run these separately:

```
/plugin marketplace add DietrichGebert/ponytail
```

```
/plugin install ponytail@ponytail
```

Restart or reload plugins as instructed by Claude Code. Use:

```
/ponytail full
```

Use `/ponytail lite` for work where simplification should be conservative, or `/ponytail off` to run your baseline comparison. The repository documents these commands and uses lifecycle hooks to keep the behaviour active. Do not merely copy its SKILL.md and assume automatic activation. 

Verification: confirm Ponytail is active in a new session and test it on a feature that could tempt the agent to add dependencies, abstractions and redundant components. Check tests, behavior, accessibility and final complexity, not just line count.

Revert: `/ponytail off` disables its behaviour for comparison. Uninstall the plugin through Claude Code's `/plugin` manager if you decide not to keep it.

### Step 3 — Install ast-grep

GitHub: [ast-grep](https://github.com/ast-grep/ast-grep)

```
brew install ast-grep
sg --version
```

Example TypeScript structural search:

```
sg -p 'console.log($$$ARGS)' -l ts
```

Use it for exact syntactic structures; continue using `rg` for filenames, string references, comments and straightforward text.

Verification: run one structural query and compare its useful matches with the output of an equivalent broad grep.

Revert:

```
brew uninstall ast-grep
```

### Step 4 — Official TypeScript/JavaScript LSP

Use this for TypeScript or JavaScript projects.

```
npm install -g typescript-language-server typescript
which typescript-language-server
```

Inside Claude Code:

```
/plugin install typescript-lsp@claude-plugins-official
```

For Python, install a `pyright-langserver` binary and use `pyright-lsp@claude-plugins-official`; the official documentation lists plugins for Rust, Go, PHP, Java, C++, Swift and other languages too. 

Verification: ask Claude to navigate to the definition of a symbol and inspect diagnostics after editing a file. Confirm the server is active, then compare the number of searches and reads needed.

Revert: uninstall the corresponding Claude plugin, then if no other application needs the binary:

```
npm uninstall -g typescript-language-server typescript
```

Do not disable plain grep. The 2026 LSP evidence argues strongly against an LSP-only agent.

### Step 5 — Context7, only for documentation-heavy work

GitHub: [Context7](https://github.com/upstash/context7)

Inside Claude Code:

```
/plugin marketplace add upstash/context7
```

```
/plugin install context7@context7-marketplace
```

Restart Claude Code, open `/mcp`, select Context7 and complete its sign-in flow. The current plugin uses the hosted MCP endpoint and does not require a local Node installation. Alternatively, Context7's documented CLI setup is:

```
npx ctx7 setup --claude
```

That CLI offers a choice between MCP and CLI integration. Use one integration route, not both. 

Verification: request a narrow, version-specific API example and confirm that Claude used retrieved documentation rather than guessing syntax.

Revert: remove the plugin from `/plugin`, or remove its MCP entry if configured manually. It should not be on the critical path for ordinary local code edits.

## 6. CLAUDE.md: maximum utility, minimum permanent instructions

Claude Code loads user and project instructions into context. Anthropic recommends keeping CLAUDE.md focused and under roughly 200 lines, with specialized material moved into on-demand skills. I would aim substantially smaller for most repositories. 

Suggested project-root CLAUDE.md — adapt the commands and paths to the actual repo.

```

# Project instructions

## Execution
- Solve the requested task with the smallest correct change.
- Preserve existing behavior and architecture unless change is necessary.
- Prefer existing utilities, standard APIs, and installed dependencies.
- Do not create extra abstractions, documents, scripts, or dependencies without need.

## Context and navigation
- Start with supplied file paths, errors, and symbols.
- For text searches, use rg with scoped paths.
- Use LSP for precise definitions or reference relationships.
- Use AST search for syntax patterns; semantic retrieval only when lexical search is insufficient.
- Read relevant sections before entire files. Re-read when files changed or correctness requires it.
- Do not dump the entire repository or extensive logs into context.

## Tool calls and verification
- Combine closely related independent checks when this reduces overhead without hiding failures.
- Preserve complete errors, stack traces, diagnostics, and exact edit context.
- Run the smallest relevant tests first; expand when failures or dependencies warrant it.
- Do not claim verification unless the check actually ran.

## Responses
- Be concise. Report changes, important trade-offs, verification, and unresolved issues.
- Do not narrate routine tool calls.
- Explain non-obvious decisions when needed for future maintenance.

## Context handoff
- At a meaningful task boundary, preserve only decisions, changed files,
  outstanding issues, verification state, and next actions.

```

The strongest part of this file is what it does not say. It does not force three searches before every edit, inject a design system into unrelated sessions, create an elaborate plan for every one-line change, or forbid legitimate file rereads.

A rule like “never read the same file twice” sounds efficient but is unsafe: a changed file, failed patch, conflicting edit or new error may require rereading. The goal is to prevent unnecessary rereads, not necessary ones.

### A better way to organize skills

Put specialty material in `.claude/skills/`, loading it only for the relevant task. Examples include design standards, animation engineering, accessibility reviews, security audits and migration procedures.

Keep each skill narrowly scoped. Its summary or discovery information may still create some overhead; its complete instructions should not be perpetually injected merely because it is installed.

## 7. Caching: probably the largest financial opportunity

Prompt caching deserves more attention than almost any compression plugin.

Claude Code builds reusable prefixes covering its tool/system layer, project instructions and conversation history. A cache hit avoids charging those tokens at the full fresh-input rate.

Fresh input

# 1.0×

Base comparison price

Cache reads

# 0.1×

Base input price

Cache writes

# 1.25–2×

5-minute / 1-hour TTL

These are Anthropic API pricing multipliers, not reductions in the number of tokens processed or guarantees of an equivalent improvement to subscription quotas. 

### Subscription versus API caching

| Setting                   | Claude subscription, included usage | API key / usage credits                                     |
| ------------------------- | ----------------------------------- | ----------------------------------------------------------- |
| Main conversation default | 1 hour                              | 5 minutes                                                   |
| Subagent default          | Generally 5 minutes                 | 5 minutes                                                   |
| Main TTL override         | Usually unnecessary                 | Optional `1h`                                               |
| Key risk                  | Compaction after idle, cold resumes | Paying more for cache writes without enough subsequent hits |

Claude Code's current official documentation specifies these defaults and accepts `"5m"` or `"1h"` through `promptCacheTtl` and `subagentPromptCacheTtl`. 

For an API-based workflow with breaks frequently exceeding five minutes but staying under an hour, you can test this in `~/.claude/settings.json`:

```

{
  "promptCacheTtl": "1h"
}

```

Do not overwrite existing settings with this fragment; merge the key into your existing JSON. For an included-usage Claude subscription, leave the default alone.

Why not force one-hour caching everywhere? Longer-lived cache writes cost more. If work is a rapid succession of turns within five minutes, the 5-minute TTL may be cheaper. The correct setting depends on actual request gaps.

### What invalidates or weakens caching?

| Action                                        | Consequence                                                  | Recommendation                                           |
| --------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------- |
| Changing the model                            | New cache prefix                                             | Keep a model stable within a task when practical         |
| Changing system/tool definitions              | Can rebuild early cache layers                               | Do not repeatedly toggle MCP/proxy configurations        |
| Adding content at the end of the conversation | Earlier prefix generally stays cached                        | Prefer append-only tool results and on-demand skills     |
| Running `/compact`                            | Conversation-history prefix rebuilt                          | Compact when discarded history outweighs rebuilding cost |
| Running `/recap`                              | Leaves earlier cache intact                                  | Use for inspection without compaction                    |
| Running `/rewind`                             | Can reuse an earlier cached prefix                           | Prefer when abandoning a failed exploration branch       |
| Editing CLAUDE.md mid-session                 | Current session keeps loaded version until reload/compaction | Edit at task boundaries                                  |
| Resuming after TTL expiration                 | Cold read/write and potentially longer latency               | Keep compact handoffs for very long sessions             |

Official behaviour, including the important distinction between compaction and recap, is documented in Claude Code's caching guide. 

### Idle compaction

Claude Code added an idle compaction feature capable of compressing sufficiently long, inactive terminal sessions near the one-hour cache expiry. This can avoid a large cold-context rebuild, but may discard details that will be needed later.

For continuity-sensitive tasks, the documented opt-out is:

```

{
  "idleCompaction": false
}

```

Keep idle compaction enabled initially. Disable it only if you observe loss of necessary working context or poorer completion outcomes. The feature requires Claude Code 2.1.290 or later. 

### Cache optimization rules worth following

1. Keep the same model and configuration during an active implementation phase.
2. Avoid frequently changing MCP server sets or system prompts mid-task.
3. Clear unrelated conversations instead of accumulating stale project history.
4. Keep reusable repository knowledge in concise files rather than repeatedly rediscovering it.
5. Do not run unnecessary “cache warming” requests on a subscription merely to keep a session alive. Those requests also consume resources.
6. Judge caching by measured cache-read, cache-write and fresh-input quantities, not the displayed context-window size alone.

## 8. MCP optimization: don't pay for tools you never use

Claude Code now supports native deferred MCP tool search. Tool definitions are no longer necessarily loaded wholesale into the model's initial context: it can load definitions when needed. The exact savings depend on the server, tool count and setup. 

This makes older blanket advice to install an MCP manager for “90% schema savings” outdated.

The first diagnostic is simply:

```
claude mcp list
```

Then, inside Claude Code:

```
/context
/mcp
```

Disable unused services and identify servers whose instructions or connection behavior still consume context. If a familiar CLI can perform the operation safely, `gh`, `git`, `rg`, `aws` or another native CLI often avoids MCP registration overhead. That is also Anthropic's published guidance.

One important complication: some custom routers and API proxies do not faithfully pass every Claude-specific request feature. The official docs warn that certain proxy configurations interfere with tool search and caching. Avoid adding a proxy solely for speculative savings, especially if your normal Claude Code authentication already works. 

Do not mistake a smaller advertised MCP tool catalog for actual saving. Confirm the agent uses the tools and obtains the same results with fewer calls.

## 9. Hooks: useful when they remove information safely

Claude Code's current `PostToolUse` hook can replace the output that Claude receives through `updatedToolOutput`. That supports built-in tools, including Bash. Older community advice claiming that post-tool hooks can only append content is no longer generally correct. 

However, I would not install an always-on aggressive filter in the essential stack. Exact compiler errors, test traces and patch anchors often matter more than the token saving.

### Optional guarded filter for successful, verbose test output

This sample is intentionally conservative. It rewrites long output only when a recognized test command produced an apparent success result, with no stderr or error indicators. It preserves all errors and unknown output unchanged.

First create the hook script:

```
mkdir -p "$HOME/.claude/hooks"

cat > "$HOME/.claude/hooks/compact-passing-tests.py" <<'PY'
#!/usr/bin/env python3
import json
import re
import sys

try:
    event = json.load(sys.stdin)
except Exception:
    sys.exit(0)

command = event.get("tool_input", {}).get("command", "")
result = event.get("tool_response")

if not isinstance(result, dict):
    sys.exit(0)

if not re.match(
    r"^\s*(npm test|npm run test|pytest|cargo test|go test)\b",
    command,
):
    sys.exit(0)

stdout = result.get("stdout", "")
stderr = result.get("stderr", "")

if not isinstance(stdout, str) or len(stdout) < 12000:
    sys.exit(0)

if stderr or result.get("interrupted") or result.get("isImage"):
    sys.exit(0)

if re.search(
    r"\b(error|fail(?:ed|ure|ing)?|traceback|exception|warning)\b",
    stdout,
    re.IGNORECASE,
):
    sys.exit(0)

if not re.search(
    r"\b(passed|passing|tests? successful|test result:\s*ok)\b",
    stdout,
    re.IGNORECASE,
):
    sys.exit(0)

lines = stdout.splitlines()
if len(lines) < 90:
    sys.exit(0)

short = (
    lines[:25]
    + [f"... {len(lines) - 65} middle log lines omitted ..."]
    + lines[-40:]
)

replacement = dict(result)
replacement["stdout"] = "\n".join(short)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "updatedToolOutput": replacement,
    }
}))
PY

chmod +x "$HOME/.claude/hooks/compact-passing-tests.py"
```

Merge this `hooks` entry into your existing settings JSON rather than replacing other configured hooks:

```

{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/compact-passing-tests.py"
          }
        ]
      }
    ]
  }
}

```

Verify: restart Claude Code, run `/hooks`, and perform a verbose passing test run. A failing test must retain its full diagnostic output. Confirm that the handler works with the tool-output schema in your installed version before depending on it.

Revert: remove only this hook entry from `settings.json`, then delete the script.

This sample is not benchmarked and is optional. It should not be combined with RTK or LeanCTX's shell compression until each treatment has been measured separately. For unusually important output, preserve the complete log or bypass compression.

## 10. Optional Serena setup for large codebases

Serena is the first additional retrieval system I would test when the repository is large enough that file exploration dominates the workflow.

It is not a universal replacement for native LSP or grep. Its value is its complete workflow for finding, reading and editing relevant symbols with less unrelated code.

GitHub: [oraios/serena](https://github.com/oraios/serena)

Current Serena documentation explicitly recommends installing with `uv` rather than relying on old MCP/plugin marketplace packages. 

```
brew install uv

uv tool install -p 3.13 serena-agent
serena init
```

Navigate to the target project directory:

```
cd /path/to/your/project

claude mcp add serena -- \
  serena start-mcp-server \
  --context claude-code \
  --project "$(pwd)"
```

Then verify:

```
claude mcp list
```

Start a new Claude Code session and use `/mcp` to confirm the server connects.

Use Serena for finding or editing relevant function/class bodies, understanding callers and following symbol relationships. Preserve the native tools for raw reads, full diffs, string references and tests.

The current Serena docs also describe optional reminder hooks for getting Claude to use its symbolic tools. I would only install those if an initial trial shows tool-selection drift. Its own maintainers acknowledge this issue, and indiscriminate reminder hooks create additional overhead. 

Revert:

```
claude mcp remove serena
uv tool uninstall serena-agent
```

If you installed Serena at a different MCP scope, remove that entry at the matching scope. Do not simultaneously configure the same Serena server globally and locally; a reported GitHub issue documents failures from duplicate registration. 

## 11. LeanCTX versus RTK versus Headroom

These tools should be evaluated as alternatives, not blindly combined.

| Capability                                 | LeanCTX                     | RTK                                  | Headroom                                |
| ------------------------------------------ | --------------------------- | ------------------------------------ | --------------------------------------- |
| Shell output compression                   | Yes                         | Main strength                        | Supported                               |
| Repository retrieval                       | Yes                         | Limited                              | Optional features                       |
| MCP integration                            | Yes                         | Not its main purpose                 | Yes                                     |
| API proxy                                  | Optional                    | Separate proxy product               | Major integration mode                  |
| Subscription-friendly without API redirect | Documented                  | Yes, normal CLI filters              | Requires careful configuration          |
| Independent evidence                       | Positive on a small fixture | Conflicting; larger test unfavorable | Limited comparable independent evidence |
| Complexity                                 | Medium/high                 | Low/medium                           | High                                    |

### If testing LeanCTX

GitHub: [LeanCTX](https://github.com/yvgude/lean-ctx)

```
brew tap yvgude/lean-ctx
brew install lean-ctx

lean-ctx wrap claude
```

After real use:

```
lean-ctx gain
```

Its current instructions say `wrap claude` does not add an `ANTHROPIC_BASE_URL` proxy redirect for Claude subscription OAuth; it enables its supported tools and shell-output optimization. Validate this in your own environment rather than assuming all variants use the same route. 

Revert:

```
lean-ctx unwrap claude
```

I would test LeanCTX against native Claude + Ponytail, with the same prompts and repository, before keeping it permanently.

### If testing RTK instead

GitHub: [RTK](https://github.com/rtk-ai/rtk)

```
brew install rtk
rtk --version
rtk gain
rtk init --global
```

After the trial:

```
rtk gain
```

And revert:

```
rtk init -g --uninstall
brew uninstall rtk
```

These commands match the current installation documentation. RTK has full and Apache-only editions, plus a separate proxy; do not confuse the CLI filtering install with its proxy. 

Crucially, `rtk gain` is not proof of money saved. JetBrains found RTK's own reported avoided-token totals could look enormous while billed costs rose, partly because the counterfactual counted text Claude Code would already have truncated. 

For Headroom, I would restrict trials to API-based workloads involving enormous structured JSON or logs. Avoid it as a default wrapper for a working subscription-based Claude Code setup. Any proxy experiment must confirm unmodified authentication, caching, tool schemas, tool calls and success rates.

## 12. Conflict matrix: what to combine and what to avoid

| Combination                         | Decision            | Reason                                                                            |
| ----------------------------------- | ------------------- | --------------------------------------------------------------------------------- |
| Ponytail + native Claude Code       | Combine             | Changes coding behavior without replacing the transport or retrieval system       |
| Ponytail + official LSP             | Combine             | Different problems                                                                |
| Ponytail + Context7                 | Combine selectively | Context7 only for documentation needs                                             |
| Official LSP + `rg`                 | Combine             | Complementary: semantic references versus complete textual matches                |
| ast-grep + `rg`                     | Combine             | Structural patterns versus text                                                   |
| Serena + native LSP                 | Test first          | Overlapping symbol navigation; Serena also offers higher-level editing and memory |
| Serena + Cartog + Octocode          | Choose one          | Redundant code graph/retrieval layers                                             |
| Serena + Token Savior               | Choose one          | Duplicate symbolic retrieval and persistent context functions                     |
| RTK + LeanCTX                       | Choose one          | Both alter shell-output workflows                                                 |
| RTK + custom Bash compression hooks | Choose one          | Double compression may hide diagnostics or trigger retries                        |
| LeanCTX + Headroom                  | Avoid initially     | Multiple context/proxy layers make cache and cost attribution difficult           |
| claude-mem + Token Savior memory    | Choose one          | Duplicate persistent-memory capture and injection                                 |
| Whole-repo Repomix + Serena         | Usually avoid       | Defeats targeted retrieval by reintroducing broad repository context              |

The best stack has fewer layers than most token-optimization repositories advertise.

## 13. Subagents: when delegation saves and when it multiplies cost

Subagents have a legitimate place, but total token consumption usually increases when they all explore the same codebase and independently repeat the same reasoning.

They can save money when a cheaper model performs a narrow task, returns a concise result and prevents an expensive main agent from processing large raw outputs. They can also protect the main agent's context window.

Anthropic states that agent teams may consume roughly seven times the tokens of standard sessions in plan mode. Each active teammate has its own working context.
