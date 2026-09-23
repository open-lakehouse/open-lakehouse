# Compatibility matrix

The versions open-lakehouse is **proven** to run, and the versions proven **not**
to. This is generated evidence, not a wish list: every "supported" row is backed
by a test that runs on the real stack (Tier 3 / Tier 4 in
[testing.md](testing.md)), and every "known-bad" row is held by a negative test
that fails if that version ever starts working (so the reason a pin exists
outlives the person who found it).

Per the version-change protocol, this file is updated **from the matrix run**
(`.github/workflows/version-matrix.yml`), not by hand — a pin bump that does not
refresh the relevant row does not merge.

## Supported (pinned, under test)

| Component | Version | Runtime | Proven by |
|-----------|---------|---------|-----------|
| Spark | 4.1.0 (Scala 2.13, Java 21) | `apache/spark:4.1.0-scala2.13-java21-python3-r-ubuntu` | full T3 stack (`e2e.yml`) |
| Delta | 4.3.1 | Spark 4.1 / Java 21 | `test_i02_delta_write_read_timetravel` (T4 `pass` leg) |
| Iceberg | 1.10.0 | Spark 4.1 | SDP table-format T3 suite |
| Unity Catalog OSS | 0.5.0 (`unitycatalog:v0.5.0`) | — | `test_i44_i08_catalog_schema_delta_roundtrip` |
| UC Spark connector | `unitycatalog-spark_2.13` 0.4.1 + `unitycatalog-client` 0.5.1 + `unitycatalog-hadoop` 0.5.1 | Spark 4.1 / Delta 4.3.1 | catalog-managed Delta T3 |
| MLflow | 3.14 (`mlflow:v3.14.0-full`) | — | `test_mlflow` T3 |
| Kafka | cp-kafka 7.5.0 (≈ Apache 3.5) | — | `test_kafka_streaming` T2/T3 |
| AWS SDK v2 | 2.24.6 | Hadoop 3.4.1 | S3 conformance T3 |
| PostgreSQL | 16 | — | storage/lifecycle T3 |

## Known-bad (held by negative tests)

| Component | Version | Failure | Held by |
|-----------|---------|---------|---------|
| Delta | 4.3.0 | NPE through the UC Spark connector (`AbstractDeltaCatalogClient` reads a null catalog-options map) | `version-matrix.yml` (`fail` leg) |
| Delta | 4.2.0 | cannot do catalog-managed Delta via the UC 0.5.x connector | `version-matrix.yml` (`fail` leg) |
| Delta | 4.0.x | `NoSuchMethodError` on `org.apache.spark.internal.LogKey` (ABI mismatch on Spark 4.1) | I-02 rationale (add a matrix leg to enforce) |
| UC connector | 0.3.0 | pre-catalog-managed; no managed-Delta write path | `verify-versions.sh` forbidden set (T0) |

> A `fail` leg that starts passing is itself a build failure: it means the
> rationale above is stale and must be reconciled here before the pin moves.
