# Building a Premium Multi-Model AI System: Why Better Delegation Matters More Than Bigger Models

**By [Shivam Kumawat](https://github.com/ohnoshivm) (@ohnoshivm) · AgentKind Labs**

*An evidence-based blueprint for using Claude, GPT, and optional DeepSeek in a unified workflow while protecting quality, context, and subscription usage.*

**Research dated October 2026.** Benchmark figures below are snapshots from [Artificial Analysis](https://artificialanalysis.ai/), not promises of performance or subscription allowance. Full research, source links and executable-task templates are in the accompanying GitHub repository.

## The mistake I was trying to fix

The usual multi-model workflow sounds reasonable: put the most intelligent model at the top, have it delegate the implementation to a cheaper model, hire more specialized agents for everything else, and put another powerful model in charge of reviewing the result.

But each delegation has costs. The new agent may re-read the repository, load the same instructions, interpret the same requirements, use more tools, and return an output the parent model then has to summarize. A plan that looks optimized on paper can silently use more tokens than one properly configured agent would have needed.

I wanted the opposite: a system that uses the best model at the right moment without treating expensive reasoning as a status symbol. The resulting architecture is quality-first, but every model switch has to earn its cost.

We started with a Claude-only structure: Opus for strategy and creative direction, Sonnet for building, Haiku for repetitive jobs. We considered a DeepSeek-first engineering layer, but the current system doesn't have an active funded DeepSeek subscription. We then introduced GPT-6 Luna for code execution, GPT-6.1 Sol for advanced engineering, GPT-5.6 Luna for repeatable work, and a unified T3-based environment.

The biggest refinement came when we stopped comparing model names and started comparing actual *effort configurations*.

## A finding that changed the default intelligence model

My original plan used Claude Sonnet 5.5 at High effort as the default director, saving Opus for exceptional decisions. Then we checked every Sonnet and Opus effort level against Artificial Analysis.

The [direct comparison](https://artificialanalysis.ai/models/comparisons/claude-sonnet-5-5-high-vs-claude-opus-5-5-medium) reports:

| Metric | Sonnet High | Opus Medium |
|---|---:|---:|
| Intelligence Index | 47 | **51** |
| Terminal-Bench 4.0 | 44% | **53%** |
| Average output tokens/task | 37K | **26K** |
| Average reasoning tokens/task | 19K | **12K** |
| Estimated API cost/task | **$0.88** | $1.34 |

Opus Medium was stronger on the measured intelligence benchmark while producing fewer output tokens. That's a useful finding, but not permission to make a false claim: **Opus Medium was still more expensive in estimated API cost.** And no public paper can tell us exactly how a specific app deducts included subscription quota. Output tokens, billed API dollars, and subscription rate limits are three separate measurements.

The choice for this system is therefore Opus Medium as the default *intellectual* model. Not because it's always cheaper, but because its benchmark position makes it a compelling quality-first option. Opus High is reserved for important creative, architectural and strategic work. Xhigh and Max are rare.

Another surprising comparison: [Sonnet Max versus Opus Xhigh](https://artificialanalysis.ai/models/comparisons/claude-sonnet-5-5-vs-claude-opus-5-5-xhigh) tied at 56 on Intelligence Index, but Sonnet Max used about 197K output tokens/task versus 66K for Opus Xhigh. Bigger thinking budgets do not always mean more productive thinking.

## Why the cheap coding model can't do everything

GPT-6 Luna is attractive as an inexpensive coding executor, especially when accessible through an existing subscription. But we should not confuse writing small patches with completing difficult, open-ended coding-agent tasks.

At High effort, Artificial Analysis reports **5% on Terminal-Bench 4.0 for GPT-6 Luna versus 52% for GPT-6.1 Sol High**. The precise numbers depend on the benchmark harness and its version, but the gap is far too large to ignore. [Comparison](https://artificialanalysis.ai/models/comparisons/gpt-6-1-sol-high-vs-gpt-6-luna-high).

So the final engineering rule is straightforward:

**Luna High receives scoped implementation tasks:** clear interfaces, approved behavior, relevant files, acceptance tests. The moment a task becomes a difficult repository-wide debugging or architectural problem, **Sol High** is a better starting point or escalation destination. Increasing Luna to Xhigh or Max is allowed only for selected coding tasks, never automatically.

A similar trap appeared when we compared GPT-5.6 Sol with GPT-6 Sol on OpenCode. Its chart appeared to give the older model a commanding reasoning and tool-use lead. But some of the GPT-6 axes were labeled as fallback values due to missing comparable measurements. At matched High effort, Artificial Analysis actually records **42 versus 42** on its Intelligence Index and **21% versus 26%** on Terminal-Bench in favor of GPT-6 on that coding test. This is why the source and methodology matter more than the colored radar graph. [High-effort comparison](https://artificialanalysis.ai/models/comparisons/gpt-6-sol-high-vs-gpt-5-6-sol-high).

## The actual model roster

Our selected production policy has six active model roles and one future candidate:

**Claude Opus 5.5 Medium** is the main thinker: strategy, architectural judgment, creative direction, research synthesis, UI/UX planning and project specifications.

**Claude Opus 5.5 High** handles major decisions, extraordinary creative reviews and difficult problems. Xhigh/Max are manual-only exceptions.

**GPT-6 Luna High** handles well-specified coding and implementation; **GPT-6.1 Sol High** handles difficult engineering, architecture-sensitive coding and serious debugging.

**GPT-5.6 Luna Medium/High** handles repetitive intelligent work. **Claude Haiku Low/Medium** is the secondary option. **Claude Sonnet 5.5 Medium** remains available for conventional analysis and specific supporting tasks, but Sonnet High is no longer the default intellectual director.

**DeepSeek V4.1 Flash 1017** is an inactive candidate pending authorized access. It was not discarded as weak: Artificial Analysis reports **34% Terminal-Bench 4.0 at Max**, versus Luna Max's 13%. The decision is about current provisioning and measured value, not brand loyalty.

For tasks a normal script can perform correctly, the script wins. Formatting, search, linting, deterministic transformations and validation should not require language-model reasoning at all.

## What makes this an operating system rather than a list of favorite models

There is a simple task protocol behind the model selections.

First, classify the task. Is it a deterministic operation, a bounded engineering problem, a complicated debugging investigation, a repetitive interpretation task, or a consequential strategic decision? Do we have clear acceptance criteria? Are the files and interfaces identified? Is a failure cheap to reverse?

Second, assign **one accountable executor**. Don't spawn three agents to investigate the same files. If parallelism is useful, isolate independent work and explicitly define ownership.

Third, write a short handoff when models must switch. A proper handoff states the objective, confirmed decisions, relevant files, non-goals, checks to run and escalation conditions. It does not dump a 100-message transcript and expect the next model to rediscover the intent.

Fourth, verify with tools before involving more models. A successful build, passing tests, a code diff and a reproduction check can be stronger evidence than a generic model review. Creative projects also require human-readable design criteria: originality, hierarchy, responsiveness, interaction craft, accessibility and coherence with the approved concept.

Fifth, stop after unproductive attempts. If a small model fails twice without reducing uncertainty, hand the exact failure to the appropriate specialist. Avoid repeating the same instruction with a slightly angrier prompt.

Finally, record what actually happened: quality, retries, token consumption if available, wall time, human review and subscription usage when the app exposes it. The target is **verified outcomes per unit of scarce resource**, not the number of generated lines or messages.

## A unified T3 environment still needs explicit context

Using several models under one interface is extremely useful. But it doesn't guarantee that two provider backends share hidden reasoning, tool history or native session state.

It's also important to distinguish [T3 Chat](https://t3.chat/), a conversational product, from [T3 Code](https://t3.codes/), a coding-agent control surface. T3 Code documents portable context handoffs, but these are budgeted transfers, not a literal transplant of one model's internal state. Model-switching and delegation details depend on the installed version and provider support. [Official documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/portable-handoffs.md).

The practical implication is simple: **store decisions in durable task files.** Treat the interface as the workspace, and the handoff as the source of truth.

## The economics most optimization posts get wrong

There are three ledgers. API tokens are charged according to the provider's input, output and cache rates. Consumer subscriptions have their own windows, caps and weighting. And human time has a real cost when a supposedly cheap model fails repeatedly.

A model can use fewer output tokens and still be more expensive. A model can have lower API prices and still be worse for a particular task. A model can score higher on a benchmark but be slower for your own simple edits. This is why we need controlled evaluation across real tasks, not a fixed claim of “90% savings.”

For every significant task, my benchmark plan measures successful completion, tests, quality, retries, time, observed usage, and rework. Only routes that meet the quality threshold are compared for efficiency. That is the difference between a cost-saving trick and an engineering method.

## The final principle

The complete policy fits into one sentence:

> **Opus Medium thinks and directs; Opus High makes exceptional decisions; GPT-6 Luna builds bounded features; GPT-6.1 Sol solves difficult engineering; GPT-5.6 Luna and Haiku handle repeatable work; local tools eliminate unnecessary model calls.**

What matters most isn't the exact brand or version of these models. Versions will change. The durable part is how the system routes work, preserves decisions, measures success, protects credentials and refuses to spend intelligence when deterministic execution is sufficient.

I've published the long-form research document together with a portable model policy, agent instructions, task brief, handoff and review templates, and a blank real-world evaluation scorecard. The routing is a proposed protocol, not a claim of having installed an autonomous agent. It is designed to be tested, challenged and improved.

**Read the full research and implementation kit:** [GitHub repository link]

**Primary source:** [Artificial Analysis](https://artificialanalysis.ai/). Benchmark results are as reported for the stated model and effort configurations in October 2026.
