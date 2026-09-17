"""Dashboard integration tests (Phase 3) — live, against a running container.

Proves the code-execution feature flag is enforced at the API layer, not merely
hidden in the UI: every gated route is hit DIRECTLY over HTTP (no browser, no
nav), and when the flag is off they must return 403. Also covers read-only
reachability (I-16..I-19) and that the container exposes only loopback:3000
(nothing extra "comes up").

Live; skips cleanly when the dashboard isn't running:
    ./lakehouse start dashboard        # default posture: code-execution OFF

Runs out of CI (integration marker). Enable the flag-ON half by starting with
DASHBOARD_ALLOW_CODE_EXECUTION=true.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_URL = os.environ.get("LAKEHOUSE_DASHBOARD_URL", "http://localhost:3000")

pytestmark = [pytest.mark.integration, pytest.mark.dashboard]

# Every route that must be dead when code-execution is off. (method, path).
GATED_ROUTES = [
    ("POST", "/api/jupyter-exec"),
    ("POST", "/api/pipelines/run"),
    ("POST", "/api/pipelines"),
    ("DELETE", "/api/pipelines/history"),
    ("GET", "/api/pipelines"),
    ("GET", "/api/pipelines/history"),
    ("GET", "/api/jupyter/contents/work"),
]


def _request(method: str, path: str, body: dict | None = None) -> int:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{DASHBOARD_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError):
        return -1


def _get_json(path: str):
    try:
        with urllib.request.urlopen(f"{DASHBOARD_URL}{path}", timeout=6) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, None
    except (urllib.error.URLError, TimeoutError):
        return -1, None


def _dashboard_up() -> bool:
    return _request("GET", "/") == 200


def _code_execution_enabled() -> bool:
    _, data = _get_json("/api/features")
    return bool(data and data.get("codeExecution"))


@pytest.fixture(autouse=True)
def _require_dashboard():
    if not _dashboard_up():
        pytest.skip("dashboard not running on :3000 (./lakehouse start dashboard)")


# --- Read-only reachability (I-16..I-19) ----------------------------------------


class TestReadOnlyReachable:
    def test_homepage_serves(self):
        assert _request("GET", "/") == 200

    def test_features_endpoint_responds(self):
        status, data = _get_json("/api/features")
        assert status == 200
        assert "codeExecution" in data

    def test_storage_health(self):
        status, data = _get_json("/api/health/storage")
        assert data and data.get("status") == "healthy", f"storage health: {data}"

    def test_mlflow_health(self):
        status, data = _get_json("/api/health/mlflow")
        assert data and data.get("status") == "healthy", f"mlflow health: {data}"

    def test_catalog_reads_real_uc(self):
        status, data = _get_json("/api/uc/catalogs")
        assert status == 200, f"uc/catalogs status {status}"
        assert (
            isinstance(data.get("catalogs"), list) and data["catalogs"]
        ), "expected at least one Unity Catalog catalog"

    def test_all_health_endpoints_wellformed(self):
        """Every service surfaced on the home page has a health probe that returns
        a well-formed status (healthy when up, unhealthy/unknown when down) — so
        the dashboard reflects the whole stack, not just the 4 data services."""
        allowed = {"healthy", "unhealthy", "unknown", "unconfigured"}
        for svc in [
            "storage",
            "mlflow",
            "spark",
            "airflow",
            "ai-gateway",
            "delta-sharing",
        ]:
            _, data = _get_json(f"/api/health/{svc}")
            assert data and data.get("status") in allowed, f"/api/health/{svc}: {data}"


# --- The core ask: API-layer enforcement, not front-end hiding ------------------


@pytest.mark.security
class TestCodeExecutionGate:
    def test_gate_tracks_the_flag(self):
        """Every gated route's reachability must follow /api/features exactly —
        hit directly over HTTP, with no browser or nav involved."""
        enabled = _code_execution_enabled()
        for method, path in GATED_ROUTES:
            code = _request(
                method, path, body={} if method in ("POST", "DELETE") else None
            )
            if enabled:
                assert code != 403, f"{method} {path} was 403 with the flag ON"
            else:
                assert (
                    code == 403
                ), f"{method} {path} returned {code}, expected 403 with the flag OFF"

    def test_disabled_by_default_returns_403(self):
        """The security-critical default: with the flag off, the whole
        code-execution surface is dead over the wire (403), not just UI-hidden."""
        if _code_execution_enabled():
            pytest.skip(
                "dashboard started with code-execution ENABLED; run with the default to assert the off posture"
            )
        for method, path in GATED_ROUTES:
            code = _request(
                method, path, body={} if method in ("POST", "DELETE") else None
            )
            assert code == 403, f"{method} {path} returned {code}, expected 403"


# --- Exposure: nothing extra comes up -------------------------------------------


@pytest.mark.security
class TestExposure:
    def test_only_loopback_3000_published(self):
        """The container must publish ONLY 127.0.0.1:3000 — no other port comes
        up, and it is not reachable off-host."""
        try:
            out = subprocess.run(
                ["docker", "port", "dashboard"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("docker not available")
        if out.returncode != 0:
            pytest.skip("dashboard container not found for `docker port`")
        mappings = [ln for ln in out.stdout.splitlines() if ln.strip()]
        assert mappings, "expected a published port mapping"
        for ln in mappings:
            # e.g. "3000/tcp -> 127.0.0.1:3000"
            assert ln.startswith("3000/tcp"), f"unexpected published port: {ln}"
            assert "127.0.0.1:" in ln, f"port not bound to loopback: {ln}"
