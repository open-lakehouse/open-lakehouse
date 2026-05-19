# <Demo name>

> Replace the headline above. One sentence, what this demo shows. No marketing.

## Purpose

What concept this demo illustrates and why someone would run it. 2-3 sentences max. Be specific: "shows Iceberg time travel against a streaming write workload" beats "demonstrates lakehouse capabilities."

## Prereqs

- Spark 4.1 + Connect server: `./lakehouse start all` (Connect is the default transport)
- _(list other services this demo requires — Kafka, UC, MLflow, Airflow — and any data prep steps)_
- _(any environment variables that must be set in `.env`)_

Transport: this demo uses `SparkSession.builder.remote("sc://localhost:15002")` (or reads `LAKEHOUSE_SPARK_REMOTE` from the env exported by the CLI). Override only if you have a reason.

Verify all green:

```bash
./lakehouse status --json | jq '.all_healthy and .spark.connect_grpc_listening'
# expect: true
```

## Run

Execute these commands in order. Each block lists the expected stdout snippet so an LLM (or human) can verify the step succeeded before moving on.

```bash
# Step 1: ...
<command>
```

Expected stdout snippet:

```
<paste a short excerpt of what success looks like>
```

```bash
# Step 2: ...
<command>
```

Expected stdout snippet:

```
<excerpt>
```

_(repeat for each step)_

## Expected output

What the final state should look like. Concrete:

- Tables created (with namespaces): `iceberg.bronze.orders`
- Row counts: `~1000 rows`
- Metrics logged to MLflow: experiment name, run id pattern
- Airflow DAG run state: `success` for `dag_id=...`

Whatever else makes "this demo worked" visible at a glance.

## Teardown

```bash
bash demos/<name>/teardown.sh
```

Or list the explicit commands if no script is needed:

```bash
# Drop tables
docker exec spark-master-41 /opt/spark/bin/spark-sql -e "DROP TABLE IF EXISTS iceberg.bronze.demo_orders;"

# Delete Kafka topic
docker exec kafka kafka-topics --delete --topic demo-orders --bootstrap-server localhost:9092

# Stop demo-specific service if started
./lakehouse stop mlflow
```
