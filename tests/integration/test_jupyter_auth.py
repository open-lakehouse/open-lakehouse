"""Jupyter token-auth enforcement (PR #13 / T-1.14, D5).

    I-12  Jupyter requires a token: an unauthenticated request to a protected
          endpoint is rejected (403); the correct token is accepted (200).
    U-18  Static: the image/compose enable token auth — no --ServerApp.token=,
          no --disable_check_xsrf, and JUPYTER_TOKEN is wired through compose.

Live half skips cleanly when Jupyter isn't running (docker compose
-f docker-compose-notebooks.yml up -d) or when JUPYTER_TOKEN is unset.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
JUPYTER_URL = os.environ.get("LAKEHOUSE_JUPYTER_URL", "http://localhost:8889")

pytestmark = [pytest.mark.integration]


def _get(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError):
        return -1


def _jupyter_up() -> bool:
    # /api is reachable without a token (returns version); use it as a liveness probe.
    return _get(f"{JUPYTER_URL}/api") == 200


# --- U-18 (static) --------------------------------------------------------------


class TestU18JupyterAuthStatic:
    def test_dockerfile_enables_token_auth(self):
        raw = (REPO_ROOT / "docker" / "jupyter" / "Dockerfile").read_text()
        # Inspect only the active (non-comment) directives — comments legitimately
        # describe the OLD tokenless posture to explain why it was removed.
        active = "\n".join(
            ln for ln in raw.splitlines() if not ln.lstrip().startswith("#")
        )
        assert "--ServerApp.token=" not in active, "empty ServerApp.token must be gone"
        assert (
            "disable_check_xsrf" not in active.lower()
        ), "XSRF protection must not be disabled in the active command"
        # And it must key off JUPYTER_TOKEN.
        assert "JUPYTER_TOKEN" in raw, "image must honor JUPYTER_TOKEN"

    def test_compose_wires_jupyter_token(self):
        compose = (REPO_ROOT / "docker-compose-notebooks.yml").read_text()
        assert "JUPYTER_TOKEN" in compose, "compose must pass JUPYTER_TOKEN through"

    def test_env_example_documents_token(self):
        env = (REPO_ROOT / ".env.example").read_text()
        assert "JUPYTER_TOKEN" in env, ".env.example must document JUPYTER_TOKEN"


# --- I-12 (live) ----------------------------------------------------------------


@pytest.mark.security
class TestI12JupyterTokenEnforced:
    @pytest.fixture(autouse=True)
    def _require_jupyter(self):
        if not _jupyter_up():
            pytest.skip("Jupyter not running on 8889")

    def test_no_token_is_rejected(self):
        # A protected endpoint without a token must be forbidden, not served.
        code = _get(f"{JUPYTER_URL}/api/contents")
        assert code == 403, f"expected 403 without a token, got {code}"

    def test_correct_token_is_accepted(self):
        token = os.environ.get("JUPYTER_TOKEN")
        if not token:
            # Fall back to the local .env value if present.
            env = REPO_ROOT / ".env"
            if env.exists():
                for line in env.read_text().splitlines():
                    if line.startswith("JUPYTER_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        break
        if not token:
            pytest.skip("JUPYTER_TOKEN not available to the test")
        code = _get(f"{JUPYTER_URL}/api/contents?token={token}")
        assert code == 200, f"expected 200 with the correct token, got {code}"
