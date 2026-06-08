# AGENTS.md

This file exists so AI tools that look for `AGENTS.md` (Cursor, Copilot, Codex) discover the project conventions.

The authoritative agent guide is **[CLAUDE.md](CLAUDE.md)**. Read that. Everything you need is either there or pointed to from there.

The deep references live under [.claude/skills/](.claude/skills/) and are loaded on demand by the LLM via skill discovery.

## Branching workflow (always applies)

All work in this repo must follow [.agents/rules/branching-rule.mdc](.agents/rules/branching-rule.mdc). Never commit directly to `main` — create a dedicated feature branch (e.g. `feat/<short-description>`) before making any changes. See the rule for naming conventions and the full workflow.
