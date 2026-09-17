# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for the open-lakehouse analytical demos (Spark Connect).

Imported by the demo scripts, which put THIS directory (demos/_lib) on sys.path and
`import delta_helpers` directly — deliberately not demos/, which would shadow the
`mlflow` PyPI package with the demos/mlflow app directory. Kept minimal on purpose —
the demo narrative still lives in each demo's own script.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

import boto3
from botocore.config import Config


def _s3_client():
    """boto3 S3 client for the local SeaweedFS endpoint (path-style, demo creds)."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:8333"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "lakehouse_s3"),
        aws_secret_access_key=os.environ.get(
            "AWS_SECRET_ACCESS_KEY", "lakehouse_s3_secret"
        ),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"}),
    )


def clear_prefix(location: str) -> None:
    """Delete every S3-visible object under a table's `s3://`/`s3a://` location.

    Best effort: SeaweedFS may retain a filer directory entry that S3 DeleteObject
    cannot remove, but a subsequent Delta `overwrite` write lays down a fresh
    `_delta_log` over it (see recreate_delta_table). Per-object delete errors are
    surfaced on stderr rather than silently ignored.
    """
    parsed = urlparse(location)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/").rstrip("/") + "/"
    s3 = _s3_client()
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        objs = [{"Key": o["Key"]} for o in resp.get("Contents", [])]
        if objs:
            del_resp = s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})
            errors = del_resp.get("Errors", [])
            if errors:
                sample = ", ".join(
                    f"{e.get('Key')}: {e.get('Code')}" for e in errors[:3]
                )
                print(
                    f"warning: clear_prefix left {len(errors)} object(s) under "
                    f"s3://{bucket}/{prefix} ({sample})",
                    file=sys.stderr,
                )
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")


def recreate_delta_table(spark, table: str, location: str, df) -> None:
    """Deterministically (re)create an EXTERNAL Delta table in Unity Catalog.

    Drops the UC table, clears stale objects, then writes the data with Delta
    `overwrite` — which lays down a fresh `_delta_log` even over a lingering SeaweedFS
    directory from a prior run (a bare `CREATE TABLE … LOCATION` would otherwise fail
    with DELTA_CREATE_TABLE_WITH_NON_EMPTY_LOCATION) — and registers the result. So
    re-runs are clean with no teardown in between. `location` is an `s3://` URI (UC
    credential vending rejects `s3a://`); the bytes are written over the s3a filesystem.
    """
    spark.sql(f"DROP TABLE IF EXISTS {table}")
    clear_prefix(location)
    s3a = "s3a://" + location.split("://", 1)[1]
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
        s3a
    )
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} USING delta LOCATION '{location}'")
