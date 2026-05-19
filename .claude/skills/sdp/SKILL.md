---
name: sdp
description: Spark Declarative Pipelines (SDP) — the declarative pipeline framework in Spark 4.x. Load when designing, running, or debugging a `pipeline.yml`-driven SDP pipeline. Covers naming rules, dry-run/run CLI, dataset types, expectations, and the medallion pattern on this stack.
---

# Spark Declarative Pipelines

SDP is Spark's declarative pipeline framework: write Python functions decorated with `@dlt.table` / `@dlt.view`, declare expectations, and Spark runs them as a managed pipeline with topological scheduling, schema enforcement, and quality checks. SDP replaces hand-rolled `read → transform → writeTo` chains.

**SDP requires Spark Connect.** `pyspark.pipelines` uses `SparkConnectGraphElementRegistry` internally for the dataflow graph, even though `spark-pipelines run` doesn't open `sc://` explicitly. In this stack the Connect server in `spark-connect-41` provides that machinery — if you see `NoClassDefFoundError` related to Connect when running a pipeline, check `./lakehouse status --json | jq .spark.connect_grpc_listening`.

Authoritative reference. The user-facing `docs/guides/pipelines.md` points here.

## Sub-files (load only the one you need)

| Topic | File |
|-------|------|
| Patterns (medallion bronze/silver/gold, type-2 SCD, CDC) | [patterns.md](patterns.md) |
| Streaming pipelines (Kafka → Iceberg) | [streaming.md](streaming.md) |
| Data sources (file, JDBC, REST, custom) | [data-sources.md](data-sources.md) |
| Errors & how to read SDP logs | [troubleshooting.md](troubleshooting.md) |

## Critical naming rules

Get these wrong and the pipeline won't compile:

1. **Function names = dataset names.** `def silver_orders():` produces a dataset named `silver_orders`. Use snake_case.
2. **Catalog/schema come from `pipeline.yml`, not from `@dlt.table(name=...)`.** Don't fully-qualify in the decorator.
3. **Reading another SDP dataset**: `dlt.read("silver_orders")` (live view) or `dlt.read_stream("silver_orders")` (streaming live view). Never `spark.read.table(...)` — that bypasses the SDP DAG.
4. **External tables**: read via `spark.read.format("iceberg").load("iceberg.bronze.raw")` — not via `dlt.read`.

## Pipeline definition

`pipeline.yml` (top-level config):

```yaml
name: medallion
catalog: iceberg            # Unity Catalog catalog
target: silver              # default schema for outputs (overridable per-dataset)
configuration:
  spark.sql.shuffle.partitions: "8"
libraries:
  - notebook:
      path: ./pipeline.py
```

`pipeline.py` (dataset definitions):

```python
import dlt
from pyspark.sql import functions as f

@dlt.table(
    name="orders",
    comment="Cleaned orders, deduplicated by order_id",
    table_properties={"quality": "silver"},
)
@dlt.expect_or_drop("valid_id", "order_id IS NOT NULL")
@dlt.expect("non_negative_amount", "amount >= 0")
def silver_orders():
    return (
        spark.read.format("iceberg").load("iceberg.bronze.orders")
        .filter(f.col("status") != "cancelled")
        .dropDuplicates(["order_id"])
    )
```

## Running

```bash
# Dry run — validates DAG, schema, expectations; runs nothing.
docker exec spark-master-41 /opt/spark/bin/spark-submit \
  --packages io.delta:delta-spark_2.13:4.0.1 \
  /opt/spark/sdp.py --pipeline /scripts/pipelines/spark-pipeline.yml --dry-run

# Full run
docker exec spark-master-41 /opt/spark/bin/spark-submit \
  --packages io.delta:delta-spark_2.13:4.0.1 \
  /opt/spark/sdp.py --pipeline /scripts/pipelines/spark-pipeline.yml
```

`scripts/pipelines/pipeline_sdp.py` is a reference SDP pipeline you can copy into a demo.

## Dataset types

| Decorator | Storage | Use for |
|-----------|---------|---------|
| `@dlt.table` | Materialized Iceberg/Delta table | Anything other layers read from |
| `@dlt.view` | Logical, recomputed on read | Intermediate transformations cheap to recompute |
| `@dlt.table(temporary=True)` | Materialized but excluded from outputs | Debug datasets |

For streaming sources, use the `dlt.read_stream()` reader and have the function return a streaming DataFrame — SDP detects and switches the dataset to streaming.

## Expectations

```python
@dlt.expect("name", "sql_predicate")          # log, don't drop
@dlt.expect_or_drop("name", "sql_predicate")  # drop violating rows
@dlt.expect_or_fail("name", "sql_predicate")  # fail the whole run
```

Choose by severity: `expect` for soft data-quality signals, `expect_or_drop` for cleansing, `expect_or_fail` for invariants (primary keys, schema contracts).

## When NOT to use SDP

- One-shot ad-hoc queries → use Spark SQL directly.
- Anything that does side effects beyond table writes (API calls, file uploads) → SDP assumes pure-function datasets.
- Workflows that need branching/conditional logic across days → use [[airflow-3]] for orchestration, SDP for the pipeline body.
