---
name: unity-catalog-oss
description: Unity Catalog OSS 0.4.x — the only catalog in this stack. Load when configuring the UC server, creating catalogs/schemas/tables via REST, or wiring a non-Spark engine (DuckDB, Trino) against UC. Covers the REST API surface, credential vending, and the no-JDBC-catalog rule.
---

# Unity Catalog OSS

This stack uses **Unity Catalog OSS only**. There is no PostgreSQL JDBC catalog path. If you see `spark.sql.catalog.iceberg.type=jdbc` or `spark.sql.catalog.iceberg.jdbc.user` anywhere, that's a leftover bug from the upstream lakehouse-stack reference — remove it, don't replicate it.

UC OSS runs as a Java server. The compose definition is `docker-compose-unity-catalog.yml`. Backing store is PostgreSQL. REST API is on `localhost:8081`.

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `http://localhost:8081/api/2.1/unity-catalog/catalogs` | List/create catalogs |
| `http://localhost:8081/api/2.1/unity-catalog/schemas` | List/create schemas |
| `http://localhost:8081/api/2.1/unity-catalog/tables` | List/create/describe tables |
| `http://localhost:8081/api/2.1/unity-catalog/iceberg/v1/config` | Iceberg REST catalog (Spark uses this) |
| `http://localhost:8081/api/2.1/unity-catalog/iceberg/v1/namespaces` | Iceberg REST namespace ops |

UC 0.4.x speaks the **Iceberg REST Catalog spec** at the `/iceberg/v1/*` path. Any Iceberg client (Spark, PyIceberg, DuckDB via `iceberg` extension) can point at this URL.

## Spark config

Already wired in `config/spark/spark-defaults.conf.example`:

```
spark.sql.catalog.iceberg               org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.iceberg.catalog-impl  org.apache.iceberg.rest.RESTCatalog
spark.sql.catalog.iceberg.uri           http://localhost:8081/api/2.1/unity-catalog/iceberg
spark.sql.catalog.iceberg.warehouse     unity
spark.sql.catalog.iceberg.token         not_used
```

In Spark, `iceberg.bronze.orders` resolves through UC. Behind the scenes Spark calls `GET /iceberg/v1/namespaces/bronze/tables/orders/`.

## Creating things via REST

```bash
# Create the iceberg catalog (one-time)
curl -X POST http://localhost:8081/api/2.1/unity-catalog/catalogs \
  -H "Content-Type: application/json" \
  -d '{"name":"iceberg","comment":"Default Iceberg catalog"}'

# Create a schema
curl -X POST http://localhost:8081/api/2.1/unity-catalog/schemas \
  -H "Content-Type: application/json" \
  -d '{"name":"bronze","catalog_name":"iceberg"}'

# List tables
curl "http://localhost:8081/api/2.1/unity-catalog/tables?catalog_name=iceberg&schema_name=bronze" | jq .
```

Auth: 0.4.x ships with no auth by default for local. Don't add a bearer token until you've wired UC's auth provider — most demos run unauth.

## Backing store

UC OSS stores its catalog metadata in PostgreSQL. Connection details are in `config/unity-catalog/server.properties`. The PostgreSQL instance is the same one used by Airflow / system Postgres on host port 5432. UC creates its tables under a `unitycatalog` schema.

Schema migrations for UC's tables are auto-applied at startup; you don't manage them.

## Credential vending

UC OSS can vend S3 credentials to clients so Spark doesn't need hardcoded `S3_ACCESS_KEY`/`S3_SECRET_KEY`. Configure in `server.properties`:

```
s3.region=us-east-1
s3.endpoint=http://seaweedfs:8333
s3.access-key=<your-seaweedfs-key>
s3.secret-key=<your-seaweedfs-secret>
s3.path-style-access=true
```

Clients then ask UC for temporary creds when reading a table — no creds in client config. For demo purposes the current spark-defaults.conf still ships static S3 keys; cleaning this up is a follow-on.

## Other engines

```python
# DuckDB
import duckdb
con = duckdb.connect()
con.sql("INSTALL iceberg; LOAD iceberg;")
con.sql("ATTACH 'http://localhost:8081/api/2.1/unity-catalog/iceberg' AS uc (TYPE iceberg);")
con.sql("SELECT * FROM uc.bronze.orders LIMIT 10;")
```

Trino, Dremio: same pattern — register UC's `/iceberg/v1/` URL as an Iceberg REST catalog.

## Limitations of UC OSS 0.4.x (don't promise users these)

- Auth providers (OAuth, SAML) are partial.
- The Delta-native API surface (`/delta/*`) is read-mostly. For full Delta DML, use Spark directly against the Delta table path.
- Lineage events (system tables) are minimal compared to managed Databricks UC.
- Cross-catalog references work; cross-deployment federation does not.

## When something's wrong

`./lakehouse logs unity-catalog | tail -100` shows the Java server's stdout. Most failures are:

1. PostgreSQL not reachable → UC crash-loops.
2. `server.properties` references a SeaweedFS endpoint that's not up yet → table operations fail with S3 errors, catalog ops still succeed.
3. Stale schema migrations after a UC OSS version bump → wipe the `unitycatalog` schema in Postgres and restart UC.
