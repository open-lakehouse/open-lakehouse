---
name: spark-4-1
description: Apache Spark 4.1 reference. Load when writing PySpark/Spark SQL against this stack — covers DataFrame API conventions, Spark 4.1-specific features (Connect, ANSI mode, streaming UDTFs), and gotchas vs older Spark.
---

# Spark 4.1 reference

This stack runs Apache Spark **4.1.0** on Scala 2.13 with Java 21 in **Connect-first** mode. The cluster master is `spark-master-41` (port 7078, UI 8082) and the Connect server is `spark-connect-41` (gRPC on 15002). Default client transport is `SparkSession.builder.remote("sc://localhost:15002")`.

## How to get a SparkSession (Connect-first)

```python
from pyspark.sql import SparkSession
import os

# Reads LAKEHOUSE_SPARK_REMOTE exported by ./lakehouse — falls back to the default.
remote = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")
spark = SparkSession.builder.remote(remote).appName("my-job").getOrCreate()
```

That's it. No `--master`, no JVM driver in your process, no `spark-submit`. The Connect server already has the Iceberg + Delta extensions wired via `config/spark/spark-defaults.conf`, so `spark.sql("SELECT * FROM iceberg.bronze.orders")` just works.

## When you still need spark-submit

- **SDP pipelines.** `spark-pipelines run` uses Connect machinery internally but isn't called via `.remote()`. It's the right tool for declarative pipelines; see `.claude/skills/sdp/`.
- **Heavy custom Scala/Java jobs** with their own JAR you want to spark-submit directly. Use the master container in that case:

```bash
docker exec spark-master-41 /opt/spark/bin/spark-submit /scripts/<your-job>.py
```

Mounts: `./scripts/` → `/scripts/`, `./jars/` → `/opt/spark/jars-extra/`.

## Imports — house style

```python
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as f
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType
```

Use `f.col`, `f.lit`, `f.when`, `f.year`, etc. **Never** `from pyspark.sql.functions import *` — pollutes the namespace and clashes with `min`, `max`, `sum` builtins.

## Spark 4.1 features worth knowing

- **ANSI mode is default.** `1 / 0` throws instead of returning `Infinity`. `cast("abc" AS INT)` throws. Use `try_cast()` / `try_divide()` when you want the legacy behavior locally.
- **Streaming UDTFs** (`@udtf`) are stable in 4.1 and work over Connect. Use for row-explosion in a streaming query.
- **Spark Connect** is the default transport in this stack. The Connect server runs in container `spark-connect-41`; clients connect via `sc://localhost:15002`. Iceberg/Delta extensions are wired server-side.
- **Variant type** (semi-structured JSON without schema). Columns can be `VARIANT` and queried via `variant_get()`. Useful for landing zone tables.
- **Photon is not in OSS Spark.** Don't claim it is. Use `EXPLAIN FORMATTED` to inspect the physical plan; the Catalyst optimizer + Tungsten codegen are what's running.

## Connect API surface — what works, what doesn't

The vast majority of DataFrame/SQL operations work identically over Connect. Known gaps in Spark 4.1:

- **Some `SparkContext`-level APIs** aren't accessible (`spark.sparkContext.broadcast`, manual accumulators, low-level RDD ops). Use DataFrame equivalents.
- **`mapInPandas` / Arrow UDFs** work, but heavy pickling has more round-trip cost over gRPC than in-JVM.
- **Custom JVM-side code** (Scala UDAFs, Hadoop input formats) can't be registered from the Connect client — load them server-side via `spark-defaults.conf` `spark.jars` or pre-install in the cluster image.
- **Structured Streaming** works including watermarks, `foreachBatch`, and Iceberg sink. See [[kafka-streaming]] for the realtime demo pattern.

## Common patterns

```python
# Add ingestion metadata
df = (raw
      .withColumn("_ingested_at", f.current_timestamp())
      .withColumn("_source", f.lit("kafka-orders")))

# Window dedup (keep latest per natural key)
from pyspark.sql.window import Window
w = Window.partitionBy("order_id").orderBy(f.col("event_ts").desc())
deduped = df.withColumn("_rn", f.row_number().over(w)).where("_rn = 1").drop("_rn")

# Iceberg write (UC-resolved namespace)
deduped.writeTo("iceberg.silver.orders").using("iceberg").createOrReplace()

# Iceberg merge (upsert)
deduped.createOrReplaceTempView("staging")
spark.sql("""
  MERGE INTO iceberg.silver.orders AS t
  USING staging AS s
  ON t.order_id = s.order_id
  WHEN MATCHED THEN UPDATE SET *
  WHEN NOT MATCHED THEN INSERT *
""")
```

## Performance defaults (already in spark-defaults.conf)

- Driver: 4g
- Executor: 8g × cores=2
- Shuffle partitions: leave at default (200) unless data is small (<10GB) — then set to `2 * cores`

## What's gone vs. older Spark

- No `sc.parallelize().toDF()` magic — use `spark.createDataFrame(rows, schema)`.
- No `pyspark.sql.functions.dropDuplicates(subset=...)` — it's a `DataFrame` method: `df.dropDuplicates(["col"])`.
- Avoid `df.toPandas()` on >1M rows; use Arrow with `df.mapInPandas()` or write to Iceberg + read back via DuckDB.

## When to use which file format

- **Iceberg** for batch + slowly-changing dimensions, time travel, schema evolution. Default for this stack's medallion path.
- **Delta** when interop with Databricks-managed destinations is required (terraform-databricks/ target).
- **Parquet (raw)** only as a landing zone; promote to Iceberg/Delta on bronze read.

See [[iceberg-ops]] and [[delta-ops]] skills for per-format ops.
