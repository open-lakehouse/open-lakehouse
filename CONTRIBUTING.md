# Contributing

Thanks for considering a contribution to **open-lakehouse**. This file has two parts:

- **[For humans](#for-humans)** — how to file issues, propose changes, and run the test suite.
- **[For AI agents](#for-ai-agents)** — how Claude / Cursor / Copilot / Codex should approach changes here. Conventions specific to this repo's `.claude/` layout, the demo template contract, and what NOT to fabricate.

If you're an AI agent that landed here from `AGENTS.md`, jump straight to [For AI agents](#for-ai-agents). The human-facing process is informational only.

---

## For humans

### What this repo is — and isn't

open-lakehouse is a **demo platform**, not a reference architecture. It ships a stripped, opinionated subset of the upstream [`lakehouse-stack`](https://github.com/lisancao/lakehouse-stack):

- Spark 4.1 only (no 4.0)
- Unity Catalog OSS only (no PostgreSQL JDBC catalog)
- Connect-first transport (`sc://localhost:15002`)
- Iceberg + Delta both enabled by default
- Four demo slots, intentionally empty until built

If you want to add multi-version Spark, the JDBC catalog path, benchmarks, or alternative catalogs (Polaris, Nessie, Glue) — those belong upstream, not here. Keep this repo's surface tight.

### Filing issues

- **Bugs**: use the bug-report issue template. Include `./lakehouse status --json` output and `docker logs <container> | tail -50` for the failing service.
- **Feature ideas**: use the feature-request template. Frame it as "what demo does this unlock?" — features without a demo path get deferred.
- **New demo proposals**: use the demo-proposal template. Read [`demos/_template/README.md`](demos/_template/README.md) first to understand the contract.

### Proposing changes

```bash
# Fork, clone, branch from main
git checkout -b <kind>/<short-slug>     # e.g. fix/connect-server-port, feat/realtime-demo

# Install pre-commit hooks (enforces detect-secrets, ShellCheck, Bandit)
pre-commit install

# Run the test suite
poetry install --with dev,test
poetry run pytest tests/ --ignore=tests/integration -v

# Push and open a PR against main
gh pr create --base main --title "<kind>: <one-line summary>"
```

PRs should be small and single-purpose. Refactors and bug fixes shouldn't be mixed. Demo additions are their own PRs.

### Code style

- **Python**: 3.10+, Black (88 cols), Ruff. `from pyspark.sql import functions as f` — never `import *`.
- **Shell**: ShellCheck-clean. The `lakehouse` CLI has known SC2086 word-splits inside `case` branches; new code shouldn't add more.
- **Terraform**: `terraform fmt` before committing.
- **Markdown**: no marketing-speak. State what the thing does and any non-obvious gotcha.

### What requires a passing CI

All of: lint (Ruff/Black/ShellCheck), compose-file validation, unit tests (`tests/`), security scan, Spark 4.1 image pull. Integration tests under `tests/integration/` need Docker and run locally — they're not in the default CI matrix.

### Don't commit

- Real `.env`, `spark-defaults.conf`, `server.properties`, or `terraform.tfvars`. The `.gitignore` covers these; the `detect-secrets` pre-commit hook is a second line.
- JAR files (`./lakehouse setup` downloads them).
- Generated data, logs, MLflow runs, Spark warehouse contents.
- AI session memory or per-machine settings (`.claude/settings.local.json`).

---

## For AI agents

You are likely Claude, Cursor, Copilot, Codex, or a similar code-aware LLM. The conventions below are non-obvious and matter. Read this section before editing.

### Where everything lives

| You want… | Read |
|-----------|------|
| Project map, golden rules, version pins | [`CLAUDE.md`](CLAUDE.md) (always loaded) |
| Cross-tool pointer (Cursor/Copilot read this name) | [`AGENTS.md`](AGENTS.md) (forwards to CLAUDE.md) |
| Setup / teardown / demo / troubleshoot runbooks | [`.claude/skills/lakehouse-lifecycle/`](.claude/skills/lakehouse-lifecycle/) |
| Per-domain reference (Spark, SDP, Iceberg, Delta, UC, Kafka, Airflow, MLflow) | [`.claude/skills/<name>/`](.claude/skills/) |
| Cross-service sub-agent prompt | [`.claude/agents/lakehouse-engineer.md`](.claude/agents/lakehouse-engineer.md) |
| Demo contract | [`demos/_template/README.md`](demos/_template/README.md) |

The skills are **loaded on demand** via the `description:` frontmatter — match the user's task against descriptions and load only what's relevant. Don't preload everything.

### Hard rules (don't break these)

1. **Catalog is Unity Catalog OSS only.** If you see `spark.sql.catalog.iceberg.type=jdbc` or `.jdbc.user`/`.jdbc.password`, that's a bug. Fix the config; don't replicate the JDBC path.
2. **Spark is 4.1 only.** No `--version` flag. Compose file is `docker-compose-spark41.yml`. Master container is `spark-master-41`.
3. **Connect-first transport.** Default mode is `--spark-connect`. Spark Connect runs in `spark-connect-41` on port 15002. Clients use `SparkSession.builder.remote("sc://localhost:15002")` (or read `LAKEHOUSE_SPARK_REMOTE` from the env exported by the CLI). SDP requires Connect machinery — `pyspark.pipelines` uses it internally.
4. **`--spark-local` is a stub.** Don't try to make it work piecemeal. When it lands, it lands as one coherent change.
5. **Never `docker compose down -v`** without explicit user consent. `-v` wipes UC metadata, MLflow runs, Airflow history.
6. **Demo placeholders are intentional.** `demos/sdp-medallion/`, `unity-catalog-multi-engine/`, `realtime-mode/`, and `local-mode-spark/` are `.gitkeep`-only by design. If asked to "run the X demo" and the directory is empty, **scaffold from `demos/_template/`** — don't fabricate content.
7. **Catalog naming**: Iceberg tables → `iceberg.<schema>.<table>` (UC REST). Delta tables → `spark_catalog.<schema>.<table>` (DeltaCatalog). There is no `delta.*` catalog; references to it are wrong.

### Adding a new skill

Skills are versioned, model-discoverable docs. Each lives in `.claude/skills/<name>/SKILL.md` (optionally with sub-files and companion scripts). The frontmatter is the contract:

```markdown
---
name: <kebab-case-slug>
description: <one-line, specific. The model uses this to decide when to load the skill.>
---
```

Guidelines:
- One concept per skill. Don't bundle "Iceberg and Delta" into one — load both `iceberg-ops/` and `delta-ops/` instead.
- 200–600 lines per `SKILL.md` is a reasonable size. If you're approaching 1000, split into sub-files and use the SKILL.md as an index.
- Decision-tree-shaped content beats prose for skills the model executes (see `.claude/skills/lakehouse-lifecycle/start.md`).
- Cross-link with `[[other-skill-name]]` — even if the target skill doesn't exist yet, the link marks it as a future write.

### Adding a new demo

Don't add demo content unless asked. When asked:

```bash
cp -r demos/_template demos/<new-name>
# then fill in README.md following the five-section contract:
# Purpose / Prereqs / Run / Expected output / Teardown
```

Every demo must:
- Have a `README.md` matching the template structure (the lifecycle skill enforces this).
- Specify the transport explicitly (Connect, spark-pipelines, local — though local mode isn't built).
- Ship a `teardown.sh` or list explicit teardown commands.
- Have idempotent teardown — `IF EXISTS`, `--if-exists`, etc.

### What not to do

- **Don't preload every skill into context** "just in case." Load only what the user's task needs.
- **Don't downgrade JAR versions** in `scripts/tools/download-jars.sh` without explicit user instruction. AWS SDK v2 is pinned to 2.24.6 for Hadoop 3.4.1 compatibility.
- **Don't add `--no-verify` to commits** or bypass pre-commit hooks. If detect-secrets flags something, fix the secret.
- **Don't fabricate command output.** If you didn't run a command, don't quote what it would have printed. Use the demo's "Expected output" section to know what success looks like, and compare actual stdout to that.
- **Don't introduce dependencies for "future" use.** If the current task doesn't need a library/service, don't add it.
- **Don't write multi-paragraph docstrings.** One short line max. Identifiers and the README do the heavy lifting.

### When you delegate

Use the Task tool to spawn `subagent_type=general-purpose` with [`.claude/agents/lakehouse-engineer.md`](.claude/agents/lakehouse-engineer.md) loaded as the system prompt context for cross-service work that benefits from a focused sub-context. Sub-agent should report back with what changed, what was verified, and what was intentionally left alone.

### Memory persistence

This repo doesn't ship a memory subsystem — that's a personal-workspace concern, not a project concern. If you have a memory system in your harness (Claude Code's `~/.claude/projects/<dir>/memory/`), keep memory _about_ this repo there, not in the repo.

### Reporting back

When you finish a task: say what you changed, what you verified, and what you intentionally didn't touch. Don't apologize for diff size — the user reads diffs. Don't write a multi-paragraph wrap-up unless the user explicitly asks for one.
