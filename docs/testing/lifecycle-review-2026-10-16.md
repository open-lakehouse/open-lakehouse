# Lifecycle review validation — 16 October 2026

This follow-up tests the combined PR #31 tree based on
`ce6d6b8bec6ed569d81e73877fedbac8074d78a0`, with the test corrections in this
commit. It is not a claim of a passing full-stack release gate.

## Corrections made during testing

- Follow connectivity scripts in `scripts/connectivity`, instead of obsolete
  paths directly under `scripts`.
- Check Airflow's bridge network and PostgreSQL service DNS, rather than requiring
  host networking. Compile the shipped DAG documentation template and user DAGs;
  the default user DAG directory is intentionally empty.
- Check the current `demos/unity-catalog/uc_governance.py` entrypoint, Spark Connect
  transport and governance schemas, instead of a removed medallion demo.
- Align pre-commit's Black pin with the project's minimum supported Black 26
  release. Black 25 had reformatted unrelated files differently.
- Add narrow scanner annotations to public legacy defaults, synthetic test values
  and container-name mappings. No real credential findings were baselined away.

## Results

| Check | Result |
| --- | --- |
| Complete Python `tests/` run, including integration collection | 453 passed, 22 failed, 77 skipped |
| Non-integration tests within that run | All 362 passed |
| Dashboard Vitest | All 85 passed, across 10 files |
| TypeScript `tsc --noEmit --incremental false` | Passed |
| Dashboard production `next build` | Passed |
| Standalone Spark file-format module without the Iceberg JAR | All 23 passed |
| Standalone local Iceberg CRUD module with the pinned JAR | All 9 passed |
| Corrected Airflow, full-stack, SeaweedFS and UC test modules | 49 passed; 8 live-service checks skipped |
| Ruff and Black across `scripts`, `tests`, `demos` | Passed |
| Bash syntax and ShellCheck for changed shell entrypoints | Passed |
| Nine Compose configurations | Passed rendering without a Docker daemon |
| Focused Bandit scan of the three credential/profile/health helpers | No reported issues after narrow public-default annotations |
| Direct secrets scan of changed credential/profile and regression sources | No findings |
| Supported pre-commit hooks | Passed; secrets-baseline, broad Bandit and Docker-backed Hadolint hooks explicitly excluded |

The complete Python run's 22 failures are in generic Spark file-format tests:
Python workers fail to launch or exit unexpectedly when the Iceberg runtime JAR
is on that run's classpath. The same module passes without that JAR, and the
Iceberg CRUD tests pass in a separate process with it. This combined-classpath
failure remains unresolved; no tests were marked xfail or newly skipped to hide
it, and no Spark/Iceberg version pin was changed.

The 77 skips include unavailable live services, explicit fresh-install opt-ins,
isolation prerequisites and existing unconditional table-format skips. Skips do
not establish the corresponding service guarantees.

## Reproduction environment and commands

Linux x86_64, Python 3.12, PySpark 4.1.0, Java 17, Docker CLI 28.5.1,
Compose 2.39.4, Node and packages installed with the dashboard lockfile.
The available Java runtime differs from the Spark container's Java 21 runtime.
There is no Docker daemon or capability to start containers in this environment.

The local Iceberg JAR used was the repository-pinned
`iceberg-spark-runtime-4.0_2.13-1.10.0.jar`. It was downloaded into temporary
storage; no JAR, generated private configuration or test output was committed.

```bash
# Complete Python attempt; LIFECYCLE_ICEBERG_JAR is a local path to that pinned JAR.
SPARK_LOCAL_IP=127.0.0.1 SPARK_LOCAL_HOSTNAME=localhost \
PYSPARK_SUBMIT_ARGS="--jars $LIFECYCLE_ICEBERG_JAR --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions pyspark-shell" \
python -m pytest tests -q -p no:cacheprovider --timeout=45

# Independent file-format check (no extra Spark JAR).
SPARK_LOCAL_IP=127.0.0.1 SPARK_LOCAL_HOSTNAME=localhost \
python -m pytest tests/integration/sdp/test_sdp_file_formats.py -q --timeout=30

# Independent local Iceberg check.
SPARK_LOCAL_IP=127.0.0.1 SPARK_LOCAL_HOSTNAME=localhost \
PYSPARK_SUBMIT_ARGS="--jars $LIFECYCLE_ICEBERG_JAR pyspark-shell" \
python -m pytest tests/integration/test_iceberg_crud.py -q --timeout=30

npm --prefix dashboard ci --no-audit --no-fund
npm --prefix dashboard test
dashboard/node_modules/.bin/tsc --noEmit --incremental false -p dashboard/tsconfig.json
npm --prefix dashboard run build

python -m ruff check scripts/ tests/ demos/
python -m black --check scripts/ tests/ demos/
bash -n lakehouse
shellcheck -S warning lakehouse config/airflow/setup_connections.sh
```

## Outstanding gates

The unmodified full pre-commit run fails because `.secrets.baseline` is absent,
the repository-wide Bandit scan has existing findings, and the Hadolint Docker
hook cannot access a daemon. Only the reviewed helpers received narrow Bandit
annotations; the broad findings were not globally suppressed. The remaining
hooks passed with those three hook IDs explicitly excluded.

Real PostgreSQL/S3/Airflow/Jupyter/MLflow/Sharing authentication, the full lifecycle
E2E, clean installation, macOS/OrbStack, the pinned Java 21 container runtime and
deployment parity still require appropriate runners. Existing data, volumes and
configured service secrets were not modified by this validation. Upstream CI
approval remains outside this integration's permissions.
