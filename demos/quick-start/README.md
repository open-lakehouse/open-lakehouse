# Quick start

> Your first governed lakehouse table: create a Delta table in Unity Catalog, query it through the three-level namespace, and see one Delta feature — in about five minutes.

## Purpose

The onboarding path. Connect to Spark, create a governed Delta table in Unity Catalog, query it
via `catalog.schema.table`, and watch one ACID update land in the Delta transaction log. For depth,
go to `delta-deep-dive/` (Delta mechanics) and `unity-catalog/` (governance) next.

## Prereqs

- Spark 4.1 + Connect + storage + Unity Catalog: `./lakehouse start all && ./lakehouse start unity-catalog`
- Python client deps: `poetry install`.

Transport: `SparkSession.builder.remote("sc://localhost:15002")` (or `LAKEHOUSE_SPARK_REMOTE`).

Verify all green:

```bash
./lakehouse status --json | jq '.all_healthy and .spark.connect_grpc_listening'
# expect: true
```

## Run

```bash
poetry run python demos/quick-start/quick_start.py
```

Expected stdout snippets, in order:

```
[2] Created governed Delta table unity.quickstart.products
```

```
[3] Products (price DESC):
|P001      |Laptop     |Electronics|999.99|50   |
```

Then a separate `SHOW TABLES` snippet:

```
|quickstart| products|      false|
```

```
[4] Applied +20% to Electronics; transaction history:
|1      |UPDATE   |
|0      |WRITE    |
```

## Expected output

- A governed Delta table `unity.quickstart.products` (5 rows) at
  `s3://lakehouse/warehouse/quick-start/products`.
- `[3]` shows the pre-update table (Laptop at 999.99); the +20% Electronics update is applied in
  step `[4]`, so it appears only in the history, not in the `[3]` listing.
- Delta history shows two versions: `WRITE` (0) — the data write — and `UPDATE` (1). (The demo
  writes the Delta data then registers it in UC, so there is no separate `CREATE TABLE` commit.)

> Re-runs are self-cleaning: the demo drops the UC table and clears its S3 LOCATION at the start,
> so you can run it repeatedly without a teardown in between (a stale, non-empty LOCATION would
> otherwise fail `CREATE TABLE` with `DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION`).

> Note: this demo uses Delta rather than a raw parquet write to verify storage — Delta commits via
> its transaction log, whereas plain `parquet` writes use S3A's rename committer, which SeaweedFS
> does not support.

## Teardown

```bash
bash demos/quick-start/teardown.sh
```
