# Choosing an optimizer profile

**Created by [Shivam Kumawat](https://github.com/ohnoshivm) · AgentKind Labs**

| Profile | Default operating strategy | External candidates to trial (one at a time) |
| --- | --- | --- |
| **Balanced** | Native caching, compact skills, scoped search, tests, complete work | Ponytail vs unmodified baseline |
| **Deep reasoning** | Constrain redundant exploration while preserving genuine depth | Occam vs Ponytail vs baseline |
| **Full product** | Preserve every agreed product feature, UI/UX detail, responsive/motion quality and accessibility | Whittle vs Ponytail vs baseline |
| **Minimal patch** | Direct file search, single executor, limited changes and focused tests | Ponytail Lite, Occam Lite, Chisle in separate trials |
| **Large repository** | Scoped grep/AST/LSP, then one symbol indexer if needed | Serena *or* Cartog *or* another indexer, not all |

Detailed source comparisons: [October 2026 coding-behavior research](../research/optimizer-behavior-comparison-2026.md).

All profiles operate as instruction and test policies by default. `tokenmaxxing.py install` stages optimizer repositories; it does not activate any upstream optimizer automatically. This is deliberate: Ponytail, Occam, Chisle and output-style tools have overlapping rules or hooks; enabling all of them is not a valid baseline.

## Controlled comparison

- Use one benchmark fixture/task brief, initial commit, model, effort, tools, time limit and acceptance tests.
- Run an untreated baseline and each candidate in independent clean sessions.
- Prefer multiple repeats, and preserve both successful and failed samples.
- Calculate quality-adjusted cost and total token/caching usage; track tests, feature completeness and regressions.
- Do not add multiple percentage-saving claims together; provider-billed costs and subscription quotas differ.

## Candidate evidence grades

- **Ponytail:** JetBrains reported a 10.3% median cost reduction across 80 paired tasks, with no statistically detectable task-score difference. Security and accessibility equivalence was not established.
- **Occam:** Developer reports 11% lower Opus Medium task cost and 51% lower Opus Max task cost in its own benchmark. Independent replication is missing.
- **Whittle:** Developer's small product tests emphasise feature completeness, with known cases where it cost more or produced broken CLI output; not an independent guarantee.
- **Chisle:** Primarily developer-reported code and tool-output compression; whole-session benefits require additional testing.
- **Master of Tokens:** Developer reports 7,224 to 897 skill-discovery tokens in one 141-component setup, not an 88% whole-task reduction. Skill discoverability must remain intact.
- **Simple Man:** Output shortening was demonstrated, but a published paired-session evaluation did not establish cost savings.

Links and pinned revisions: [`policy/optimizer-registry.json`](../policy/optimizer-registry.json).
