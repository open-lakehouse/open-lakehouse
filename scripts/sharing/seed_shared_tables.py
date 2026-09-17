#!/usr/bin/env python3
"""Seed the two self-contained Delta tables that the Delta Sharing demo shares.

Writes deterministic, path-based (non-UC) Delta tables to fixed S3 prefixes:

    s3a://lakehouse/warehouse/sharing/sales_by_region/
    s3a://lakehouse/warehouse/sharing/daily_revenue/

These are exactly the locations declared in docker/delta-sharing/server.yaml, so
`./lakehouse share start` can serve them. Path-based Delta (not catalog-managed)
is used deliberately: Delta Sharing reads a table by its physical `_delta_log`, so
the share needs a stable, predictable location — not an opaque UC-managed path.
This makes the Sharing PR verifiable in isolation: no other demo need have run.

Transport is Spark Connect (the Connect server carries the S3A + Delta config);
the prefix is cleared first with boto3 so re-runs are clean even over a lingering
SeaweedFS filer directory (see the seaweedfs-ops skill).

Run:  poetry run python scripts/sharing/seed_shared_tables.py
Prereqs: storage (SeaweedFS) + Spark Connect up.
"""

from __future__ import annotations

import os
import sys

import boto3
from botocore.client import Config

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "lakehouse_s3")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "lakehouse_s3_secret")
BUCKET = os.environ.get("S3_BUCKET", "lakehouse")
SPARK_REMOTE = os.environ.get("LAKEHOUSE_SPARK_REMOTE", "sc://localhost:15002")

# (table name, s3 key prefix under the bucket) — must match server.yaml locations.
TABLES = {
    "sales_by_region": "warehouse/sharing/sales_by_region",
    "daily_revenue": "warehouse/sharing/daily_revenue",
}


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def clear_prefix(client, prefix: str) -> None:
    """Delete every object under a bucket prefix (idempotent, paginated)."""
    paginator = client.get_paginator("list_objects_v2")
    to_delete: list[dict[str, str]] = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix.rstrip("/") + "/"):
        for obj in page.get("Contents", []):
            to_delete.append({"Key": obj["Key"]})
            if len(to_delete) == 1000:
                _delete_batch(client, to_delete)
                to_delete = []
    if to_delete:
        _delete_batch(client, to_delete)


def _delete_batch(client, objs: list[dict[str, str]]) -> None:
    resp = client.delete_objects(Bucket=BUCKET, Delete={"Objects": objs, "Quiet": True})
    for err in resp.get("Errors", []):
        print(f"  WARN delete failed: {err}", file=sys.stderr)


def main() -> int:
    from pyspark.sql import SparkSession

    s3 = _s3()
    for prefix in TABLES.values():
        clear_prefix(s3, prefix)

    spark = SparkSession.builder.remote(SPARK_REMOTE).getOrCreate()
    spark.conf.set("spark.sql.shuffle.partitions", "8")

    sales = spark.createDataFrame(
        [
            ("Amsterdam", 152340.75, 4120),
            ("Rotterdam", 98120.40, 2755),
            ("Utrecht", 61890.10, 1840),
            ("Den Haag", 74210.55, 2010),
            ("Eindhoven", 45230.00, 1290),
        ],
        "region string, revenue double, orders int",
    )
    daily = spark.createDataFrame(
        [
            ("2026-08-15", 41230.10),
            ("2026-08-16", 38950.75),
            ("2026-08-17", 52310.40),
            ("2026-08-18", 47820.00),
            ("2026-08-19", 50110.25),
            ("2026-08-20", 44900.90),
            ("2026-08-21", 61540.60),
        ],
        "day string, revenue double",
    )

    for name, prefix in TABLES.items():
        df = sales if name == "sales_by_region" else daily
        location = f"s3a://{BUCKET}/{prefix}/"
        (
            df.write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            # checkpointInterval=1 so the very next commit writes a checkpoint.
            .option("delta.checkpointInterval", "1")
            .save(location)
        )
        # Force a second commit so a checkpoint (_last_checkpoint) is written. The
        # Delta Sharing server's delta-format reader (Delta Kernel — used when a
        # client such as Databricks sends `delta-sharing-capabilities:
        # responseformat=delta`) treats a missing _last_checkpoint as fatal, and a
        # fresh single-commit table has none. The parquet-format path tolerates it,
        # but real consumers request delta. Re-writing the same rows is a no-op to
        # the data but produces v1, which checkpoints.
        df.write.format("delta").mode("overwrite").save(location)
        count = spark.read.format("delta").load(location).count()
        print(f"  seeded {name}: {count} rows -> {location}")

    spark.stop()
    print("sharing seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
