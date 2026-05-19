# Documentation index

| Section | What's inside |
|---------|----------------|
| [`getting-started/`](getting-started/) | Installation, 5-minute quickstart, configuration reference |
| [`guides/`](guides/) | CLI reference, streaming, pipelines, Airflow, Unity Catalog, test data |
| [`runbooks/`](runbooks/) | Human-readable lifecycle narrative (start / demo / stop / fix) |
| [`deployment/`](deployment/) | Local Docker, AWS self-hosted, Databricks managed |
| [`architecture.md`](architecture.md) | System design — service map, catalog model, version pins |
| [`troubleshooting.md`](troubleshooting.md) | Common issues + diagnostic commands |

## For AI agents

These docs are human-facing. Deeper, on-demand reference material for AI assistants lives at:

- [`../CLAUDE.md`](../CLAUDE.md) — always-loaded project map
- [`../.claude/skills/`](../.claude/skills/) — load-on-demand skill files (one per concept)

The single most useful skill for stack operations is [`../.claude/skills/lakehouse-lifecycle/`](../.claude/skills/lakehouse-lifecycle/) — decision-tree-shaped runbooks for start, stop, demo, and troubleshooting.
