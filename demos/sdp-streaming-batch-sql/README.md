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
`seed.py` from the generated event dataset; the two semantics under study
(`sxb_clean`, `sxb_rollup`) are pure SQL.

## Prereqs

- Spark 4.1 + Connect server: `./lakehouse start all`
- `spark-pipelines` Python deps in the Spark image (`/tmp/pylibs` — see
  `.claude/skills/sdp/unity-catalog.md`).
- **Generated event data** at `data/events/orders_7d.parquet` — `seed.py` reads
  the order-lifecycle events from it. Generate with `./lakehouse testdata
  generate`; `run.sh` runs `demos/preflight.sh` first to confirm it is present.
- Targets `spark_catalog.default` (Delta). No Kafka.

## Run

```bash
bash demos/sdp-streaming-batch-sql/run.sh
```

`run.sh` runs the preflight check, stops the standalone Connect server (it
shares port 15002 with `spark-pipelines`), copies the project into
`spark-master-41`, **seeds a source Delta table** (`seed.py` reads the
order-lifecycle events — everything except the high-volume `driver_ping` GPS
noise — into `file:///tmp/sxb-seed`), runs the pipeline once, and restarts the
Connect server.

The pipeline has three datasets:

| File | Dataset | Kind |
|------|---------|------|
| `transformations/00_source.py` | `sxb_raw` | streaming table — `readStream` over the seed |
| `transformations/10_events_clean.sql` | `sxb_clean` | **streaming table** — `FROM STREAM sxb_raw` |
| `transformations/20_events_by_type.sql` | `sxb_rollup` | **materialized view** — batch aggregate |

Why a seeded Delta table rather than a live stream: the SDP run consumes the
seed with a one-shot trigger, so the source must already hold its rows when
the run starts. Seeding from the generated parquet keeps the demo
deterministic — see `seed.py`. (`read_files` / `read_kafka` SQL functions that
would let a SQL streaming table read a stream directly are Databricks
extensions, absent from OSS Spark 4.1.)

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
   FROM delta.\`s3a://lakehouse/warehouse/sdp/sxb_rollup\` ORDER BY event_count DESC;"
```

```
kitchen_started   299820
driver_arrived    299771
order_ready       299762
driver_picked_up  299705
order_created     299689
delivered         299664
kitchen_finished  299618
```

`sxb_clean` holds the ~2.1M order-lifecycle events ingested this run;
`sxb_rollup` is their batch rollup by event type. The teaching point is in the
DDL:

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
- The streaming source is a Python `@dp.table` (`spark.readStream`) because a
  SQL streaming table needs its raw source defined in Python — `read_files` /
  `read_kafka` SQL functions are Databricks-only.
