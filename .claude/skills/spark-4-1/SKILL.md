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
docker exec -u root spark-master-41 /opt/spark/bin/spark-submit /scripts/<your-job>.py
```

Mounts: `./scripts/` → `/scripts/`, `./jars/` → `/opt/spark/jars-extra/`.

### spark-submit on this stack — three gotchas

The stock `apache/spark:4.1.0` image has rough edges that bite the first time
you reach for spark-submit on this cluster. All three are environmental, not
Spark bugs:

1. **Run with `-u root`.** The default `spark` user has `home=/nonexistent`
   in `/etc/passwd`, and `user.home` is hardcoded by the JVM at start (env
   `HOME=` doesn't help). Ivy can't write its resolution cache, the
   checkpoint dir can't be created, the SDP `pylibs` aren't on the path.
   `docker exec -u root spark-master-41 …` makes all of that go away.
2. **`--packages` doesn't work; use `--jars`.** Same `user.home=/nonexistent`
   reason — Ivy fails creating `/nonexistent/.ivy2.5.2/cache/resolved-…-1.0.xml`.
   `spark.jars.ivy=/root/.ivy2` and `--driver-java-options -Duser.home=/root`
   are both ignored. Pre-download required jars to `jars/`
   (`scripts/tools/download-jars.sh`) and pass `--jars
   /opt/spark/jars-extra/foo.jar,/opt/spark/jars-extra/bar.jar`.
3. **In-container, address peers by service name.** The stack runs on the
   `lakehouse-network` bridge, so from inside `spark-master-41` use
   `kafka:9092`, `unity-catalog:8080`, `seaweedfs:8333`, `postgres:5432`,
   `spark-master-41:7078`. The `localhost:HOSTPORT` form is for **host** clients
   (`sc://localhost:15002`, `localhost:8081`, `localhost:8333`, `localhost:9092`).
   These service-name endpoints are already wired in `spark-defaults.conf`, so a
   normal `spark-submit` needs no `-e KAFKA_BOOTSTRAP_SERVERS=…` override.

Loud-but-ignorable on startup: `ClassNotFoundException` for
`IcebergSparkSessionExtensions`, `DeltaSparkSessionExtension`, and
`S3AFileSystem` print because `spark-defaults.conf` lists them as extensions
but the relevant jars aren't on the submit classpath. If your job needs them,
add the iceberg / delta / hadoop-aws jars to `--jars`. If it doesn't (e.g. a
pure Kafka→Kafka stream), ignore them — the job still starts.

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
- **Structured Streaming** works including watermarks, `foreachBatch`, and a Delta sink into Unity Catalog (`unity.<schema>.<table>`). The `iceberg.` REST catalog is **read-only** on this stack, so it is not a streaming write target. See [[kafka-streaming]] for the realtime demo pattern.

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

# Write to Unity Catalog as DELTA — the primary write path on this stack.
# The `iceberg.` catalog is READ-ONLY (UC OSS 0.5.0 exposes no Iceberg write
# endpoints — CLAUDE.md Golden Rule #1); read Iceberg via `iceberg.<schema>.<t>`.
deduped.writeTo("unity.silver.orders").using("delta").createOrReplace()

# Delta merge (upsert)
deduped.createOrReplaceTempView("staging")
spark.sql("""
  MERGE INTO unity.silver.orders AS t
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

- **Delta** — the **write path** on this stack. All demos (medallion, streaming)
  write Delta into Unity Catalog (`unity.<schema>.<table>`). Time travel, schema
  evolution, catalog-managed tables, and the Databricks hand-off all live here.
- **Iceberg** — **read-only** on this stack (UC OSS exposes no Iceberg write).
  Use `iceberg.<schema>.<table>` for cross-engine reads (DuckDB/Trino/PyIceberg)
  of tables registered via UC. Do not target it as a write sink.
- **Parquet (raw)** only as a landing zone; promote to Delta on bronze read.

See [[iceberg-ops]] and [[delta-ops]] skills for per-format ops.
