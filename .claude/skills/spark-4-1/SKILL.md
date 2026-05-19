---
name: spark-4-1
description: Apache Spark 4.1 reference. Load when writing PySpark/Spark SQL against this stack — covers DataFrame API conventions, Spark 4.1-specific features (Connect, ANSI mode, streaming UDTFs), and gotchas vs older Spark.
---

# Spark 4.1 reference

This stack runs Apache Spark **4.1.0** on Scala 2.13 with Java 21. The cluster master is `spark-master-41` (port 7078, UI 8082). Submit jobs from inside the master container:

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

## SparkSession in this stack

```python
spark = (
    SparkSession.builder.appName("my-job")
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    # The Iceberg catalog is wired via spark-defaults.conf to Unity Catalog REST.
    # In-job overrides only when you need a different catalog.
    .getOrCreate()
)
```

For Delta in the same job:

```python
.config("spark.sql.extensions",
        "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
        "io.delta.sql.DeltaSparkSessionExtension")
.config("spark.sql.catalog.spark_catalog",
        "org.apache.spark.sql.delta.catalog.DeltaCatalog")
```

## Spark 4.1 features worth knowing

- **ANSI mode is default.** `1 / 0` throws instead of returning `Infinity`. `cast("abc" AS INT)` throws. Use `try_cast()` / `try_divide()` when you want the legacy behavior locally.
- **Streaming UDTFs** (`@udtf`) are stable in 4.1. Use for row-explosion in a streaming query.
- **Spark Connect** is the recommended client transport for thin clients. Inside this stack we still use the JVM driver (the spark-master container runs both driver and connect server). For Python notebooks, prefer `SparkSession.builder.remote("sc://spark-master-41:15002")`.
- **Variant type** (semi-structured JSON without schema). Columns can be `VARIANT` and queried via `variant_get()`. Useful for landing zone tables.
- **Photon is not in OSS Spark.** Don't claim it is. Use `EXPLAIN FORMATTED` to inspect the physical plan; the Catalyst optimizer + Tungsten codegen are what's running.

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
