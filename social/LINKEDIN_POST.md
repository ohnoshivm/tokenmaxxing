# I spent days designing a multi-model AI system. The biggest lesson wasn't which model was smartest.

**By [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

It was that **bad delegation can waste more tokens than a powerful model ever would.**

I compared Claude Opus and Sonnet across five reasoning levels, examined GPT-6 Luna and GPT-6.1 Sol as coding executors, studied DeepSeek and Haiku, and looked at the cost of actual completed tasks rather than only price per million tokens.

One finding changed the architecture: on Artificial Analysis, **Opus 5.5 Medium scored 51 against Sonnet 5.5 High's 47 on the Intelligence Index, while using approximately 26K rather than 37K output tokens per benchmark task.** Opus Medium still cost more in API-equivalent terms: $1.34 versus $0.88. Fewer tokens are not automatically lower costs.

Another finding was more uncomfortable. GPT-6 Luna High scored 5% on Terminal-Bench 4.0 versus 52% for GPT-6.1 Sol High. So although Luna can be an inexpensive coding executor, it needs well-defined tasks and strong verification. Difficult autonomous engineering belongs with a stronger specialist much earlier.

Here's the system I arrived at:

- **Opus Medium** — high-level thinking, creative direction, architecture, planning.
- **Opus High** — consequential decisions, exceptional concepts, critical reviews.
- **GPT-6 Luna High** — bounded implementation and routine coding.
- **GPT-6.1 Sol High** — difficult engineering and debugging.
- **GPT-5.6 Luna + Haiku** — repetitive intelligent work.
- **Local scripts** — everything deterministic.

The actual breakthrough is in the handoffs: one accountable executor, compact specs instead of pasted transcripts, tests before model reviews, and escalation after evidence of failure—not after an arbitrary number of agents have repeated each other's reasoning.

I wrote a long-form, source-linked research paper and a GitHub-ready operating kit with routing policy, agent instructions, handoff templates and a benchmark scorecard.

The hypothesis is straightforward: **quality-first orchestration should optimize the cost of verified work, not the number of tokens generated.**

The project still needs controlled real-world benchmarking before anyone should claim a fixed savings percentage. That's the point of making the protocol reproducible.

Sources and methodology: Artificial Analysis, T3 Code documentation, provider usage documentation. [GitHub repository link]
