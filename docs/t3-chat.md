# T3 Chat integration (portable, no pretend automation)

TOKENMAXXING was designed with **T3 Chat as the user's central multi-model workspace**, not three permanently running separate coding apps. Its multi-model routing and task-handoff policy is described in the root `README.md`, `AGENTS.md` and `policy/routing-policy.yaml`.

1. Put the repository URL or relevant policy text into T3 Chat project guidance when that feature supports it.
2. Keep Opus Medium for primary thinking and creative direction, GPT-6 Luna High for routine coding execution, GPT-6.1 Sol High for difficult engineering, GPT-5.6 Luna for repetition, with Haiku and Sonnet available as supporting specialists.
3. Use a compact task handoff file for any model change; do not assume every T3 model session shares complete active context, skills, filesystem state or internal cache.
4. Invoke the portable `skills/tokenmaxxing/SKILL.md` instructions where T3 supports project/system guidance or manual attachment.
5. Plugins installed into Claude Code through `claude plugin` **are not automatically installed or activated in T3 Chat**. Verify product capabilities first.
6. Keep API billing, OAuth subscriptions, provider routing and local macOS app settings separate. The installer never changes them.

## One-line onboarding

```bash
git clone https://github.com/ohnoshivm/tokenmaxxing.git && cd tokenmaxxing && ./install.sh
```

This one command installs the project token-efficiency skill in Claude Code and stages the **pinned source checkouts** of the 8 optimizer repositories in `~/.tokenmaxxing/vendor/`. It does **not** activate unsafe upstream hooks, configure T3, or install external optimizer dependencies. Those depend on user approval and the agent host.
