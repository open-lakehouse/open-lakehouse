---
name: sdp
description: Spark Declarative Pipelines (SDP) — the declarative pipeline framework in Spark 4.x. Load when designing, running, or debugging an SDP pipeline. Covers the OSS `pyspark.pipelines` API, dataset primitives, the `spark-pipelines` CLI, and the medallion pattern on this stack.
---

# Spark Declarative Pipelines

SDP defines data pipelines declaratively: decorate Python functions (or write SQL files), and Spark builds the dependency graph, schedules topologically, and handles incremental execution + recovery. You declare WHAT the tables are; SDP handles HOW.

This is **OSS Apache Spark 4.1 SDP** (`pyspark.pipelines`), **not** Databricks DLT. The APIs differ — see "API: OSS vs Databricks DLT" below. The canonical OSS reference repo is [`lisancao/pyspark-sdp`](https://github.com/lisancao/pyspark-sdp) (pattern library + examples); the canonical doc is <https://spark.apache.org/docs/latest/declarative-pipelines-programming-guide.html>.

**SDP requires Spark Connect.** `spark-pipelines` spawns its own embedded Connect server (the `SparkConnectPlugin` driver plugin) — it binds port 15002, the same port as this stack's standalone `spark-connect-41` container. **Stop one while running the other.**

## API: OSS vs Databricks DLT

If you've seen Databricks DLT, unlearn these — they do **not** exist in OSS SDP:

| Databricks DLT (wrong here) | OSS SDP (`pyspark.pipelines`) |
|------------------------------|-------------------------------|
| `import dlt` | `from pyspark import pipelines as dp` |
| `@dlt.table` / `@dlt.view` | `@dp.table` / `@dp.materialized_view` / `@dp.temporary_view` |
| `dlt.read("x")` / `dlt.read_stream("x")` | `spark.read.table("x")` / `spark.readStream.table("x")` |
| `spark` is injected | `spark = SparkSession.active()` — call it yourself |
| `@dlt.expect_or_drop(...)` | **no expectations API in OSS** — filter-split manually (see patterns.md) |
| `APPLY CHANGES INTO` / Auto CDC | Databricks-only (SPARK-56249 not merged) |
| `refresh_interval` on a view | Databricks-only — schedule pipeline runs with Airflow/cron |

`pyspark.pipelines` exports exactly: `table`, `materialized_view`, `temporary_view`, `append_flow`, `create_streaming_table`, `create_sink`. Nothing else.

## Sub-files (load only the one you need)

| Topic | File |
|-------|------|
| Patterns — medallion, dedup, quarantine, stream-static join | [patterns.md](patterns.md) |
| Streaming pipelines (Kafka → table) | [streaming.md](streaming.md) |
| Data sources (files, JDBC, existing tables) | [data-sources.md](data-sources.md) |
| **Targeting Unity Catalog OSS** (the `table_properties` location+provider pattern) | [unity-catalog.md](unity-catalog.md) |
| Errors & how to read SDP logs | [troubleshooting.md](troubleshooting.md) |

> **Catalog note:** SDP-on-UC works for **Delta tables only**, and requires an
> explicit `location` + `provider` in `table_properties`. Verified, non-obvious
> — read [unity-catalog.md](unity-catalog.md) before targeting `catalog: unity`.

## Primitives

| Decorator | Dataset | Use for |
|-----------|---------|---------|
| `@dp.table` | **Streaming table** — append-only, persisted | Ingesting external sources (Kafka, files) and append-only derived tables |
| `@dp.materialized_view` | **Materialized view** — recomputed | Aggregations, joins, transforms over other SDP tables |
| `@dp.temporary_view` | **Temp view** — not persisted, pipeline-internal | Intermediate steps not worth materializing |

Rule of thumb: reading Kafka/files → `@dp.table`. Aggregating/joining SDP tables → `@dp.materialized_view`. Reading a streaming source with a materialized view is a common mistake — don't.

## Critical rules

1. **`spark = SparkSession.active()`** at module level (or inside each function). OSS SDP does not inject `spark`. Agents get this wrong constantly.
2. **Function name = dataset name.** `def orders_silver():` registers a dataset `orders_silver`. snake_case.
3. **Reference upstream tables INSIDE the function body** via `spark.read.table("name")` / `spark.readStream.table("name")`. SDP infers the DAG from those calls. Never pass upstream datasets as function arguments — that breaks dependency inference.
4. **No DataFrame analysis inside a pipeline function.** `spark.createDataFrame([...rows...])`, `.collect()`, `.count()` all trigger analysis and SDP rejects them (`ATTEMPT_ANALYSIS_IN_PIPELINE_QUERY_FUNCTION`). Build lazily — `spark.range(n).selectExpr(...)`, or read a source.
5. **Pipeline functions are pure.** No side effects beyond returning a DataFrame. No API calls, no file uploads.

## Pipeline definition

`spark-pipeline.yml` (the spec — `spark-pipelines init` generates it; don't hand-write blindly):

```yaml
name: my-pipeline
catalog: unity                       # optional — target catalog
schema: bronze                       # optional — target schema (alias: database). NOT `target`
storage: file:///tmp/my-pipeline-storage   # required — pipeline state/checkpoints
libraries:
  - glob:
      include: transformations/**     # picks up .py and .sql files
```

Transformations (`transformations/orders_silver.py`):

```python
from pyspark import pipelines as dp
from pyspark.sql import DataFrame, SparkSession

spark = SparkSession.active()


@dp.materialized_view(name="orders_silver", comment="Cleaned orders.")
def orders_silver() -> DataFrame:
    # Dependency on orders_bronze inferred from this read.
    return spark.read.table("orders_bronze").where("amount > 0")
```

SQL transformations (`transformations/orders_gold.sql`) also work:

```sql
CREATE MATERIALIZED VIEW orders_gold AS
SELECT order_date, count(*) AS order_count, sum(amount) AS revenue
FROM orders_silver
GROUP BY order_date;
```

## Running

`spark-pipelines` is the CLI. From the pipeline project directory:

```bash
spark-pipelines init my-pipeline   # scaffold a project (generates the spec)
spark-pipelines dry-run            # validate the DAG + schemas, run nothing
spark-pipelines run                # execute
spark-pipelines run --full-refresh-all   # reset + recompute every dataset
```

On this stack the CLI lives at `/opt/spark/bin/spark-pipelines` inside `spark-master-41`, and needs Python deps the base image lacks — see [unity-catalog.md](unity-catalog.md) "Pre-reqs the base Spark image is missing".

## Data quality without an expectations API

OSS SDP has no `@dp.expect*`. For row-level quality, **filter-split**: one `@dp.table` for valid rows, one for quarantined rows, both filtering the same source on a boolean predicate. See [patterns.md](patterns.md) → quarantine. The `lisancao/pyspark-sdp` repo's `patterns/quarantine.py` is the reference implementation.

## When NOT to use SDP

- One-shot ad-hoc queries → Spark SQL directly.
- Sub-second latency that can't tolerate streaming-table checkpointing → raw Structured Streaming / Real-Time Mode.
- Side-effecting workflows (API calls, branching across days) → orchestrate with [[airflow-3]]; keep SDP for the pipeline body.
- Custom state machines beyond append/aggregate → `transformWithState` directly.
