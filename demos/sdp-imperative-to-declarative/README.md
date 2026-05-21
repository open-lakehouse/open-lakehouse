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
- Both target `spark_catalog.default` (Delta). Distinct table prefixes
  (`imp_orders_*` vs `dec_orders_*`) keep the two versions side by side.
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
  spark_catalog.default.imp_orders_bronze: 299689 rows
  spark_catalog.default.imp_orders_silver: 285255 rows
  spark_catalog.default.imp_orders_gold: 7 rows
```

Note what the script had to spell out: session creation, the `body` JSON
schema, three explicit `write...saveAsTable` calls, and the ordering (bronze
before silver before gold) enforced only by the order of statements.

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
Flow spark_catalog.default.dec_orders_bronze has COMPLETED.
Flow spark_catalog.default.dec_orders_silver has COMPLETED.
Flow spark_catalog.default.dec_orders_gold has COMPLETED.
Run is COMPLETED.
```

SDP ran the three flows in dependency order — which it derived itself. The
`transformations/pipeline.py` file contains no ordering logic.

## Expected output

Both versions produce three Delta tables (`imp_orders_*` from the imperative
script, `dec_orders_*` from SDP) over the real order events: ~300k `bronze`
rows (parsed `order_created` events) → valid-total `silver` → 7-row daily
`gold` rollup (revenue + order count per day).

The teaching point is the diff, not the data:

| | imperative_pipeline.py | declarative/transformations/pipeline.py |
|--|--|--|
| Session | `SparkSession.builder.remote(...)` | `SparkSession.active()` |
| Per table | explicit `.write...saveAsTable()` | just `return` a DataFrame |
| Ordering | statement order, by hand | inferred from `spark.read.table()` |
| Failure handling | you re-run the whole script | SDP resolves the graph and reports per-flow status |

## Teardown

```bash
bash demos/sdp-imperative-to-declarative/teardown.sh
```

Drops all six tables and removes the pipeline storage.

## Notes

- **Run once per teardown.** `spark-pipelines run` materializes each dataset
  with a fresh `CREATE TABLE`. Re-running without a teardown in between fails
  with `DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION` — the previous run's data
  is still at the table's storage path. This is a known rough edge of SDP on
  object storage; see `.claude/skills/sdp/troubleshooting.md`.
- The imperative script uses `mode("overwrite")`, so it is safely rerunnable
  on its own.

## See also

- `.claude/skills/sdp/SKILL.md` — the OSS SDP API
- Canonical migration example: [`lisancao/pyspark-sdp`](https://github.com/lisancao/pyspark-sdp) `examples/python/03_migration_imperative_to_declarative.py`
