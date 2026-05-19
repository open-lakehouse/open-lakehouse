# local-mode-spark — **NOT YET IMPLEMENTED**

> Placeholder for the demo backing the `./lakehouse --spark-local` flag.

This demo is part of the roadmap, not part of this build. The CLI accepts `--spark-local` and exits with a "not yet implemented" message; this directory exists so that error message points somewhere real.

## What this demo will show (when built)

In-process Spark with no Docker cluster, no Spark Connect server, no Kafka. The point: minimum-viable Spark for laptops where Docker isn't running, where you want to iterate on transformation logic without spinning up the full stack.

Likely shape:

```python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("local-mode-spark")
    .master("local[*]")
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.iceberg.type", "hadoop")
    .config("spark.sql.catalog.iceberg.warehouse", "/tmp/iceberg-warehouse")
    .getOrCreate()
)
```

`hadoop` catalog (filesystem-only) replaces Unity Catalog REST since no UC server is running. The trade-off: no multi-engine catalog interop, no credential vending.

## Trade-offs vs Connect-first mode

| Capability | Connect (default) | Local (this demo) |
|------------|-------------------|-------------------|
| Spark cluster needed | Yes (Docker) | No |
| Unity Catalog OSS | Yes | No (filesystem catalog) |
| Kafka streaming | Yes | Not in scope |
| Iteration speed (simple transforms) | Network round-trip | Fastest (in-process) |
| Matches AWS production shape | Yes | No |

## Why it's deferred

Connect-first is the only supported transport in the current build because:

1. SDP requires Connect machinery in the session — local mode breaks the SDP demo path.
2. The catalog story is UC OSS only; local mode forces a fallback catalog (hadoop) that the rest of the stack doesn't use.
3. The platform is demo-first, and most demos benefit from Docker shape parity with AWS deployment.

When this lands, it'll come with a working Iceberg-local catalog example and clear "when to use" framing in `.claude/skills/spark-4-1/` and `docs/`.

## See also

- `.claude/skills/lakehouse-lifecycle/SKILL.md` — current Connect-first lifecycle
- `.claude/skills/spark-4-1/SKILL.md` — Spark 4.1 reference (Connect-first)
- CLI flag stub: `./lakehouse --spark-local <command>` → exits with not-implemented
