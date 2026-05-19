# Pipelines

The pipeline framework for open-lakehouse is **Spark Declarative Pipelines (SDP)**. The authoritative reference — including patterns, streaming, data sources, and troubleshooting — lives at:

**[`.claude/skills/sdp/`](../../.claude/skills/sdp/)**

That directory is human-readable. Start with `SKILL.md` (overview, naming rules, CLI), then read the sub-file that matches your task:

| Topic | File |
|-------|------|
| Bronze → Silver → Gold patterns, SCD, idempotence | `patterns.md` |
| Streaming (Kafka → Iceberg) | `streaming.md` |
| External data sources (files, JDBC, REST) | `data-sources.md` |
| Errors and how to read SDP logs | `troubleshooting.md` |

## Why is this not duplicated here?

Earlier versions of this stack maintained an SDP guide in `docs/` and a deeper SDP skill in `.claude/skills/`. They drifted out of sync. open-lakehouse keeps one canonical source under `.claude/skills/sdp/`. AI agents discover it via skill metadata; humans can read the markdown files directly.

If you need the legacy "imperative vs declarative" framing, that's covered in `SKILL.md` under "When NOT to use SDP."

## Quick start

```bash
# Reference pipeline
cat scripts/pipelines/pipeline_sdp.py

# Dry-run validates the DAG without writing
docker exec spark-master-41 /opt/spark/bin/spark-submit \
  --packages io.delta:delta-spark_2.13:4.0.1 \
  /opt/spark/sdp.py --pipeline /scripts/pipelines/spark-pipeline.yml --dry-run

# Full run
docker exec spark-master-41 /opt/spark/bin/spark-submit \
  --packages io.delta:delta-spark_2.13:4.0.1 \
  /opt/spark/sdp.py --pipeline /scripts/pipelines/spark-pipeline.yml
```

For new pipelines, start from the `demos/sdp-medallion/` placeholder and follow the demo contract.
