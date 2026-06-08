# sdp-medallion

> Bronze -> Silver -> Gold built with Spark Declarative Pipelines, materialized as Delta tables in Unity Catalog OSS.

## Purpose

Shows the SDP runtime driving a three-stage medallion pipeline whose outputs
register in Unity Catalog OSS as Delta tables. It is also the reference for the
non-obvious `table_properties` pattern required to make SDP write to UC - see
[`.claude/skills/sdp/unity-catalog.md`](../../.claude/skills/sdp/unity-catalog.md)
for the full why.

Transport: `spark-pipelines` CLI (which spawns its own embedded Spark Connect
driver). Not the standalone Connect server.

## Prereqs

- Spark 4.1 + UC OSS running: `./lakehouse start all && ./lakehouse start unity-catalog`
- UC OSS image `newfrontdocker/unitycatalog:v0.4.1` (set in `docker-compose-unity-catalog.yml`)
- `config/spark/spark-defaults.conf` wired with: Delta 4.2.0 + UC Spark connector
  JARs, the `unity` catalog, `spark_catalog = DeltaCatalog`, `spark.hadoop.fs.s3.impl`,
  and real S3 credentials.
- The `unity.bronze` schema exists:
  ```bash
  curl -s -X POST http://localhost:8081/api/2.1/unity-catalog/schemas \
    -H 'Content-Type: application/json' \
    -d '{"name":"bronze","catalog_name":"unity"}'
  ```
- **`spark-pipelines` Python deps in the Spark image.** The stock
  `apache/spark:4.1.0` image is missing `pyyaml pandas pyarrow grpcio
  grpcio-status protobuf zstandard`. Until the open-lakehouse Spark Dockerfile
  pre-installs them, install into the container manually:
  ```bash
  docker exec -u root spark-master-41 pip install --target=/tmp/pylibs \
    pyyaml pandas pyarrow grpcio grpcio-status protobuf zstandard
  ```
  and prefix runs with `PYTHONPATH=/tmp/pylibs:$PYTHONPATH`.

## Run

The standalone Connect server (`spark-connect-41`) and SDP's embedded driver
both bind port 15002 - stop the standalone one first.

```bash
# 1. Free port 15002
docker stop spark-connect-41
```

```bash
# 2. Copy the demo into the Spark container and run the pipeline
docker cp demos/sdp-medallion spark-master-41:/tmp/sdp-medallion
docker exec spark-master-41 sh -c \
  'cd /tmp/sdp-medallion && PYTHONPATH=/tmp/pylibs:$PYTHONPATH /opt/spark/bin/spark-pipelines run'
```

Expected stdout snippet:

```
Flow unity.bronze.orders_bronze has COMPLETED.
Flow unity.bronze.orders_silver has COMPLETED.
Flow unity.bronze.orders_gold has COMPLETED.
Run is COMPLETED.
```

```bash
# 3. Restart the standalone Connect server for client work
docker start spark-connect-41
```

## Expected output

Three Delta tables registered in UC under `unity.bronze`:

```bash
curl -s "http://localhost:8081/api/2.1/unity-catalog/tables?catalog_name=unity&schema_name=bronze" \
  | python3 -c 'import sys,json; [print(t["name"], t["data_source_format"], t["storage_location"]) for t in json.load(sys.stdin)["tables"]]'
```

```
orders_bronze  DELTA  s3://lakehouse/warehouse/sdp/v2/bronze/orders_bronze
orders_silver  DELTA  s3://lakehouse/warehouse/sdp/v2/bronze/orders_silver
orders_gold    DELTA  s3://lakehouse/warehouse/sdp/v2/bronze/orders_gold
```

Read them back through the standalone Connect server:

```python
from pyspark.sql import SparkSession
spark = SparkSession.builder.remote("sc://localhost:15002").getOrCreate()
spark.sql("SELECT * FROM unity.bronze.orders_gold ORDER BY order_date").show()
```

`orders_bronze` has 5 synthetic rows; `orders_silver` filters `amount > 0`;
`orders_gold` is a per-day revenue rollup.

## Teardown

```bash
bash demos/sdp-medallion/teardown.sh
```

Drops the three UC tables and clears the pipeline storage. The Delta files
under `s3://lakehouse/warehouse/sdp/` are left in place - delete that prefix
with an S3 client for a fully clean slate (re-running over existing tables
fails: UC's connector doesn't support truncate).

## Known sharp edges

This demo exists partly to document them. All covered in detail in
[`.claude/skills/sdp/unity-catalog.md`](../../.claude/skills/sdp/unity-catalog.md):

- Transformations targeting UC **must be Python** (`@dp.materialized_view`),
  not `.sql` - SDP rejects the SQL `LOCATION` clause.
- Every UC-targeted table needs `table_properties={"location": "s3://...",
  "provider": "delta"}`. Both keys. `s3://` scheme, not `s3a://`.
- Re-runs over an existing table fail (no truncate support) - teardown first.
