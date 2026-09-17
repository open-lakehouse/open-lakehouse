#!/usr/bin/env python3
"""Warehouse-layout lint for SeaweedFS (PR #13 / Phase 2, T-2.4; S-09).

SeaweedFS's one real S3 incompatibility (§2.3): it cannot hold an object at key
`x` AND a prefix `x/` at the same time (documented "same path for a file and a
folder — No"; the collision surfaces as `InternalError`). Standard Delta/Iceberg
layouts never do this, but a stray write could. This lint lists the live
warehouse and fails if any object key is a strict prefix (at a `/` boundary) of
another key — catching a collision before it corrupts a table.

Config from env: S3_ENDPOINT (default http://localhost:8333), S3_ACCESS_KEY,
S3_SECRET_KEY, S3_BUCKET (default lakehouse), WAREHOUSE_PREFIX (default
warehouse/). Exit 0 = clean.

Usage: python scripts/connectivity/test-warehouse-layout.py
"""

from __future__ import annotations

import os
import sys

import boto3
from botocore.client import Config

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
ACCESS = os.environ.get("S3_ACCESS_KEY", "lakehouse_s3")
SECRET = os.environ.get("S3_SECRET_KEY", "lakehouse_s3_secret")
BUCKET = os.environ.get("S3_BUCKET", "lakehouse")
PREFIX = os.environ.get("WAREHOUSE_PREFIX", "warehouse/")

_GREEN, _RED, _NC = "\033[0;32m", "\033[0;31m", "\033[0m"


def _all_keys(s3) -> list[str]:
    keys: list[str] = []
    token = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": PREFIX}
        if token:
            kw["ContinuationToken"] = token
        r = s3.list_objects_v2(**kw)
        keys.extend(o["Key"] for o in r.get("Contents", []))
        if not r.get("IsTruncated"):
            break
        token = r.get("NextContinuationToken")
    return keys


def find_collisions(keys: list[str]) -> list[tuple[str, str]]:
    """Return (file_key, child_key) pairs where file_key is also a directory
    prefix — i.e. some other key starts with file_key + '/'."""
    key_set = set(keys)
    collisions = []
    for k in keys:
        if k.endswith("/"):
            continue  # explicit directory marker, not a file-vs-dir collision
        needle = k + "/"
        child = next((o for o in key_set if o.startswith(needle)), None)
        if child is not None:
            collisions.append((k, child))
    return collisions


def main() -> int:
    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS,
        aws_secret_access_key=SECRET,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )
    keys = _all_keys(s3)
    collisions = find_collisions(keys)
    print(f"warehouse-layout lint @ s3://{BUCKET}/{PREFIX} ({len(keys)} objects)")
    if collisions:
        for f, c in collisions:
            print(f"  {_RED}COLLISION{_NC} object '{f}' is also a prefix (e.g. '{c}')")
        print(f"  {_RED}FAIL{_NC} {len(collisions)} file-vs-directory collision(s)")
        return 1
    print(f"  {_GREEN}PASS{_NC} no file-vs-directory collisions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
