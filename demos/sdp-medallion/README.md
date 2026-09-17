# sdp-medallion

> Bronze -> Silver -> Gold built with Spark Declarative Pipelines, materialized as
> **catalog-managed Delta tables** in Unity Catalog OSS.

## Purpose

Shows the SDP runtime driving a three-stage medallion pipeline whose outputs
register in Unity Catalog OSS as **catalog-managed** Delta tables — the catalog
assigns each table's storage under its `storage_root`, so the transformations
carry **no explicit `location`**. This is the concrete win of UC 0.5.0 +
Delta 4.3.1: only the raw ingest stays Python; silver and gold are pure
declarative **SQL** (`.sql`), which catalog-managed Delta makes possible. See
[`.claude/skills/sdp/unity-catalog.md`](../../.claude/skills/sdp/unity-catalog.md)
for the full mechanism and the exact version requirements.

Transport: `spark-pipelines` CLI (which spawns its own embedded Spark Connect
driver). Not the standalone Connect server.

## Prereqs

- Spark 4.1 + UC OSS running: `./lakehouse start all && ./lakehouse start unity-catalog`
- UC OSS image `unitycatalog/unitycatalog:v0.5.0` (set in `docker-compose-unity-catalog.yml`).
- **Delta 4.3.1 + the UC 0.5.x Spark connector family** (connector 0.4.1 +
  client 0.5.1 + hadoop 0.5.1) — wired in `config/spark/spark-defaults.conf`.
  Catalog-managed Delta does NOT work on Delta 4.2.0/4.3.0 or older connectors.
- `config/spark/spark-defaults.conf` registers `spark.sql.catalog.managed_demo`
  as `UCSingleCatalog` (alongside `unity`).
- The **`managed_demo` catalog must exist with a `storage_root`** and the
  `medallion_demo` schema (the pipeline's target). Create once:
  ```bash
  curl -s -X POST http://localhost:8081/api/2.1/unity-catalog/catalogs \
    -H 'Content-Type: application/json' \
    -d '{"name":"managed_demo","storage_root":"s3://lakehouse/warehouse/managed"}'
  curl -s -X POST http://localhost:8081/api/2.1/unity-catalog/schemas \
    -H 'Content-Type: application/json' \
    -d '{"name":"medallion_demo","catalog_name":"managed_demo"}'
  ```
- **`spark-pipelines` Python deps in the Spark image.** The stock
  `apache/spark:4.1.0` image lacks `pyyaml pandas pyarrow grpcio grpcio-status
  protobuf zstandard`; install them into the container (see `run.sh`, which does
  this for you). Behind a firewall, set `PIP_INDEX_URL=<mirror>/simple`.

## Run

The simplest path — one command that seeds a small self-contained dataset,
ensures the catalog, installs the deps, and runs the pipeline:

```bash
bash demos/sdp-medallion/run.sh
```

<details>
<summary>What run.sh does (and the manual equivalent)</summary>

1. Ensures the `managed_demo` catalog (with `storage_root`) + `medallion_demo` schema.
2. Drops any prior medallion tables — **SDP cannot re-materialize (ALTER) an
   existing UC table**, so a re-run must drop first.
3. Seeds `data/events/orders_7d.parquet` + `data/dimensions/locations.parquet`
   via `seed.py` (24 order events, 4 locations).
4. Installs the `spark-pipelines` deps into `spark-master-41`.
5. Frees port 15002 (`docker stop spark-connect-41`), then runs `spark-pipelines`
   with a conf that **drops `spark.master`** — SDP uses its own embedded Connect
   driver, and `spark.master` + `--remote` conflict (`Remote cannot be specified
   with master`). Restarts the Connect server afterward.

```bash
docker cp demos/sdp-medallion spark-master-41:/tmp/sdp-medallion
docker exec spark-master-41 sh -c \
  'mkdir -p /tmp/pconf && grep -v "^spark.master " /opt/spark/conf/spark-defaults.conf > /tmp/pconf/spark-defaults.conf'
docker stop spark-connect-41
docker exec spark-master-41 sh -c \
  'cd /tmp/sdp-medallion && SPARK_CONF_DIR=/tmp/pconf PYTHONPATH=/tmp/pylibs:$PYTHONPATH /opt/spark/bin/spark-pipelines run'
docker start spark-connect-41
```
</details>

Expected stdout snippet:

```
Flow managed_demo.medallion_demo.dim_locations has COMPLETED.
Flow managed_demo.medallion_demo.orders_bronze has COMPLETED.
Flow managed_demo.medallion_demo.orders_enriched has COMPLETED.
Flow managed_demo.medallion_demo.gold_hourly_metrics has COMPLETED.
Flow managed_demo.medallion_demo.gold_brand_summary has COMPLETED.
Run is COMPLETED.
```

> Benign noise: `WARN UpdateMetricsHook: … reportMetrics call failed with: 404`.
> UC OSS doesn't implement the Delta metrics-report endpoint; the flows complete
> regardless. Not an error.

## Expected output

Five **catalog-managed** Delta tables in UC under `managed_demo.medallion_demo`,
each with a UC-assigned `storage_location` under the catalog's storage root
(`s3://lakehouse/warehouse/managed/__unitystorage/catalogs/<id>/tables/<id>`):

```bash
curl -s "http://localhost:8081/api/2.1/unity-catalog/tables?catalog_name=managed_demo&schema_name=medallion_demo" \
  | python3 -c 'import sys,json; [print(t["name"], t["data_source_format"]) for t in json.load(sys.stdin)["tables"]]'
```

```
orders_bronze        DELTA
dim_locations        DELTA
orders_enriched      DELTA
gold_hourly_metrics  DELTA
gold_brand_summary   DELTA
```

Read them back through the standalone Connect server (register the catalog on
the client the same way `spark-defaults` does):

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder.remote("sc://localhost:15002").getOrCreate()
spark.sql("SELECT * FROM managed_demo.medallion_demo.gold_brand_summary "
          "ORDER BY total_revenue DESC").show()
```

`orders_bronze` holds the seeded events; `orders_enriched` parses the JSON body
and joins the city dimension; the two `gold_*` tables are per-brand and
per-hour/city revenue rollups.

## Teardown

```bash
bash demos/sdp-medallion/teardown.sh
```

Drops the five UC tables (which releases their catalog-managed storage under
`__unitystorage/`) and clears the pipeline storage.

## Known sharp edges

All covered in detail in
[`.claude/skills/sdp/unity-catalog.md`](../../.claude/skills/sdp/unity-catalog.md):

- **Catalog-managed Delta needs the exact versions** — Delta 4.3.1 + the UC 0.5.x
  connector family. On 4.2.0 a location-less create falls back to `spark_catalog`;
  on 4.3.0 the connector NPEs.
- **Required table properties** — every catalog-managed table must set
  `delta.feature.catalogManaged=supported` **and** both
  `delta.checkpoint.writeStatsAsJson=true` / `...writeStatsAsStruct=true`, or UC's
  `createTable` returns 400.
- **No in-place re-run** — SDP tries to ALTER an existing table on refresh and UC
  rejects it (`Altering a table is not supported yet`). Drop the tables first
  (`teardown.sh`, or `run.sh` does it automatically).
- **Reading external files stays Python** — a SQL `FROM parquet.\`path\`` gets
  catalog-qualified by SDP and fails; ingest in a Python `@dp.materialized_view`,
  transform in SQL.
- **`spark.master` vs `spark-pipelines`** — the demo strips `spark.master` from
  the conf it hands SDP (see `run.sh`); leaving it set errors with
  `Remote cannot be specified with master`.
