"""Opt-in generated credentials against isolated, fresh PostgreSQL and S3 storage."""

import json
import os
import platform
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(scope="session", autouse=True)
def composed_storage():
    """Use isolated storage without starting the shared installation."""
    return False


@pytest.mark.skipif(
    os.environ.get("LAKEHOUSE_TEST_FRESH_INSTALL") != "1",
    reason="set LAKEHOUSE_TEST_FRESH_INSTALL=1 to boot isolated storage",
)
def test_generated_credentials_authenticate_fresh_storage(tmp_path):
    name = "setup-check-" + uuid.uuid4().hex[:10]
    native = "arm64" if platform.machine() in ("arm64", "aarch64") else "amd64"
    target = os.environ.get("LAKEHOUSE_TEST_PLATFORM", "linux/" + native)
    for rel in (
        ".env.example",
        "config/spark/spark-defaults.conf.example",
        "config/unity-catalog/server.properties.example",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, path)

    def run(*args, check=True, timeout=180, env=None):
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=env
        )
        # Never include subprocess arguments or output in credential-test failures.
        if check:
            assert result.returncode == 0, "isolated setup command failed"
        return result

    environment = {**os.environ, "COMPOSE_PROJECT_NAME": name}
    # This test must not borrow any real credentials from the calling shell.
    for key in (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "AIRFLOW_ADMIN_USER",
        "AIRFLOW_ADMIN_PASSWORD",
        "AIRFLOW_FERNET_KEY",
        "JUPYTER_TOKEN",
        "MLFLOW_PG_PASS",
        "DELTA_SHARING_TOKEN",
        "LAKEHOUSE_SHARING_PROFILE",
        "DASHBOARD_ALLOW_JUPYTER_LAUNCH",
    ):
        environment.pop(key, None)
    run(
        "python3",
        str(ROOT / "scripts/tools/configure-local-credentials.py"),
        "--root",
        str(tmp_path),
        env=environment,
    )
    private = tmp_path / ".env"
    config = json.loads(
        run(
            "docker",
            "compose",
            "--env-file",
            str(private),
            "-f",
            str(ROOT / "docker-compose-storage.yml"),
            "config",
            "--format",
            "json",
            env=environment,
        ).stdout
    )
    for key, service in config["services"].items():
        service.pop("container_name", None)
        service.pop("restart", None)
        service.pop("volumes", None)
        service["tmpfs"] = [
            "/var/lib/postgresql/data" if key == "postgres" else "/data"
        ]
        service["platform"] = target
        port = 5432 if key == "postgres" else 8333
        service["ports"] = [{"target": port, "published": "0", "host_ip": "127.0.0.1"}]
    config.pop("volumes", None)
    compose_file = tmp_path / "storage.json"
    compose_file.write_text(json.dumps(config))
    compose_file.chmod(0o600)
    compose = ["docker", "compose", "-p", name, "-f", str(compose_file)]
    before = private.read_bytes()
    try:
        run(*compose, "up", "-d", "--wait", "--wait-timeout", "120")
        pg = config["services"]["postgres"]["environment"]
        result = run(
            *compose,
            "exec",
            "-T",
            "-e",
            "PGPASSWORD=" + pg["POSTGRES_PASSWORD"],
            "postgres",
            "psql",
            "-h",
            "postgres",
            "-U",
            pg["POSTGRES_USER"],
            "-d",
            "postgres",
            "-tAc",
            "SELECT 1",
        )
        assert result.stdout.strip() == "1"
        rejected = run(
            *compose,
            "exec",
            "-T",
            "-e",
            "PGPASSWORD=incorrect-test-value",
            "postgres",
            "psql",
            "-h",
            "postgres",
            "-U",
            pg["POSTGRES_USER"],
            "-d",
            "postgres",
            "-tAc",
            "SELECT 1",
            check=False,
        )
        assert rejected.returncode != 0, "database accepted an incorrect password"
        port = run(*compose, "port", "seaweedfs", "8333").stdout.strip()
        s3_env = config["services"]["seaweedfs"]["environment"]
        client = boto3.client(
            "s3",
            endpoint_url="http://" + port,
            region_name="us-east-1",
            aws_access_key_id=s3_env["S3_ACCESS_KEY"],
            aws_secret_access_key=s3_env["S3_SECRET_KEY"],
        )
        deadline = time.monotonic() + 60
        while True:
            try:
                client.list_buckets()
                break
            except Exception:
                assert (
                    time.monotonic() < deadline
                ), "S3 did not accept generated credentials"
                time.sleep(2)
        invalid = boto3.client(
            "s3",
            endpoint_url="http://" + port,
            region_name="us-east-1",
            aws_access_key_id=s3_env["S3_ACCESS_KEY"],
            aws_secret_access_key="incorrect-test-value",  # pragma: allowlist secret - intentionally invalid
        )
        with pytest.raises(ClientError):
            invalid.list_buckets()
        run(
            "python3",
            str(ROOT / "scripts/tools/configure-local-credentials.py"),
            "--root",
            str(tmp_path),
            env=environment,
        )
        assert private.read_bytes() == before, "rerun changed generated credentials"
        print(
            target,
            "generated PostgreSQL and S3 credentials accepted; invalid credentials rejected; rerun stable",
        )
    finally:
        # Only this UUID-scoped project's containers/network; no named data volumes.
        run(*compose, "down", check=False)
