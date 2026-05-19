---
name: delta-ops
description: Delta Lake 4.0 operations on Spark 4.1 in this stack. Load when working with Delta tables specifically — covers OPTIMIZE, VACUUM, time travel, UniForm interop with Iceberg, and when to choose Delta over Iceberg here.
---

# Delta Lake operations

Delta Lake 4.0.1 is wired by default in this stack. The JARs (`delta-spark_2.13-4.0.1.jar`, `delta-storage-4.0.1.jar`) ship via `./lakehouse setup`, and `config/spark/spark-defaults.conf.example` enables both Iceberg and Delta extensions plus registers `spark_catalog` as the `DeltaCatalog`. You don't need per-session config — just write Delta.

```python
# Sanity check the extensions on a fresh Connect session
spark.sql("SHOW CATALOGS").show()
# expect: iceberg, spark_catalog
```

Delta tables live under the default `spark_catalog` (not `iceberg`). Address them as `spark_catalog.<schema>.<table>`, or path-based with `delta.\`s3a://warehouse/path\``. Use a `spark_catalog.bronze.*` namespace pattern if you want to mirror the medallion layout used for Iceberg.

## When to choose Delta in this stack

- Downstream consumer is a Databricks workspace (terraform-databricks/ target).
- A demo specifically shows Delta features (DML on streaming targets, Change Data Feed).
- Otherwise, prefer Iceberg — it's the default and Unity Catalog OSS surfaces it natively.

## Reading and writing

```python
# Write
(df.write.format("delta")
   .mode("overwrite")
   .saveAsTable("spark_catalog.silver.orders"))

# Read
spark.read.format("delta").table("spark_catalog.silver.orders")

# Path-based (no catalog)
spark.read.format("delta").load("s3a://warehouse/delta/orders")
```

## OPTIMIZE (compaction)

```sql
OPTIMIZE spark_catalog.silver.orders;
OPTIMIZE spark_catalog.silver.orders WHERE event_date >= '2026-05-01';
OPTIMIZE spark_catalog.silver.orders ZORDER BY (customer_id);   -- multi-dim clustering
```

Z-ordering helps point queries on the listed columns. Cost: rewrite. Don't z-order on a high-cardinality column you don't query against.

## VACUUM (file cleanup)

```sql
VACUUM spark_catalog.silver.orders RETAIN 168 HOURS;   -- 7 days, the minimum safe default
```

Lower retention than 7 days is possible (`spark.databricks.delta.retentionDurationCheck.enabled = false`) but **don't** — concurrent readers may be using files newer than the new horizon.

## Time travel

```sql
SELECT * FROM spark_catalog.silver.orders VERSION AS OF 42;
SELECT * FROM spark_catalog.silver.orders TIMESTAMP AS OF '2026-05-01 00:00:00';

-- Inspect history
DESCRIBE HISTORY spark_catalog.silver.orders;
```

## MERGE INTO

```sql
MERGE INTO spark_catalog.silver.orders t
USING staging s ON t.order_id = s.order_id
WHEN MATCHED AND s.event_ts > t.event_ts THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

`MERGE` is the canonical Delta upsert. Iceberg has the same syntax — most code is portable.

## UniForm (Delta ↔ Iceberg interop)

Delta tables can expose an Iceberg metadata layer for read-only access by Iceberg readers (DuckDB, Trino):

```sql
CREATE TABLE spark_catalog.silver.orders (...)
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
ALTER TABLE spark_catalog.silver.orders SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

Read changes:

```sql
SELECT * FROM table_changes('spark_catalog.silver.orders', 100, 105);   -- versions 100..105
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

- **Catalog name is `spark_catalog`, not `delta`.** Our `spark-defaults.conf` registers `DeltaCatalog` on Spark's default catalog name (`spark_catalog`). If you see code that addresses tables as `delta.silver.orders`, it's from a different setup — either rename to `spark_catalog.silver.orders` or use path-based writes.
- **Mixing Iceberg and Delta extensions** — the order of `spark.sql.extensions` matters when both are listed. Iceberg first, Delta second, comma-separated.
- **`ALTER TABLE` doesn't auto-OPTIMIZE** — schema changes don't compact. Run OPTIMIZE explicitly after large evolution events.
