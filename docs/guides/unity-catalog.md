# Unity Catalog OSS

Unity Catalog OSS is **the** Iceberg/Delta catalog for this stack. There is no PostgreSQL JDBC catalog path. If a tutorial or config mentions one, treat it as stale.

For AI-assistant deep reference (REST API, credential vending, multi-engine examples), see [`.claude/skills/unity-catalog-oss/SKILL.md`](../../.claude/skills/unity-catalog-oss/SKILL.md).

## Why Unity Catalog OSS

| Capability | What you get |
|------------|--------------|
| Iceberg REST API | Standard endpoint any Iceberg client speaks |
| Multi-engine reads | DuckDB, Trino, Dremio, PyIceberg without per-engine config |
| Multi-format | Iceberg + Delta + Hudi (via UniForm) in one catalog |
| Credential vending | UC mints short-lived S3 creds; clients don't ship hardcoded keys |
| Open governance | UC's permission model (Spark and downstream both honor it) |

## Architecture

```
        Spark · DuckDB · Trino · PyIceberg
                       │
                       ▼ REST API (Iceberg + Delta endpoints)
        ┌────────────────────────────────────┐
        │   Unity Catalog OSS  :8081         │
        │   ├─ /api/2.1/unity-catalog/...    │
        │   └─ /api/2.1/unity-catalog/iceberg/v1/...
        └────────────────────────────────────┘
                       │
       ┌───────────────┴────────────────┐
       ▼                                ▼
PostgreSQL :5432              SeaweedFS :8333
(metastore — UC's tables)     (table data — Iceberg/Delta files)
```

## Start

```bash
./lakehouse start unity-catalog
./lakehouse status --json | jq '.services.unity_catalog'   # → true
```

First start: ~30 seconds (image pull + DB schema init).

## Config

`config/unity-catalog/server.properties` controls UC's behavior. Common settings:

```properties
server.port=8081

s3.bucketPath.0=s3://warehouse
s3.region.0=us-east-1
s3.accessKey.0=your_seaweedfs_access_key
s3.secretKey.0=your_seaweedfs_secret_key
s3.endpoint.0=http://localhost:8333

# Metastore (PostgreSQL)
db.url=jdbc:postgresql://localhost:5432/unitycatalog
db.user=postgres
db.password=...
```

Copy from the example:

```bash
cp config/unity-catalog/server.properties.example config/unity-catalog/server.properties
# edit with your SeaweedFS credentials
```

`spark-defaults.conf` is already wired to UC out of the box (see `config/spark/spark-defaults.conf.example`):

```properties
spark.sql.catalog.iceberg                 org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.catalog-impl    org.apache.iceberg.rest.RESTCatalog
spark.sql.catalog.iceberg.uri             http://localhost:8081/api/2.1/unity-catalog/iceberg
spark.sql.catalog.iceberg.warehouse       unity
spark.sql.catalog.iceberg.token           not_used
```

## CLI commands

```bash
./lakehouse start unity-catalog
./lakehouse stop unity-catalog
./lakehouse logs unity-catalog
./lakehouse status                       # includes UC
```

## REST API quickstart

```bash
# List catalogs
curl -s http://localhost:8081/api/2.1/unity-catalog/catalogs | jq .

# Create a schema
curl -X POST http://localhost:8081/api/2.1/unity-catalog/schemas \
  -H "Content-Type: application/json" \
  -d '{"name":"bronze","catalog_name":"iceberg"}'

# List tables in a schema
curl -s "http://localhost:8081/api/2.1/unity-catalog/tables?catalog_name=iceberg&schema_name=bronze" | jq .

# Iceberg REST endpoint (Spark uses this)
curl -s http://localhost:8081/api/2.1/unity-catalog/iceberg/v1/config | jq .
```

## Multi-engine: DuckDB example

```sql
-- DuckDB ≥ 0.10
INSTALL iceberg;
LOAD iceberg;

ATTACH 'http://localhost:8081/api/2.1/unity-catalog/iceberg'
  AS uc (TYPE iceberg);

SELECT * FROM uc.bronze.orders LIMIT 10;
```

The same `iceberg.bronze.orders` table is visible to Spark (via the JVM client) and DuckDB (via the REST client). One catalog, two engines, no data movement.

## Limitations of UC OSS 0.4.x

- Auth providers (OAuth, SAML) are partial. Local demos run without auth.
- The Delta-native API surface is read-mostly. Full Delta DML still goes through Spark.
- Lineage events are minimal compared to managed Databricks UC.
- Cross-deployment federation isn't supported.

## Troubleshooting

### UC won't start

```bash
docker logs unity-catalog --tail 100
```

Most common: PostgreSQL not reachable. UC OSS uses Postgres as its metastore — if Postgres on `:5432` is down, UC crash-loops.

### Spark can't see tables created via REST

Check the catalog name matches. Spark is configured for catalog `iceberg`; if you POSTed a table to `catalog_name=unity`, Spark won't find it.

### S3 access denied on table reads

Verify `s3.accessKey.0` / `s3.secretKey.0` in `server.properties` match the SeaweedFS credentials your Spark job uses (or in `.env`). Mismatch → UC vends keys that can't read SeaweedFS.

## Resources

- [Unity Catalog OSS docs](https://docs.unitycatalog.io/)
- [Unity Catalog OSS on GitHub](https://github.com/unitycatalog/unitycatalog) (Apache-2.0)
- [`.claude/skills/unity-catalog-oss/SKILL.md`](../../.claude/skills/unity-catalog-oss/SKILL.md) — deeper reference for AI agents
