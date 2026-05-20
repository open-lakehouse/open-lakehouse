# sdp-streaming-batch-sql

> One SDP pipeline, two dataset kinds in SQL — a `STREAMING TABLE` and a `MATERIALIZED VIEW` — so the streaming-vs-batch distinction is something you can read off the DDL.

## Purpose

SDP datasets come in two flavours, and which one you get is a property of the
SQL you write:

- `CREATE STREAMING TABLE ... FROM STREAM <source>` — **incremental**. Each run
  processes only newly-arrived rows, tracked by a checkpoint.
- `CREATE MATERIALIZED VIEW ...` — **batch**. Each run recomputes the whole
  result from its inputs.

This demo runs both in a single pipeline so you can compare them directly.
The streaming faucet (`sxb_raw`) ingests a seed Delta table written by
`seed.py`; the two semantics under study (`sxb_clean`, `sxb_rollup`) are pure
SQL. No Kafka, no test data.

## Prereqs

- Spark 4.1 + Connect server: `./lakehouse start all`
- `spark-pipelines` Python deps in the Spark image (`/tmp/pylibs` — see
  `.claude/skills/sdp/unity-catalog.md`).
- Targets `spark_catalog.default` (Delta). No Unity Catalog, no Kafka.

## Run

```bash
bash demos/sdp-streaming-batch-sql/run.sh
```

`run.sh` stops the standalone Connect server (it shares port 15002 with
`spark-pipelines`), copies the project into `spark-master-41`, **seeds a
source Delta table** (`seed.py` writes 300 events to `file:///tmp/sxb-seed`),
runs the pipeline once, and restarts the Connect server.

The pipeline has three datasets:

| File | Dataset | Kind |
|------|---------|------|
| `transformations/00_source.py` | `sxb_raw` | streaming table — `readStream` over the seed |
| `transformations/10_events_clean.sql` | `sxb_clean` | **streaming table** — `FROM STREAM sxb_raw` |
| `transformations/20_events_by_type.sql` | `sxb_rollup` | **materialized view** — batch aggregate |

Why a seeded Delta table and not a `rate` stream: SDP runs streaming tables
with a one-shot trigger, so a `rate` source yields zero rows (no wall-clock
time has elapsed when the run starts). Seeding a real source table keeps the
demo deterministic — see `seed.py`.

## Expected output

```
Flow spark_catalog.default.sxb_raw has COMPLETED.
Flow spark_catalog.default.sxb_clean has COMPLETED.
Flow spark_catalog.default.sxb_rollup has COMPLETED.
Run is COMPLETED.
```

Inspect the results (the SDP run uses an ephemeral metastore, so query the
Delta tables by storage path rather than by name):

```bash
docker exec spark-master-41 /opt/spark/bin/spark-sql -e \
  "SELECT event_type, event_count
   FROM delta.\`s3a://lakehouse/warehouse/sdp/sxb_rollup\` ORDER BY event_type;"
```

```
click     100
purchase  100
view      100
```

`sxb_clean` holds the 300 events ingested this run; `sxb_rollup` is their
batch rollup by type. The teaching point is in the DDL:

| | `sxb_clean` (`CREATE STREAMING TABLE`) | `sxb_rollup` (`CREATE MATERIALIZED VIEW`) |
|--|--|--|
| Processing | incremental — only new rows | full recompute every run |
| State | checkpoint under pipeline `storage` | none |
| `FROM` clause | `FROM STREAM sxb_raw` | `FROM sxb_clean` |
| Use it for | ingestion, append-only history | aggregates, dashboards, joins |

## Teardown

```bash
bash demos/sdp-streaming-batch-sql/teardown.sh
```

Drops the three tables and removes the in-container project and seed.

## Notes

- **Run once per teardown.** Each `spark-pipelines run` materializes its
  datasets with a fresh `CREATE TABLE`. A second run without `teardown.sh` in
  between fails with `DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION`: the prior
  run's data is still at the storage path and SDP will not write over it. This
  is a known rough edge of SDP on object storage — see
  `.claude/skills/sdp/troubleshooting.md`.
- `read_files` / `read_kafka` table functions are Databricks extensions and
  are **not** available in OSS Spark 4.1, which is why the streaming source
  here is a Python `spark.readStream` dataset rather than a SQL TVF.
