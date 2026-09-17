#!/usr/bin/env python3
"""SeaweedFS S3 conformance matrix (PR #13 / Phase 2, T-2.1).

Asserts the §2.1 capabilities the lakehouse data path and Delta Sharing rely on,
against the live SeaweedFS S3 endpoint (path-style + SigV4):

    S-01  Presigned GET (path-style SigV4) -> 200 + exact payload
    S-02  Range GET (bytes=990-999) -> correct 10-byte slice
    S-03  ListObjectsV2 + delimiter -> CommonPrefixes includes `t/_delta_log/`
    S-04  Conditional PUT `If-None-Match: *` -> enforced (PreconditionFailed).
          KNOWN-LIMITATION on the pinned SeaweedFS 3.80 (not enforced); reported,
          not failed — 4.x enforces it but rejects UC's vended token (§2.5).
    S-05  Multipart upload >=5 MiB -> completes, readable at full length
    S-06  Multi-object delete -> all deleted, Errors empty (informs T-2.6)
    S-10  Anonymous (unsigned) GET -> 403

Config from env: S3_ENDPOINT (default http://localhost:8333), S3_ACCESS_KEY,
S3_SECRET_KEY, S3_BUCKET (default lakehouse). Creates + cleans a throwaway
`_conformance/<uuid>/` prefix. Exit 0 = all pass.

Usage: python scripts/connectivity/test-s3-conformance.py
"""

from __future__ import annotations

import os
import sys
import uuid

import boto3
import requests
from botocore.client import Config
from botocore.exceptions import ClientError

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
ACCESS = os.environ.get("S3_ACCESS_KEY", "lakehouse_s3")
SECRET = os.environ.get("S3_SECRET_KEY", "lakehouse_s3_secret")
BUCKET = os.environ.get("S3_BUCKET", "lakehouse")
PREFIX = f"_conformance/{uuid.uuid4().hex[:12]}"

_GREEN, _RED, _YELLOW, _NC = "\033[0;32m", "\033[0;31m", "\033[1;33m", "\033[0m"


class KnownLimitation(Exception):
    """A capability that the PINNED SeaweedFS deliberately does not support —
    reported (not counted as a failure) so the matrix stays honest."""


def _client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS,
        aws_secret_access_key=SECRET,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def s01_presigned_get(s3) -> None:
    key = f"{PREFIX}/s01.bin"
    payload = b"open-lakehouse-conformance-payload"
    s3.put_object(Bucket=BUCKET, Key=key, Body=payload)
    url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=300
    )
    r = requests.get(url, timeout=10)
    assert r.status_code == 200, f"presigned GET status {r.status_code}"
    assert r.content == payload, "presigned GET payload mismatch"


def s02_range_get(s3) -> None:
    key = f"{PREFIX}/s02.bin"
    body = bytes(i % 256 for i in range(1000))
    s3.put_object(Bucket=BUCKET, Key=key, Body=body)
    r = s3.get_object(Bucket=BUCKET, Key=key, Range="bytes=990-999")
    chunk = r["Body"].read()
    assert chunk == body[990:1000], f"range slice wrong: {chunk!r}"


def s03_list_delimiter(s3) -> None:
    s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}/t/_delta_log/00000.json", Body=b"{}")
    s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}/t/part-0.parquet", Body=b"x")
    r = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{PREFIX}/t/", Delimiter="/")
    prefixes = {p["Prefix"] for p in r.get("CommonPrefixes", [])}
    assert f"{PREFIX}/t/_delta_log/" in prefixes, f"CommonPrefixes missing: {prefixes}"
    keys = {o["Key"] for o in r.get("Contents", [])}
    assert f"{PREFIX}/t/part-0.parquet" in keys, f"keys missing part file: {keys}"


def s04_conditional_put(s3) -> None:
    key = f"{PREFIX}/s04.bin"
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"first", IfNoneMatch="*")
    try:
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"second", IfNoneMatch="*")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        assert code in ("PreconditionFailed", "412"), f"unexpected code {code}"
        return
    # Not enforced. SeaweedFS 3.80 (pinned) doesn't implement conditional PUT;
    # 4.x does, but 4.x rejects UC OSS credential vending's mandatory placeholder
    # session token (§2.5) — so we pin 3.80 and accept this. It only affects
    # CONCURRENT multi-writer Delta commits (not the single-writer local stack).
    raise KnownLimitation(
        "conditional PUT If-None-Match:* not enforced on SeaweedFS 3.80 "
        "(4.x enforces it but breaks UC credential vending — see seaweedfs-ops)"
    )


def s05_multipart(s3) -> None:
    key = f"{PREFIX}/s05.bin"
    part = b"z" * (5 * 1024 * 1024 + 1024)  # >5 MiB single part + a small tail part
    tail = b"y" * 1024
    up = s3.create_multipart_upload(Bucket=BUCKET, Key=key)
    uid = up["UploadId"]
    try:
        p1 = s3.upload_part(
            Bucket=BUCKET, Key=key, PartNumber=1, UploadId=uid, Body=part
        )
        p2 = s3.upload_part(
            Bucket=BUCKET, Key=key, PartNumber=2, UploadId=uid, Body=tail
        )
        s3.complete_multipart_upload(
            Bucket=BUCKET,
            Key=key,
            UploadId=uid,
            MultipartUpload={
                "Parts": [
                    {"PartNumber": 1, "ETag": p1["ETag"]},
                    {"PartNumber": 2, "ETag": p2["ETag"]},
                ]
            },
        )
    except Exception:
        s3.abort_multipart_upload(Bucket=BUCKET, Key=key, UploadId=uid)
        raise
    got = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    assert len(got) == len(part) + len(tail), f"multipart length {len(got)}"


def s06_multi_delete(s3) -> None:
    keys = [f"{PREFIX}/s06/{i}.bin" for i in range(5)]
    for k in keys:
        s3.put_object(Bucket=BUCKET, Key=k, Body=b"d")
    resp = s3.delete_objects(
        Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in keys]}
    )
    errors = resp.get("Errors", [])
    assert not errors, f"multi-delete reported errors: {errors}"
    left = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{PREFIX}/s06/").get("KeyCount", 0)
    assert left == 0, f"{left} objects survived multi-delete"


def s10_anonymous_denied(s3) -> None:
    key = f"{PREFIX}/s10.bin"
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"secret")
    # Unsigned path-style GET must be refused (s3conf.json identities enforced).
    r = requests.get(f"{ENDPOINT}/{BUCKET}/{key}", timeout=10)
    assert r.status_code in (401, 403), f"anonymous GET not denied: {r.status_code}"


CHECKS = [
    ("S-01 presigned GET (path-style SigV4)", s01_presigned_get),
    ("S-02 range GET", s02_range_get),
    ("S-03 ListObjectsV2 + delimiter", s03_list_delimiter),
    ("S-04 conditional PUT If-None-Match:*", s04_conditional_put),
    ("S-05 multipart upload >=5 MiB", s05_multipart),
    ("S-06 multi-object delete", s06_multi_delete),
    ("S-10 anonymous access denied", s10_anonymous_denied),
]


def main() -> int:
    s3 = _client()
    failures = 0
    known = 0
    print(f"SeaweedFS S3 conformance @ {ENDPOINT} (bucket {BUCKET})")
    for name, fn in CHECKS:
        try:
            fn(s3)
            print(f"  {_GREEN}PASS{_NC} {name}")
        except KnownLimitation as e:
            known += 1
            print(f"  {_YELLOW}KNOWN-LIMITATION{_NC} {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  {_RED}FAIL{_NC} {name}: {type(e).__name__}: {e}")
    # Cleanup the throwaway prefix.
    try:
        objs = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{PREFIX}/").get(
            "Contents", []
        )
        if objs:
            s3.delete_objects(
                Bucket=BUCKET, Delete={"Objects": [{"Key": o["Key"]} for o in objs]}
            )
    except Exception:
        pass
    passed = len(CHECKS) - failures - known
    tail = f" ({known} known-limitation)" if known else ""
    print(f"conformance: {passed}/{len(CHECKS)} passed{tail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
