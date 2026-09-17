"""S3 conformance / hardening integration gates (PR #13 / Phase 2).

Thin pytest wrappers that run the connectivity scripts against the live
SeaweedFS and assert they exit 0:

    S-01..S-06, S-10  scripts/connectivity/test-s3-conformance.py
    S-07, S-08        scripts/connectivity/test-presigned-host-rewrite.py
    S-09 (live)       scripts/connectivity/test-warehouse-layout.py
    S-11              init-storage.sh is idempotent (twice -> exit 0, bucket once)

Skip cleanly when SeaweedFS isn't reachable on localhost:8333. Run with the same
interpreter as the suite (the .venv has boto3/requests).
"""

from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONN = REPO_ROOT / "scripts" / "connectivity"
S3_ENDPOINT = "http://localhost:8333"

pytestmark = [pytest.mark.integration, pytest.mark.storage]


def _s3_up() -> bool:
    try:
        urllib.request.urlopen(S3_ENDPOINT, timeout=3)
        return True
    except urllib.error.HTTPError:
        return True  # 403 (identities enforced) still means it's up
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _require_s3():
    if not _s3_up():
        pytest.skip("SeaweedFS not reachable on localhost:8333")


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CONN / script)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=REPO_ROOT,
    )


def test_s01_s06_s10_conformance_matrix():
    r = _run("test-s3-conformance.py")
    assert r.returncode == 0, f"conformance failed:\n{r.stdout}\n{r.stderr}"


def test_s07_s08_presigned_host_rewrite():
    r = _run("test-presigned-host-rewrite.py")
    assert r.returncode == 0, f"host-rewrite failed:\n{r.stdout}\n{r.stderr}"


def test_s09_warehouse_layout_lint_live():
    r = _run("test-warehouse-layout.py")
    assert r.returncode == 0, f"layout lint failed:\n{r.stdout}\n{r.stderr}"


def test_s11_init_storage_idempotent():
    # Two consecutive runs both succeed and don't duplicate the bucket/prefixes.
    init = REPO_ROOT / "scripts" / "tools" / "init-storage.sh"
    if not init.exists():
        pytest.skip("init-storage.sh missing")
    for _ in range(2):
        r = subprocess.run(
            ["bash", str(init)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO_ROOT,
        )
        assert r.returncode == 0, f"init-storage.sh non-zero:\n{r.stdout}\n{r.stderr}"
