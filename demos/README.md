# Demos

Connect-first demos for the open-lakehouse stack. Each demo lives in its own subdirectory and follows the contract in [`_template/README.md`](_template/README.md). An AI agent that knows the contract can run any demo by reading the demo's README - no per-demo scripting needed.

## Transport: Spark Connect (default)

Demos use `SparkSession.builder.remote("sc://localhost:15002")` against the Connect server in `docker-compose-spark41.yml`. The CLI default mode is `--spark-connect`; clients can read `LAKEHOUSE_SPARK_REMOTE` exported by `./lakehouse` to discover the endpoint.

Spark Declarative Pipelines (SDP) doesn't open `sc://` explicitly but requires Connect machinery in the Spark session - `pyspark.pipelines` uses `SparkConnectGraphElementRegistry` internally. The demo therefore depends on the same Connect server.

## Demo contract

Every `demos/<name>/README.md` has these five sections, in order:

1. **Purpose** - one sentence describing what this demo shows.
2. **Prereqs** - which services must be running, plus the transport (Connect / spark-pipelines / local).
3. **Run** - exact commands in order, each annotated with the expected stdout snippet.
4. **Expected output** - what success looks like (tables created, metrics logged, DAG run id).
5. **Teardown** - exact commands to remove all demo artifacts, or `bash teardown.sh`.

## Demos in this build

| Demo | Status | Transport | What it shows |
|------|--------|-----------|---------------|
| [`sdp-medallion/`](sdp-medallion/) | **Built** | `spark-pipelines` | Bronze -> Silver -> Gold via Spark Declarative Pipelines, materialized as Delta tables in Unity Catalog OSS. |
| [`unity-catalog-multi-engine/`](unity-catalog-multi-engine/) | Placeholder | Spark Connect + DuckDB | One catalog, multiple engines reading the same table. |
| [`realtime-mode/`](realtime-mode/) | **Built** | `spark-submit` (Structured Streaming) | Kafka -> Kafka stateless guardrail in Real-Time Mode (`trigger(realTime=...)`), dynamic topic routing to `-allowed` / `-quarantine`. |
| [`local-mode-spark/`](local-mode-spark/) | **Not yet implemented** | Local (no cluster) | In-process SparkSession for offline / laptop-only demos. Backs the `--spark-local` flag. |

`sdp-medallion` and `realtime-mode` are working demos with full READMEs.
`unity-catalog-multi-engine` and `local-mode-spark` are placeholders -
content is added demo-by-demo, never fabricated. To scaffold:

```bash
cp -r demos/_template demos/<name>
# then edit demos/<name>/README.md
```

## How an LLM uses this

1. User says "run the realtime-mode demo."
2. Agent reads `.claude/skills/lakehouse-lifecycle/demo.md` to recall the contract.
3. Agent reads `demos/realtime-mode/README.md`.
4. Agent checks "Prereqs" against `./lakehouse status --json` (verifying `spark.connect_grpc_listening: true`).
5. Agent runs commands from "Run" in order, comparing stdout to "Expected output".
6. After success or error, agent runs "Teardown".

No demo-specific skill files. The lifecycle skill + the demo's README are enough.
