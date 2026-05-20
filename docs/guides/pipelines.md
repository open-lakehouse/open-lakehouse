# Pipelines

The pipeline framework for open-lakehouse is **Spark Declarative Pipelines (SDP)** — OSS Apache Spark 4.1's `pyspark.pipelines`, not Databricks DLT.

The authoritative reference — API, patterns, streaming, data sources, UC integration, troubleshooting — lives at:

**[`.claude/skills/sdp/`](../../.claude/skills/sdp/)**

That directory is human-readable. Start with `SKILL.md`, then the sub-file that matches your task:

| Topic | File |
|-------|------|
| OSS API, primitives, CLI, critical rules | `SKILL.md` |
| Medallion, dedup, quarantine, CDC patterns | `patterns.md` |
| Streaming (Kafka → streaming table) | `streaming.md` |
| External data sources (files, JDBC, existing tables) | `data-sources.md` |
| Targeting Unity Catalog OSS | `unity-catalog.md` |
| Errors and how to read SDP output | `troubleshooting.md` |

The canonical OSS SDP reference repo — pattern library + runnable examples — is [`lisancao/pyspark-sdp`](https://github.com/lisancao/pyspark-sdp). The open-lakehouse SDP skill is kept aligned with it.

## Why is this not duplicated here?

Earlier versions kept an SDP guide in `docs/` *and* a skill in `.claude/skills/` and they drifted. One canonical source under `.claude/skills/sdp/` — AI agents discover it via skill metadata, humans read the markdown directly.

## Quick start

```bash
# spark-pipelines is the CLI. Scaffold a project:
docker exec spark-master-41 /opt/spark/bin/spark-pipelines init my-pipeline

# Validate the DAG without writing:
docker exec spark-master-41 sh -c 'cd my-pipeline && spark-pipelines dry-run'

# Run it:
docker exec spark-master-41 sh -c 'cd my-pipeline && spark-pipelines run'
```

`demos/sdp-medallion/` is a working bronze→silver→gold pipeline materialized
into Unity Catalog — copy it as a starting point. Note the SDP↔UC sharp edges
documented in [`.claude/skills/sdp/unity-catalog.md`](../../.claude/skills/sdp/unity-catalog.md).
