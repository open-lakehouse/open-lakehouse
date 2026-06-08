# sdp-imperative-to-declarative

> The same three-table medallion pipeline written twice — imperative PySpark vs Spark Declarative Pipelines — so you can see exactly what SDP takes off your plate.

## Purpose

Migration demo. `imperative_pipeline.py` is the "before": you create the
session, read, transform, and `write` each table by hand, and you order the
steps yourself. `declarative/` is the "after": three `@dp.materialized_view`
functions, no write statements, no ordering code — SDP infers the
bronze → silver → gold DAG from the table references. Read the two side by
side; the declarative version is the same logic with the orchestration
deleted.

## Prereqs

- Spark 4.1 + Connect server: `./lakehouse start all`
- The imperative script connects via `sc://localhost:15002`; the declarative
  pipeline runs through `spark-pipelines`.
- Both versions materialize into **Unity Catalog** under `unity.i2d`, with
  distinct table prefixes (`imp_orders_*` vs `dec_orders_*`). SDP does not
  create schemas — create `unity.i2d` once:

```bash
curl -s -X POST http://localhost:8081/api/2.1/unity-catalog/schemas \
  -H 'Content-Type: application/json' \
  -d '{"name":"i2d","catalog_name":"unity"}'
```

- **Generated event data** at `data/events/orders_7d.parquet` — both versions
  read the `order_created` events from it (~300k rows). Generate it with
  `./lakehouse testdata generate`, then verify:

```bash
bash demos/preflight.sh        # checks the event data is present + populated
```

## Run

### The imperative version

```bash
poetry run python demos/sdp-imperative-to-declarative/imperative_pipeline.py
```

Expected stdout (counts depend on the generated dataset):

```
imperative run complete:
  unity.i2d.imp_orders_bronze: 299689 rows
  unity.i2d.imp_orders_silver: 295888 rows
  unity.i2d.imp_orders_gold: 7 rows
```

Note what the script had to spell out: session creation, the `body` JSON
schema, three explicit `writeTo(...)` calls — each setting the `location` and
`delta.feature.catalogManaged` properties UC's connector demands — and the
ordering (bronze before silver before gold) enforced only by statement order.

### The declarative version

`spark-pipelines` embeds its own Connect server on port 15002 — stop the
standalone one first.

```bash
docker stop spark-connect-41
docker exec -u root spark-master-41 rm -rf /tmp/declarative
docker cp demos/sdp-imperative-to-declarative/declarative spark-master-41:/tmp/declarative
docker exec -u root spark-master-41 sh -c \
  'cd /tmp/declarative && PYTHONPATH=/tmp/pylibs:$PYTHONPATH /opt/spark/bin/spark-pipelines run'
docker start spark-connect-41
```

Expected stdout:

```
Flow unity.i2d.dec_orders_bronze has COMPLETED.
Flow unity.i2d.dec_orders_silver has COMPLETED.
Flow unity.i2d.dec_orders_gold has COMPLETED.
Run is COMPLETED.
```

SDP ran the three flows in dependency order — which it derived itself. The
`transformations/pipeline.py` file contains no ordering logic.

## Expected output

Both versions produce three Delta tables under `unity.i2d` (`imp_orders_*` from
the imperative script, `dec_orders_*` from SDP) over the real order events:
~300k `bronze` rows (parsed `order_created` events) → valid-total `silver` →
7-row daily `gold` rollup (revenue + order count per day).

```bash
curl -s "http://localhost:8081/api/2.1/unity-catalog/tables?catalog_name=unity&schema_name=i2d" \
  | python3 -c 'import sys,json; [print(t["name"], t["table_type"]) for t in json.load(sys.stdin)["tables"]]'
```

The teaching point is the diff, not the data:

| | imperative_pipeline.py | declarative/transformations/pipeline.py |
|--|--|--|
| Session | `SparkSession.builder.remote(...)` | `SparkSession.active()` |
| Per table | explicit `writeTo(...).tableProperty(...)` | just `return` a DataFrame |
| UC properties | you set `location` + `catalogManaged` by hand | SDP sets `location` from `table_properties` |
| Ordering | statement order, by hand | inferred from `spark.read.table()` |
| Failure handling | you re-run the whole script | SDP resolves the graph and reports per-flow status |

## Teardown

```bash
bash demos/sdp-imperative-to-declarative/teardown.sh
```

Drops all six `unity.i2d` tables (via the UC API) and removes the pipeline
storage. Delta files under `s3://lakehouse/warehouse/sdp/v2/i2d/` are left in
place — clear them with an S3 client for a fully clean slate.

## Notes

- **UC managed vs external.** The imperative `writeTo(...)` path creates UC
  *catalog-managed* tables (it must set `delta.feature.catalogManaged`); SDP
  creates UC *external* tables (it passes a `location` and cannot create
  catalog-managed tables — Delta rejects that). Both register under `unity.i2d`.
- **Run once per teardown.** `spark-pipelines run` materializes each dataset
  with a fresh `CREATE TABLE`. Re-running without a teardown in between fails —
  the previous run's data is still at the table's storage path. This is a known
  rough edge of SDP on object storage; see
  `.claude/skills/sdp/troubleshooting.md`.

## See also

- `.claude/skills/sdp/SKILL.md` — the OSS SDP API
- Canonical migration example: [`lisancao/pyspark-sdp`](https://github.com/lisancao/pyspark-sdp) `examples/python/03_migration_imperative_to_declarative.py`
