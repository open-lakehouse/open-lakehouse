# SDP troubleshooting

## Running and reading output

```bash
# from the pipeline project dir inside the Spark container
docker exec spark-master-41 sh -c \
  'cd /tmp/<pipeline> && spark-pipelines run'
```

Progress prints as `Flow <catalog>.<schema>.<name> is QUEUED / PLANNING /
STARTING / RUNNING / has COMPLETED`, ending with `Run is COMPLETED`. A failure
prints a Python traceback ending in a `pyspark.errors.exceptions.connect.*`
exception — the useful line is the last one.

## Errors seen on this stack (verified)

### `PIPELINE_SPEC_UNEXPECTED_FIELD: target`
The spec field is `schema:` (or `database:`), not `target:`. Allowed spec
fields: `name`, `storage`, `catalog`, `database`/`schema`, `configuration`,
`libraries`.

### `ATTEMPT_ANALYSIS_IN_PIPELINE_QUERY_FUNCTION`
A pipeline function triggered DataFrame analysis — `spark.createDataFrame([...])`,
`.collect()`, `.count()`, `.show()`. Pipeline functions must return a lazy
DataFrame. Build synthetic data with `spark.range(n).selectExpr(...)` instead.

### `CANNOT_MODIFY_STATIC_CONFIG`
The spec's `configuration:` block tried to set a static Spark config
(`spark.sql.extensions`, `spark.sql.warehouse.dir`,
`spark.connect.grpc.binding.port`). Those are fixed at JVM startup — set them
in `spark-defaults.conf`, keep the spec's `configuration:` block minimal.

### bare `java.lang.AssertionError: assertion failed`
Targeting `catalog: unity` without `table_properties={"location": ...,
"provider": "delta"}`. UC's connector asserts on both. See
[unity-catalog.md](unity-catalog.md).

### `Table does not support truncates`
Re-running over an existing UC table — UC's connector has no truncate. Drop
the table first (`curl -X DELETE .../tables/unity.<schema>.<name>`), or
`spark-pipelines run --full-refresh-all` after dropping.

### `BindException: ... 15002`
`spark-pipelines` embeds its own Connect server on 15002 — the standalone
`spark-connect-41` container holds that port. Stop one:
`docker stop spark-connect-41` before an SDP run, restart it after.

### `ModuleNotFoundError` from `pyspark/pipelines/cli.py`
The Spark image lacks `spark-pipelines`' Python deps. Install
`pyyaml pandas pyarrow grpcio grpcio-status protobuf zstandard` — see
[unity-catalog.md](unity-catalog.md) "Pre-reqs the base Spark image is missing".

### `Dataset '<name>' is not defined`
A `spark.read.table("<name>")` references a dataset that isn't decorated, or
lives in a file not matched by the spec's `libraries: glob`. Confirm the
function is decorated and the file is under `transformations/`.

### Cycle in the DAG
`A` reads `B` and `B` reads `A`. The pipeline graph must be acyclic.
`spark-pipelines dry-run` validates the graph without executing.

### Streaming pipeline starts then stops with no error
`startingOffsets: "latest"` against an empty Kafka topic. Seed the topic or
use `earliest` for the first run.

## What does NOT exist in OSS SDP

If you see these in a doc or an LLM suggestion, it's Databricks DLT, not OSS:

- `import dlt`, `@dlt.*`, `dlt.read()`
- `@dp.expect*` / any expectations API — `event_log()` expectation metrics
- `APPLY CHANGES INTO` / `create_auto_cdc_flow` / Auto CDC (SPARK-56249 unmerged)
- `refresh_interval` on a materialized view
- an injected `spark` variable — call `SparkSession.active()`

## When to bring in Airflow

SDP runs *a* pipeline. Scheduling, cross-pipeline dependencies, and retries are
[[airflow-3]]'s job — an Airflow DAG that invokes `spark-pipelines run` as a
task. If you're writing branching logic inside SDP, lift it to Airflow.
