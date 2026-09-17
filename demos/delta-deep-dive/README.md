# Delta Lake deep dive

> ACID DML, time travel, schema evolution, and OPTIMIZE on a path-based Delta table, over Spark Connect.

## Purpose

Shows Delta Lake's core table features against object storage: partitioned writes, ACID
`UPDATE` / `DELETE` / `MERGE`, time travel by version, schema evolution with `mergeSchema`, and
`OPTIMIZE` file compaction. All operations run through Spark Connect using SQL, so there is no
DeltaTable client dependency. The table is path-based (`delta.\`s3a://...\``) — this demo is about
Delta mechanics, not catalog governance (see `unity-catalog/` for that).

## Prereqs

- Spark 4.1 + Connect server + storage: `./lakehouse start storage && ./lakehouse start all`
- This demo needs **only** Spark + storage (SeaweedFS). It does not use UC, Kafka, or MLflow.
- Python client deps: `poetry install` (provides `pyspark[connect]`).

Transport: `SparkSession.builder.remote("sc://localhost:15002")` (or `LAKEHOUSE_SPARK_REMOTE`).

Verify all green:

```bash
./lakehouse status --json | jq '.all_healthy and .spark.connect_grpc_listening'
# expect: true
```

> Memory note: the demo caps `spark.sql.shuffle.partitions=8` to keep its footprint small on
> a local host. If your Docker/Colima VM is tight on RAM (≤8 GB) and the Connect container
> gets OOM-killed mid-run, either give the VM more memory (e.g. `colima start --memory 16`) or
> stop what this demo doesn't need: `docker stop mlflow-server kafka zookeeper`.

## Run

```bash
poetry run python demos/delta-deep-dive/deep_dive.py
```

Expected stdout snippets, in order:

```
[1] Created 5,000 transactions, partitioned by region
|North America| 1295|
```

```
[2] UPDATE: applied 10% discount to orders > $1,000
[2] DELETE: removed 1,187 cancelled orders (3,813 remaining)
[2] MERGE: upserted 2 orders (1 update + 1 insert); final count 3,814
```

```
[3] version 0 (original): 5,000 rows | latest: 3,814 rows | delta: 1,186
```

```
[4] Schema evolved; columns now: [... 'loyalty_tier']
```

```
[5] format=delta numFiles=4 sizeInBytes=...
delta-deep-dive complete.
```

## Expected output

- A partitioned Delta table at `s3a://lakehouse/warehouse/delta-deep-dive/transactions`.
- The `[3]` history snapshot (printed after the MERGE) shows 4 versions: `WRITE` (0), `UPDATE` (1),
  `DELETE` (2), `MERGE` (3). Steps 4–5 then add two more commits — a schema-evolution `WRITE` and an
  `OPTIMIZE` — so the final table has 6 versions.
- Row counts are deterministic (`random.seed(42)`): 5,000 written → 3,814 after DELETE + MERGE.
- Final table has the evolved schema including `loyalty_tier`.

## Teardown

```bash
bash demos/delta-deep-dive/teardown.sh
```
