# SDP troubleshooting

## Reading SDP logs

```bash
docker logs spark-master-41 --tail 200 | grep -E "dlt|pipeline|expectation"
```

Pipeline events are logged as JSON. The `event_type` field is the discriminator:

| event_type | Meaning |
|------------|---------|
| `flow_definition` | Dataset registered |
| `flow_progress` | A flow is running (records read/written) |
| `flow_completed` | A flow finished successfully |
| `expectation_progress` | Per-expectation row counts |
| `flow_failure` | A flow failed — `details.message` has the cause |

For streaming runs, the metrics flush every micro-batch.

## Common errors

### `pyspark.errors.exceptions.captured.AnalysisException: Dataset 'silver_orders' is not defined`

You used `dlt.read("silver_orders")` but `silver_orders` is not decorated as `@dlt.table` or `@dlt.view`, OR it's in a different pipeline file not included via `libraries:`.

Fix: confirm the function is decorated and the file is listed in `pipeline.yml` under `libraries`.

### `Cycle detected in pipeline DAG`

You have `A → B → A`. SDP's DAG must be acyclic. Find the cycle by running with `--dry-run` and reading the printed dependency graph.

### `Schema mismatch: existing table has columns [...], new write has columns [...]`

The target table has a fixed schema; you're trying to write a different one. Either:
1. Add `@dlt.table(table_properties={"pipelines.autoMerge.enabled": "true"})` (Iceberg/Delta both support schema evolution).
2. Do an explicit `ALTER TABLE` outside the pipeline and re-run.

### Expectation failures dropping all rows

Symptom: silver table is empty after run.

Check `expectation_progress` events:
```bash
docker logs spark-master-41 | jq -r 'select(.event_type=="expectation_progress")'
```

You'll see which expectation dropped how many rows. Usually a too-strict `expect_or_drop` predicate.

### Iceberg writes fail with `NoSuchNamespaceException: silver`

The catalog doesn't have the schema yet. Create it once:

```sql
CREATE NAMESPACE IF NOT EXISTS iceberg.silver;
```

SDP creates tables, not namespaces.

### Streaming pipeline starts then immediately stops with no error

Usually `startingOffsets: "latest"` against an empty topic. Either seed the topic with one event, or switch to `earliest` for the first run.

## When to bring in [[airflow-3]]

SDP runs a pipeline. Airflow orchestrates *when* pipelines run, depends on, and after-the-fact triggers. If you find yourself writing branching logic inside SDP, lift it to an Airflow DAG that runs the SDP pipeline as a task.
