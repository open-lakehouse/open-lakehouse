# Unity Catalog governance

> The three-level namespace, external Delta registration, metadata discovery (SQL + REST), and a cross-schema join on Unity Catalog OSS.

## Purpose

Shows how Unity Catalog OSS governs data on this stack: the `catalog.schema.table` namespace,
schema management, registering external Delta tables through the UC Spark connector, discovering
metadata via both SQL (`DESCRIBE`) and the UC REST API, and joining tables across schemas. This is
the governance counterpart to `delta-deep-dive/` (which is about Delta mechanics).

## Prereqs

- Spark 4.1 + Connect + storage + Unity Catalog: `./lakehouse start all && ./lakehouse start unity-catalog`
- Needs Spark, storage (SeaweedFS), and the UC server (`localhost:8081`). No Kafka/MLflow.
- Python client deps: `poetry install`.

Transport: `SparkSession.builder.remote("sc://localhost:15002")` (or `LAKEHOUSE_SPARK_REMOTE`).
UC REST base overridable via `UC_API` (default `http://localhost:8081/api/2.1/unity-catalog`).

Verify all green:

```bash
./lakehouse status --json | jq '.all_healthy and .spark.connect_grpc_listening'
# expect: true
```

## Run

```bash
poetry run python demos/unity-catalog/uc_governance.py
```

Expected stdout snippets, in order:

```
[1] Catalogs (UC REST): [... 'unity' ...]  (+ spark_catalog session default)
```

(The catalog list always includes `unity`; `managed_demo` only appears once the
`sdp-medallion` demo has created it. Order is not guaranteed.)

```
[3] Registered unity.uc_demo_core.dim_regions and unity.uc_demo_core.orders (external Delta)
|uc_demo_core|dim_regions|      false|
|uc_demo_core|     orders|      false|
```

```
[4] ... Type  EXTERNAL ... Location  s3://lakehouse/warehouse/unity-catalog/dim_regions ... Provider  delta
```

```
[5] UC REST tables/dim_regions: type=EXTERNAL format=DELTA location=s3://lakehouse/warehouse/unity-catalog/dim_regions
```

```
[6] Cross-schema join -> unity.uc_demo_analytics.revenue_by_region:
|Europe       |EUR     |2          |260.0  |
|North America|USD     |2          |200.0  |
```

## Expected output

- Two schemas in `unity`: `uc_demo_core`, `uc_demo_analytics`.
- Three external Delta tables under `s3://lakehouse/warehouse/unity-catalog/`:
  `uc_demo_core.dim_regions` (4 rows), `uc_demo_core.orders` (6 rows),
  `uc_demo_analytics.revenue_by_region` (4 rows, deterministic: Europe 260, NA 200, AP 150, SA 90).
- Metadata visible via `DESCRIBE EXTENDED` (columns + location) and the UC REST API
  (type / format / location).

### Notes on UC OSS 0.5.0 behavior

- **`LOCATION` must use `s3://`**, not `s3a://` — UC credential vending rejects the `s3a` scheme
  (`Unsupported URI scheme: s3a`). Spark still reads/writes the bytes over the `s3a` filesystem.
- **External tables are (re)created by writing Delta then registering** — the demo's
  `recreate_delta_table` helper does `DROP TABLE IF EXISTS` → clear the S3 prefix → write the
  DataFrame with Delta `overwrite` → `CREATE TABLE … USING delta LOCATION 's3://…'`. The
  `overwrite` lays down a fresh `_delta_log` even over a lingering SeaweedFS directory, so re-runs
  are deterministic (a bare `CREATE TABLE … LOCATION` on a non-empty prefix fails
  `DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION`). Note: **not `CREATE TABLE AS SELECT`** (CTAS
  triggers path-credential vending that fails for ad-hoc locations), and a location-less create is
  treated as catalog-managed (see `demos/sdp-medallion/`).
- **`SHOW CATALOGS` over Connect** lists only the session-default `spark_catalog`; the UC v2
  catalogs register lazily. The REST API is the authoritative catalog list.
- **The `/tables` REST API omits column metadata** for connector-registered external tables;
  columns live in the Delta log and surface via `DESCRIBE`.

## Teardown

```bash
bash demos/unity-catalog/teardown.sh
```
