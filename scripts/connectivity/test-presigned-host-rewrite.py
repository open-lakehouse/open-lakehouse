#!/usr/bin/env python3
"""SeaweedFS presigned host-rewrite modes (PR #13 / Phase 2, T-2.2).

The Delta Sharing proxy signs presigned SigV4 URLs for a PUBLIC tunnel hostname
while the request actually lands on the LOCAL store. SigV4 covers `host`, so the
backend's host-verification behavior decides whether the delivered request
verifies. SeaweedFS accepts two delivery modes where MinIO accepts only one
(§2.2) — this locks that in:

    S-07  Mode B: URL signed for a public host, delivered to localhost with
          `X-Forwarded-Host` + `X-Forwarded-Proto` -> 200
    S-08  Mode C: same, delivered with a `Host:` header override -> 200

(Mode A — naive host swap, no forwarding headers — is expected to 403; we assert
that too, as the control.)

Config from env: S3_ENDPOINT (default http://localhost:8333), S3_ACCESS_KEY,
S3_SECRET_KEY, S3_BUCKET. Exit 0 = all pass.

Usage: python scripts/connectivity/test-presigned-host-rewrite.py
"""

from __future__ import annotations

import os
import sys
import uuid
from urllib.parse import urlparse, urlunparse

import boto3
import requests
from botocore.client import Config

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
ACCESS = os.environ.get("S3_ACCESS_KEY", "lakehouse_s3")
SECRET = os.environ.get("S3_SECRET_KEY", "lakehouse_s3_secret")
BUCKET = os.environ.get("S3_BUCKET", "lakehouse")
PUBLIC_HOST = os.environ.get("PRESIGN_PUBLIC_HOST", "my-sharing-host.example.com")
KEY = f"_conformance/host-rewrite/{uuid.uuid4().hex[:12]}.bin"
PAYLOAD = b"presigned-host-rewrite-payload"

_GREEN, _RED, _NC = "\033[0;32m", "\033[0;31m", "\033[0m"


def _client(endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=ACCESS,
        aws_secret_access_key=SECRET,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def _local_url_from(signed_url: str) -> str:
    """Keep path + SigV4 query, but point the request at the LOCAL endpoint."""
    local = urlparse(ENDPOINT)
    s = urlparse(signed_url)
    return urlunparse((local.scheme, local.netloc, s.path, "", s.query, ""))


def main() -> int:
    # 1. Put the object with a normal (local, correctly-signed) client.
    _client(ENDPOINT).put_object(Bucket=BUCKET, Key=KEY, Body=PAYLOAD)

    # 2. Presign a GET as if the store lived at the PUBLIC host (https, no port —
    #    so the signed Host header is the bare hostname, like a public reverse
    #    proxy / tunnel fronting the local store).
    public = _client(f"https://{PUBLIC_HOST}")
    signed = public.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": KEY}, ExpiresIn=300
    )
    local_url = _local_url_from(signed)

    failures = 0

    # Control — Mode A: naive host swap, no forwarding headers -> must 403.
    ra = requests.get(local_url, timeout=10)
    if ra.status_code == 403:
        print(f"  {_GREEN}PASS{_NC} Mode A control (naive swap) -> 403 as expected")
    else:
        failures += 1
        print(f"  {_RED}FAIL{_NC} Mode A control expected 403, got {ra.status_code}")

    # S-07 — Mode B: X-Forwarded-Host / -Proto -> 200.
    rb = requests.get(
        local_url,
        headers={"X-Forwarded-Host": PUBLIC_HOST, "X-Forwarded-Proto": "https"},
        timeout=10,
    )
    if rb.status_code == 200 and rb.content == PAYLOAD:
        print(f"  {_GREEN}PASS{_NC} S-07 Mode B (X-Forwarded-Host/-Proto) -> 200")
    else:
        failures += 1
        print(f"  {_RED}FAIL{_NC} S-07 Mode B expected 200, got {rb.status_code}")

    # S-08 — Mode C: Host header override -> 200.
    rc = requests.get(local_url, headers={"Host": PUBLIC_HOST}, timeout=10)
    if rc.status_code == 200 and rc.content == PAYLOAD:
        print(f"  {_GREEN}PASS{_NC} S-08 Mode C (Host override) -> 200")
    else:
        failures += 1
        print(f"  {_RED}FAIL{_NC} S-08 Mode C expected 200, got {rc.status_code}")

    # Cleanup.
    try:
        _client(ENDPOINT).delete_object(Bucket=BUCKET, Key=KEY)
    except Exception:
        pass

    print(f"host-rewrite: {3 - failures}/3 passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
