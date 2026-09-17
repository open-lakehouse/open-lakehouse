# SPDX-License-Identifier: Apache-2.0
"""Delta Sharing (Phase 4) — config, repoint, and re-sign logic tests.

Unit-level (no running server): static checks on the imported proxy, assertions
that the CP setup was repointed to SeaweedFS, the re-sign logic of
url-rewriter-proxy.py exercised directly (loaded via importlib since the filename
is hyphenated), and structural checks on the `share` CLI wiring.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SHARING = REPO / "docker" / "delta-sharing"
PROXY = SHARING / "url-rewriter-proxy.py"
SERVER_YAML = SHARING / "server.yaml"
CLI = REPO / "lakehouse"
COMPOSE = REPO / "docker-compose-sharing.yml"

pytestmark = pytest.mark.merge


def _load_proxy():
    """Load the hyphenated proxy module by path (offline; no server needed)."""
    spec = importlib.util.spec_from_file_location("url_rewriter_proxy", PROXY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Deterministic signing inputs for the tests.
    mod.S3_PUBLIC_ENDPOINT = "localhost:8333"
    mod.S3_PUBLIC_SCHEME = "http"
    mod.AWS_ACCESS_KEY = "test_key"
    mod.AWS_SECRET_KEY = "test_secret"
    mod.AWS_REGION = "us-east-1"
    return mod


class TestProxyStatic:
    """Ported from the CP test_url_rewriter.py static checks."""

    def test_proxy_is_valid_python(self):
        ast.parse(PROXY.read_text())

    def test_proxy_uses_session_and_retry(self):
        content = PROXY.read_text()
        assert "requests.Session()" in content
        assert "Retry" in content and "HTTPAdapter" in content


class TestRepointedToSeaweedFS:
    def test_no_minio_anywhere(self):
        for f in SHARING.iterdir():
            if f.is_file():
                assert (
                    "minio" not in f.read_text().lower()
                ), f"stray MinIO ref in {f.name}"

    def test_server_yaml_points_at_seaweedfs_and_seed_prefixes(self):
        text = SERVER_YAML.read_text()
        assert "http://seaweedfs:8333" in text
        assert "s3a://lakehouse/warehouse/sharing/sales_by_region/" in text
        assert "s3a://lakehouse/warehouse/sharing/daily_revenue/" in text

    def test_placeholders_renamed_to_s3(self):
        text = SERVER_YAML.read_text()
        assert "__S3_ACCESS_KEY__" in text and "__S3_SECRET_KEY__" in text
        assert "__MINIO_ACCESS_KEY__" not in text


class TestResignLogic:
    def test_parse_s3_url_path_and_virtual_hosted(self):
        mod = _load_proxy()
        # Path-style (what the buggy server emits): s3.amazonaws.com/bucket/key
        b, k = mod.parse_s3_url(
            "https://s3.amazonaws.com/lakehouse/warehouse/sharing/daily_revenue/"
            "part-0.parquet?X-Amz-Signature=abc"
        )
        assert b == "lakehouse"
        assert k == "warehouse/sharing/daily_revenue/part-0.parquet"
        # Virtual-hosted: bucket.s3.amazonaws.com/key
        b2, k2 = mod.parse_s3_url(
            "https://lakehouse.s3.amazonaws.com/warehouse/x?X-Amz-Signature=z"
        )
        assert b2 == "lakehouse"
        assert k2 == "warehouse/x"

    def test_generate_presigned_url_is_wellformed_sigv4(self):
        mod = _load_proxy()
        url = mod.generate_presigned_url("lakehouse", "warehouse/sharing/x/f.json", 900)
        # Path-style, points at the target endpoint, carries a fresh SigV4 signature.
        assert url.startswith(
            "http://localhost:8333/lakehouse/warehouse/sharing/x/f.json?"
        )
        assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
        assert "X-Amz-Expires=900" in url
        assert "X-Amz-Signature=" in url
        assert "s3.amazonaws.com" not in url

    def test_rewrite_response_body_replaces_amazonaws_host(self):
        mod = _load_proxy()
        body = json.dumps(
            {
                "file": {
                    "url": "https://s3.amazonaws.com/lakehouse/warehouse/sharing/"
                    "sales_by_region/part-0.parquet?X-Amz-Algorithm=AWS4-HMAC-SHA256"
                    "&X-Amz-Expires=3600&X-Amz-Signature=deadbeef"
                }
            }
        ).encode()
        out = mod.rewrite_response_body(body, "application/json").decode()
        # The upstream amazonaws host is gone; the URL now targets the local store,
        # preserving bucket + key.
        assert "s3.amazonaws.com" not in out
        assert (
            "localhost:8333/lakehouse/warehouse/sharing/sales_by_region/part-0.parquet"
            in out
        )
        assert "X-Amz-Signature=" in out


class TestShareCliWiring:
    def test_share_command_dispatched(self):
        text = CLI.read_text()
        assert "share)        cmd_share" in text
        assert "cmd_share()" in text

    def test_share_is_opt_in_not_in_start_all(self):
        text = CLI.read_text()
        # `sharing` must not be one of the services `start all` iterates.
        assert (
            "storage|spark|kafka|all|unity-catalog|uc|airflow|mlflow|notebooks|sharing"
            not in text
        )
        assert "delta_sharing" in text  # but it IS reported in status --json

    def test_compose_file_exists_and_targets_seaweedfs(self):
        assert COMPOSE.exists()
        assert (
            "seaweedfs:8333" in COMPOSE.read_text()
            or "S3_PUBLIC_ENDPOINT" in COMPOSE.read_text()
        )


class TestReviewFixesBc7189c:
    """Lock the /code-review fixes from commit bc7189c."""

    def test_parse_s3_url_decodes_key_no_double_encode(self):
        # urlparse path is percent-ENCODED; parse_s3_url must decode so
        # generate_presigned_url re-encodes exactly once (no %20 -> %2520).
        mod = _load_proxy()
        b, k = mod.parse_s3_url(
            "https://s3.amazonaws.com/lakehouse/dir%20name/f.parquet?X-Amz-Signature=x"
        )
        assert (b, k) == ("lakehouse", "dir name/f.parquet")
        url = mod.generate_presigned_url(b, k, 60)
        assert "dir%20name/f.parquet" in url
        assert "%2520" not in url

    def test_proxy_drops_and_strips_content_encoding(self):
        # Accept-Encoding dropped upstream; Content-Encoding stripped from the
        # re-emitted (decompressed) response body.
        src = PROXY.read_text().lower()
        assert "accept-encoding" in src
        assert "content-encoding" in src

    def test_share_seed_gates_on_storage_and_connect(self):
        text = CLI.read_text()
        seed = text.split("seed)", 1)[1].split("start)", 1)[0]
        assert "is_service_healthy 8333" in seed
        assert "get_spark_connect_port" in seed

    def test_share_profile_recovers_token_from_container(self):
        text = CLI.read_text()
        assert "share_container_token()" in text  # helper defined
        # the profile branch resolves the token from env, else the running container
        assert "${DELTA_SHARING_TOKEN:-$(share_container_token)}" in text
