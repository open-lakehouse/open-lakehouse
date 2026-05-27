# realtime-mode

> Spark 4.1 Structured Streaming **Real-Time Mode** — Kafka → guardrail → Kafka with sub-second routing.

## Purpose

Demonstrates Real-Time Mode (RTM) on OSS Spark 4.1.0: a single stateless query reads Ethereum-style block events from one Kafka topic, applies guardrail checks (gas limits, anomalous transaction counts, PII / credential leakage in `extra_data`), and routes each record to either an `-allowed` or `-quarantine` output topic via the `topic` column on the write — no `forEachBatch`, no double-writes.

RTM here means `Trigger.RealTime("5 seconds")` + `outputMode("update")`. The Scala `Trigger.RealTime(...)` API landed in 4.1.0 ([SPARK-52330 SPIP](https://issues.apache.org/jira/browse/SPARK-52330), [SPARK-53736](https://issues.apache.org/jira/browse/SPARK-53736)) as `@Experimental`. **There is no native PySpark `trigger(realTime=...)` kwarg in 4.1.0** — `rtm_pipeline.py` reaches through the JVM (`spark._jvm.org.apache.spark.sql.streaming.Trigger.RealTime(...)`) to construct the trigger, then drives `start()` through the Java `DataStreamWriter`. Set `USE_REALTIME=0` to fall back to `trigger(processingTime="0 seconds")` if you want pure-Python and don't need single-digit-ms latency.

## Prereqs

- Spark 4.1 + Kafka running: `./lakehouse start all`
- The 4 Spark-Kafka-connector jars in `jars/` (`./lakehouse setup` puts them
  there; `--packages` does **not** work on the stock `apache/spark:4.1.0`
  image, see "Notes" below).
- Demo deps on the host for the producer: `poetry install` (kafka-python ships
  in the dev/test extras).

Transport: this demo does **not** use the standalone Connect server. It
submits the streaming job into `spark-master-41` via `spark-submit` (long-
running streams + Connect don't compose cleanly). Verification reads the
output topics with `kafka-console-consumer` inside the Kafka container.

The stack runs Spark + Kafka on the **host network**, so the Kafka bootstrap
is `localhost:9092` from inside `spark-master-41` — *not* `kafka:9092`. The
producer and the streaming job both read `KAFKA_BOOTSTRAP_SERVERS`; pass it
explicitly per the Run section.

`spark-submit` (and any `spark-pipelines run`) must run as `-u root` — the
default `spark` user has `home=/nonexistent` and Ivy / checkpoint dirs trip
on it.

Verify the stack is up:

```bash
./lakehouse status --json | jq '.all_healthy and .kafka.healthy and .spark.healthy'
# expect: true
```

## Run

```bash
# Step 1: Sanity-check the validation logic locally (no Kafka needed).
poetry run python demos/realtime-mode/test_pipeline.py
```

Expected stdout snippet:

```
pattern tests
  ok None input
  ...
transform tests
  ok block=1000001 ALLOW []
  ok block=1000002 QUARANTINE ['HIGH_GAS_USAGE']
  ...
0 pattern failure(s), 0 transform failure(s)
```

```bash
# Step 2: Pre-create the input and output Kafka topics so RTM doesn't race
# topic auto-creation on first write.
for t in ethereum-blocks ethereum-validated-allowed ethereum-validated-quarantine; do
  docker exec kafka kafka-topics --create --if-not-exists \
    --topic "$t" --partitions 1 --replication-factor 1 \
    --bootstrap-server localhost:9092
done
```

Expected stdout snippet:

```
Created topic ethereum-blocks.
Created topic ethereum-validated-allowed.
Created topic ethereum-validated-quarantine.
```

```bash
# Step 3: Submit the RTM streaming job into the Spark master container.
# Copy the pipeline in, then spark-submit it with the pre-downloaded Kafka
# connector jars and the right Kafka bootstrap for this stack's host network.
docker cp demos/realtime-mode/rtm_pipeline.py spark-master-41:/tmp/rtm_pipeline.py

KJARS='/opt/spark/jars-extra/spark-sql-kafka-0-10_2.13-4.1.0.jar'
KJARS+=',/opt/spark/jars-extra/spark-token-provider-kafka-0-10_2.13-4.1.0.jar'
KJARS+=',/opt/spark/jars-extra/kafka-clients-3.9.0.jar'
KJARS+=',/opt/spark/jars-extra/commons-pool2-2.12.0.jar'

docker exec -u root -d -e KAFKA_BOOTSTRAP_SERVERS=localhost:9092 spark-master-41 \
  sh -c "/opt/spark/bin/spark-submit --jars '$KJARS' \
    --conf spark.sql.shuffle.partitions=8 \
    /tmp/rtm_pipeline.py >/tmp/rtm.log 2>&1"

# Tail the spark-submit log until you see the query started message.
docker exec spark-master-41 sh -c 'tail -f /tmp/rtm.log' 2>&1 | grep -m1 "streaming query started"
```

Expected stdout snippet:

```
streaming query started: id=... name=rtm-realtime-mode
```

```bash
# Step 4: Send 12 deterministic test blocks. One ALLOW, eleven QUARANTINE
# covering every guardrail (high gas, empty block, zero miner, high tx count,
# PII email/SSN/credit card, AWS key, JWT, and a multi-reason combo).
poetry run python demos/realtime-mode/produce_test_data.py --seeded
```

Expected stdout snippet:

```
sending 12 seeded blocks
  block_number=4000001 label=clean
  block_number=4000002 label=high_gas
  ...
```

```bash
# Step 5: Read the routed output. Allowed first, then quarantine.
docker exec kafka kafka-console-consumer \
  --topic ethereum-validated-allowed \
  --from-beginning --timeout-ms 10000 \
  --bootstrap-server localhost:9092 | head -5

docker exec kafka kafka-console-consumer \
  --topic ethereum-validated-quarantine \
  --from-beginning --timeout-ms 10000 \
  --bootstrap-server localhost:9092 | head -5
```

Expected stdout snippet (allowed):

```
{"block_number":4000001,...,"decision":"ALLOW","is_quarantined":false,"validation_reasons":[]}
{"block_number":4000005,...,"decision":"ALLOW","is_quarantined":false,"validation_reasons":[]}
```

Expected stdout snippet (quarantine):

```
{"block_number":4000002,...,"decision":"QUARANTINE","is_quarantined":true,"validation_reasons":["HIGH_GAS_USAGE"]}
{"block_number":4000004,...,"decision":"QUARANTINE","is_quarantined":true,"validation_reasons":["PII_EMAIL"]}
```

## Expected output

After the seeded run:

- Topic `ethereum-validated-allowed`: 2 records (block 4000001, 4000005) with `decision=ALLOW`, empty `validation_reasons`.
- Topic `ethereum-validated-quarantine`: 10 records with `decision=QUARANTINE` and the expected reason codes:
  - `HIGH_GAS_USAGE`, `EMPTY_BLOCK`, `PII_EMAIL`, `ZERO_MINER`, `HIGH_TX_COUNT`, `PII_SSN`, `PII_CREDIT_CARD`, `CREDENTIAL_AWS_KEY`, `[HIGH_GAS_USAGE, PII_EMAIL]`, `CREDENTIAL_JWT`.
- Spark master logs show one active streaming query named `rtm-realtime-mode`.
- Checkpoint dir on the master container: `/opt/spark-data/checkpoints/rtm-realtime-mode` exists and is non-empty.

For a continuous demo, swap `--seeded` for `--num-messages 0` on the producer — it will emit ~10 msg/sec with random validation outcomes.

## Teardown

```bash
bash demos/realtime-mode/teardown.sh
```

This stops the streaming query (by killing the spark-submit JVM inside `spark-master-41`), deletes the three Kafka topics, and removes the checkpoint directory.

## Notes — stack-specific gotchas

- **`--packages` is broken on the stock `apache/spark:4.1.0` image.** The
  default `spark` user has `home=/nonexistent`, and Ivy fails creating
  `/nonexistent/.ivy2.5.2/cache/resolved-…-1.0.xml` even with the dir
  pre-made and chmod-ed. `spark.jars.ivy` is ignored. Pre-downloading the
  Kafka jars (done by `./lakehouse setup` →
  `scripts/tools/download-jars.sh`) and using `--jars` sidesteps Ivy
  entirely. The Step 3 command above uses this approach.
- **Bootstrap is `localhost:9092`, not `kafka:9092`** — Spark and Kafka run
  on the host network, so service-name resolution doesn't work. Both the
  Spark job and the host-side producer read `KAFKA_BOOTSTRAP_SERVERS`.
- **Submit as `-u root`** — same `home=/nonexistent` reason. Without it,
  spark-submit can't write to the checkpoint dir or Ivy cache.
- **Loud-but-ignorable warnings on submit.** `ClassNotFoundException` for
  `IcebergSparkSessionExtensions`, `DeltaSparkSessionExtension`, and
  `S3AFileSystem` print at startup — Spark loads them eagerly because
  they're set in `spark-defaults.conf`, but this job doesn't need them.
  The streaming query starts fine afterward.
