# sdp-cli-lifecycle

> The `spark-pipelines` developer loop as shell commands — `init`, `dry-run`, edit, `run`.

## Purpose

Shows how an SDP project is created, validated, and executed — entirely
through the `spark-pipelines` CLI. Where the other demos ship hand-written
transformations, this one starts from nothing: `spark-pipelines init`
scaffolds the project (spec + example transformations), and the rest of the
walkthrough drives it. It's the demo for "what does the SDP developer loop
actually look like."

## Prereqs

- Spark 4.1 + Connect server: `./lakehouse start all`
- No Unity Catalog, no Kafka, no test data. The generated example project
  targets `spark_catalog.default` with two trivial materialized views.
- `spark-pipelines` Python deps present in the Spark image (`/tmp/pylibs` —
  see `.claude/skills/sdp/unity-catalog.md` "Pre-reqs the base Spark image is
  missing").

## Run

The whole lifecycle is one script:

```bash
bash demos/sdp-cli-lifecycle/walkthrough.sh
```

It executes these `spark-pipelines` steps in order (each is a shell command —
`spark-pipelines` runs inside the `spark-master-41` container):

| # | Command | What it does |
|---|---------|--------------|
| 1 | `spark-pipelines init --name app` | Scaffolds a project: `spark-pipeline.yml` + `transformations/` with one Python and one SQL example. |
| 2 | `find app -type f` | Shows the generated structure. |
| 3 | `spark-pipelines dry-run` | Validates the dataflow graph + schemas. Writes nothing. |
| 4 | edit transformations, then `spark-pipelines dry-run` again | The inner dev loop. The edit renames the example datasets to project-specific names (`clife_nums`, `clife_even`); `dry-run` materializes nothing, so it is always safe to repeat. |
| 5 | `spark-pipelines run` | Executes — materializes both datasets. |

The standalone Connect server (`spark-connect-41`) and `spark-pipelines`'
embedded driver both bind port 15002; the script stops the standalone server
at step 0 and restarts it at the end.

### What `init` generates

```
app/
├── spark-pipeline.yml
└── transformations/
    ├── example_python_materialized_view.py   # @dp.materialized_view → spark.range(10)
    └── example_sql_materialized_view.sql     # CREATE MATERIALIZED VIEW ... WHERE id % 2 = 0
```

```yaml
# spark-pipeline.yml — init writes this; don't hand-author it
name: app
storage: file:///tmp/sdp-lifecycle/app/pipeline-storage
libraries:
  - glob:
      include: transformations/**
```

## Expected output

Step 5 ends with (dataset names are the renamed `clife_*` from step 4):

```
Flow spark_catalog.default.clife_nums has COMPLETED.
Flow spark_catalog.default.clife_even has COMPLETED.
Run is COMPLETED.
```

The lifecycle loop: `init` once, then `dry-run` to check as many times as you
iterate, then `run` to materialize.

## Teardown

```bash
bash demos/sdp-cli-lifecycle/teardown.sh
```

Drops the two datasets (`clife_nums`, `clife_even`) and removes the scaffolded
project.

## Notes — running the pipeline again

`spark-pipelines run` materializes each dataset with a fresh `CREATE TABLE`.
Running it a second time without a teardown in between fails with
`DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION` — the first run's data is still at
the dataset's storage path, and SDP will not write over it.

- `--full-refresh-all` is SDP's documented reset flag (drop state and
  recompute every dataset). On object storage it does not currently clear the
  poisoned location either — see `.claude/skills/sdp/troubleshooting.md`.
- To re-run cleanly: `bash teardown.sh`, then `bash walkthrough.sh` again.
  (`init` regenerates the example each time, and step 4 renames the datasets,
  so the walkthrough is self-contained.)
- `dry-run` has none of this constraint — it materializes nothing and can be
  repeated freely (step 4 above).
