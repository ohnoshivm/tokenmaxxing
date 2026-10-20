# TOKENMAXXING Research — Coding-Behavior Optimizers and Skill Discovery (October 2026)

**Shivam Kumawat (@ohnoshivm) · AgentKind Labs**  
**Status:** Source-linked research and candidate registry; not independent replication of every reported result.

## Why this matters

A large proportion of coding-agent waste comes from (1) generating unnecessary abstractions, (2) inspecting irrelevant context, (3) creating extra agent steps, or (4) shipping a smaller but incomplete product that requires another implementation pass. A useful optimizer must reduce **total cost per verified, feature-complete outcome**, not simply visible answer length.

This report is part of TOKENMAXXING's **primary token-efficiency pillar** alongside model delegation. All third-party projects remain credited to their original authors. GitHub dependencies are pinned as submodules and mirrored in the [registry](../policy/optimizer-registry.json); their source is not copied or relicensed as TOKENMAXXING's own work.

## Coding behavior tools — compare rather than stack

| Candidate | Where it may help | Evidence provenance | Major caveat |
| --- | --- | --- | --- |
| [Ponytail 5](https://github.com/DietrichGebert/ponytail) | General implementation discipline, fewer unnecessary abstractions and components | [JetBrains paired-task study](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/): median cost down 10.3% over 80 paired tasks, without a statistically detectable task-score change | The study does not prove universal feature completeness or equal security/accessibility; updated release differs from tested version |
| [Occam](https://github.com/quisbaum-prog/occam) | High-effort reasoning, unnecessary search and repeated tool calls | Developer-reported Opus 5.5 **Medium −11%**, **Max −51%** task cost on its test set | Not independently replicated, result differs dramatically by effort and workload; conflicts with Ponytail hooks |
| [Whittle](https://github.com/Obed0101/whittle) | Complete feature-rich products, avoiding implementations that save cost by omitting requirements | Author reports approximately **94–95% feature delivery** vs **82–83%** with Ponytail in selected small Sonnet 5.5 tests; costs were higher for Whittle in those runs | Small, author-scored benchmark; other tasks showed regressions and incomplete/broken outputs |
| [Chisle](https://github.com/JayPokale/Chisle) | Concise implementation and compressing some verbose tool results | Developer claims about **46% reduction in oversized tool outputs** with example traces | Tool-output shrinkage is not proven end-to-end cost saving; unscoped installer may touch other apps |

**Selection rule:** Choose **one active coding-behavior optimizer** per comparable trial. Running Ponytail, Occam and Chisle at the same time adds overlapping instructions/hooks and makes savings attribution unreliable. Whittle's complete-feature emphasis can inform the acceptance criteria even when its skill is not activated.

## Skill discovery / secondary tools

| Tool | Function | Reported data | Recommended policy |
| --- | --- | --- | --- |
| [Master of Tokens](https://github.com/devrudals/master-of) | Gate rarely needed skills to reduce startup discovery metadata | Author's **141-component** example: **7,224 → 897 discovery tokens**, roughly 88% lower discovery context | Stage and measure first; gated capabilities must remain discoverable; not 88% whole-session savings |
| [Claude Token Saver](https://github.com/AllenSwift/claude-token-saver) | File outlines, narrow searches, error-log filtering, repository maps through local scripts | No sufficiently strong comparable independent task-cost benchmark in reviewed material | Use on demand; inspect installer and preserve raw diagnostics |
| [Simple Man](https://github.com/Maksim-Burtsev/simple-man) | Output brevity | 81-session evaluation reportedly cut visible response tokens but increased median total cost by 2.8%; statistically inconclusive | Optional output style, not a core token-cost optimizer |
| [Simpler Token Saver](https://github.com/tim-hub/cc-simpler-token-saver) | Very concise final answer style | Headline output-saving claims lack a convincing full-task benchmark | On-demand only; not layered with other global output styles |

## What to prioritise

1. **Correct complete specification and validation.** A shorter incomplete implementation is wasted cost when features must be added later.
2. **Native context features and selective retrieval.** They often cost less to maintain and avoid competing with runtime defaults.
3. **Ponytail baseline candidate.** It has stronger third-party evidence than the small new alternatives; test it against a control on actual tasks.
4. **Occam for deep-reasoning experiments.** Its Max-effort savings claim is notable but not independently validated, and its Medium claim is much smaller.
5. **Whittle for full-product experiments.** Evaluate user journeys, interactions, mobile breakpoints, animations, tests, accessibility and delivery completeness.
6. **Master of Tokens only if discovery metadata is genuinely costly.** Some hosts already defer skill definitions; premature gating can hide an essential skill.
7. **No global shell compression until outcomes are tested.** Prior larger studies found compressed tool outputs sometimes increased total paid cost due to additional steps.

## Reproducible benchmark protocol

For each model and effort under comparison, begin from the same repository commit. Preserve identical task briefs, acceptance criteria, verification tools, time limits and allowed permissions. Run multiple trials across routine bug fixes, complex engineering, and rich frontend features. Record fresh input, cache writes, cache reads, output, agent turns, real or API-equivalent cost, completion time, tests, feature coverage and defect counts. Use one optimizer per trial, not cumulative layers.

Mark absence of provider-side token measurements as **unobserved**, never zero. Distinguish *vendor-provided savings*, *independent measurements*, *unverified marketing percentages* and *hypothetical examples*. Do not claim generalized superiority from five-run tests.

## Deployment inside T3 Chat and Claude Code

The user's full Premium model-routing system lives in **T3 Chat**. Claude Code's plugin/skill infrastructure is a distinct execution host: a Claude plugin does not automatically configure T3 Chat. TOKENMAXXING ships an own portable skill and a simple Claude Code plugin, with an explicit [T3 Chat integration guide](../docs/t3-chat.md). The eight third-party projects are pinned GitHub submodules and available through a staged local checkout after `./install.sh`; nothing is silently enabled.

## Further reading

- [Core 2026 token-efficiency research](claude-code-token-maxxing-2026.md)
- [Optimizer registry](../policy/optimizer-registry.json)
- [Profile selection](../docs/optimizer-profiles.md)
- [Install and source-verification instructions](../docs/installation.md)
- [Primary model routing policy](../policy/routing-policy.yaml)
