---
name: delta-ops
description: Delta Lake 4.0 operations on Spark 4.1 in this stack. Load when working with Delta tables specifically — covers OPTIMIZE, VACUUM, time travel, UniForm interop with Iceberg, and when to choose Delta over Iceberg here.
---

# Delta Lake operations

Delta Lake 4.0.1 is available alongside Iceberg in this stack. The JARs (`delta-spark_2.13-4.0.1.jar`, `delta-storage-4.0.1.jar`) are downloaded by `./lakehouse setup`. To enable Delta in a Spark session:

```python
.config("spark.sql.extensions",
        "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
        "io.delta.sql.DeltaSparkSessionExtension")
.config("spark.sql.catalog.spark_catalog",
        "org.apache.spark.sql.delta.catalog.DeltaCatalog")
```

Delta tables live under the default `spark_catalog` (not `iceberg`). Use `delta.bronze.*` namespace style if you want to mirror the medallion layout.

## When to choose Delta in this stack

- Downstream consumer is a Databricks workspace (terraform-databricks/ target).
- A demo specifically shows Delta features (DML on streaming targets, Change Data Feed).
- Otherwise, prefer Iceberg — it's the default and Unity Catalog OSS surfaces it natively.

## Reading and writing

```python
# Write
(df.write.format("delta")
   .mode("overwrite")
   .saveAsTable("delta.silver.orders"))

# Read
spark.read.format("delta").table("delta.silver.orders")

# Path-based (no catalog)
spark.read.format("delta").load("s3a://warehouse/delta/orders")
```

## OPTIMIZE (compaction)

```sql
OPTIMIZE delta.silver.orders;
OPTIMIZE delta.silver.orders WHERE event_date >= '2026-05-01';
OPTIMIZE delta.silver.orders ZORDER BY (customer_id);   -- multi-dim clustering
```

Z-ordering helps point queries on the listed columns. Cost: rewrite. Don't z-order on a high-cardinality column you don't query against.

## VACUUM (file cleanup)

```sql
VACUUM delta.silver.orders RETAIN 168 HOURS;   -- 7 days, the minimum safe default
```

Lower retention than 7 days is possible (`spark.databricks.delta.retentionDurationCheck.enabled = false`) but **don't** — concurrent readers may be using files newer than the new horizon.

## Time travel

```sql
SELECT * FROM delta.silver.orders VERSION AS OF 42;
SELECT * FROM delta.silver.orders TIMESTAMP AS OF '2026-05-01 00:00:00';

-- Inspect history
DESCRIBE HISTORY delta.silver.orders;
```

## MERGE INTO

```sql
MERGE INTO delta.silver.orders t
USING staging s ON t.order_id = s.order_id
WHEN MATCHED AND s.event_ts > t.event_ts THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

`MERGE` is the canonical Delta upsert. Iceberg has the same syntax — most code is portable.

## UniForm (Delta ↔ Iceberg interop)

Delta tables can expose an Iceberg metadata layer for read-only access by Iceberg readers (DuckDB, Trino):

```sql
CREATE TABLE delta.silver.orders (...)
USING delta
TBLPROPERTIES (
  'delta.universalFormat.enabledFormats' = 'iceberg',
  'delta.enableIcebergCompatV2' = 'true'
);
```

The table is still Delta-canonical for writes; Iceberg readers see a synthesized snapshot. Useful when your write path is Delta-native but your downstream is Iceberg-only.

## Change Data Feed (CDF)

Enable on table creation or via `ALTER`:

```sql
ALTER TABLE delta.silver.orders SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

Read changes:

```sql
SELECT * FROM table_changes('delta.silver.orders', 100, 105);   -- versions 100..105
```

CDF emits per-row change records (`_change_type` ∈ insert/update_preimage/update_postimage/delete). Use for incremental downstream pipelines without re-reading the full table.

## Delta vs Iceberg cheat sheet (this stack)

| Need | Choose |
|------|--------|
| Multi-engine read (DuckDB/Trino/etc.) via UC OSS REST | Iceberg |
| Hand-off to Databricks | Delta |
| Time travel + schema evolution | Either (both support it) |
| Change Data Feed | Delta (Iceberg has incremental reads, different API) |
| Hidden partitioning | Iceberg |
| Liquid clustering | Delta (`CLUSTER BY`) |
| Default for this stack's medallion path | Iceberg |

## Common pitfalls

- **`spark_catalog` vs `delta` namespace** — by default Delta lives under `spark_catalog`. Saving as `saveAsTable("delta.silver.orders")` requires a registered catalog called `delta`, which you'd have to wire explicitly. Use `spark_catalog.silver.orders` or path-based writes if you haven't set up a `delta` catalog.
- **Mixing Iceberg and Delta extensions** — the order of `spark.sql.extensions` matters when both are listed. Iceberg first, Delta second, comma-separated.
- **`ALTER TABLE` doesn't auto-OPTIMIZE** — schema changes don't compact. Run OPTIMIZE explicitly after large evolution events.
