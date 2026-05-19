---
name: iceberg-ops
description: Apache Iceberg 1.10 operations on this stack — compaction, snapshot management, time travel, schema evolution, table maintenance. Load when working with Iceberg tables, not when writing PySpark generally.
---

# Iceberg operations

Tables in this stack are registered in Unity Catalog and physically stored in SeaweedFS (S3 API). Catalog is `iceberg`; default schemas are `bronze`, `silver`, `gold`.

## Namespaces (medallion)

```sql
CREATE NAMESPACE IF NOT EXISTS iceberg.bronze;
CREATE NAMESPACE IF NOT EXISTS iceberg.silver;
CREATE NAMESPACE IF NOT EXISTS iceberg.gold;
```

## Time travel

```sql
-- by snapshot id
SELECT * FROM iceberg.silver.orders VERSION AS OF 1234567890123456789;

-- by timestamp (as-of point in time)
SELECT * FROM iceberg.silver.orders TIMESTAMP AS OF '2026-05-01 00:00:00';
```

List snapshots:

```sql
SELECT * FROM iceberg.silver.orders.snapshots ORDER BY committed_at DESC LIMIT 20;
```

## Compaction

Iceberg accumulates small files from streaming writes. Compact via the `rewrite_data_files` action:

```sql
CALL iceberg.system.rewrite_data_files(
  table => 'silver.orders',
  options => map('target-file-size-bytes', '134217728')   -- 128 MB
);
```

Schedule via Airflow (see [[airflow-3]]) — typical cadence is hourly for streaming bronze, daily for silver/gold.

## Snapshot cleanup

```sql
-- Expire snapshots older than 7 days
CALL iceberg.system.expire_snapshots(
  table => 'silver.orders',
  older_than => TIMESTAMP '2026-05-12 00:00:00',
  retain_last => 5
);

-- Remove orphaned data files (after expiration)
CALL iceberg.system.remove_orphan_files(table => 'silver.orders');
```

`remove_orphan_files` is expensive (full table scan). Run weekly, not after every write.

## Schema evolution

```sql
ALTER TABLE iceberg.silver.orders ADD COLUMN region STRING;
ALTER TABLE iceberg.silver.orders ALTER COLUMN amount TYPE DOUBLE;     -- widening only
ALTER TABLE iceberg.silver.orders RENAME COLUMN ts TO event_ts;
ALTER TABLE iceberg.silver.orders DROP COLUMN deprecated_field;
```

Iceberg uses column IDs internally so rename/drop are safe and don't break reads of older snapshots.

## Partitioning

```sql
CREATE TABLE iceberg.silver.orders (
  order_id STRING,
  event_ts TIMESTAMP,
  amount DOUBLE
)
USING iceberg
PARTITIONED BY (days(event_ts));
```

Hidden partitioning — queries on `event_ts` automatically prune partitions. Don't manually compute partition columns.

Evolve partitioning without rewriting data:

```sql
ALTER TABLE iceberg.silver.orders ADD PARTITION FIELD days(event_ts);
```

## Common pitfalls

- **Writing without specifying format** → defaults to Parquet which is what you want. Don't override unless you need Avro.
- **`CREATE TABLE ... AS SELECT`** with no `USING iceberg` → creates a Hive-style table that UC won't track properly. Always specify `USING iceberg`.
- **Concurrent writes** — Iceberg uses optimistic concurrency. If two streams write the same table, the loser retries. Acceptable; if not, serialize via Airflow.
- **Reading a table while compaction runs** — safe. Iceberg snapshots are immutable; readers see a consistent point-in-time view.

## Useful metadata queries

```sql
SELECT * FROM iceberg.silver.orders.files;       -- file-level catalog
SELECT * FROM iceberg.silver.orders.history;     -- commit history
SELECT * FROM iceberg.silver.orders.partitions;  -- partition stats
SELECT * FROM iceberg.silver.orders.manifests;   -- manifest list
```
