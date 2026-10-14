"""Opt-in clean MLflow build with real host-header validation."""

import os
import platform as platform_info
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(scope="session", autouse=True)
def composed_storage():
    """Override the shared-stack fixture; this test provisions its own database."""
    return False


@pytest.mark.skipif(
    os.environ.get("LAKEHOUSE_TEST_FRESH_INSTALL") != "1",
    reason="set LAKEHOUSE_TEST_FRESH_INSTALL=1 to build and boot isolated containers",
)
def test_mlflow_localhost_headers(tmp_path):
    native = "arm64" if platform_info.machine() in ("arm64", "aarch64") else "amd64"
    platform = os.environ.get("LAKEHOUSE_TEST_PLATFORM", "linux/" + native)
    name = "mlflow-install-" + uuid.uuid4().hex[:10]
    postgres = name + "-postgres"
    image = name + ":test"

    def run(*args, check=True, timeout=120):
        return subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, check=check, timeout=timeout
        )

    log = tmp_path / "build.log"
    with log.open("w") as out:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--platform",
                platform,
                "--pull",
                "--no-cache",
                "-f",
                "docker/mlflow/Dockerfile",
                "-t",
                image,
                ".",
            ],
            cwd=ROOT,
            stdout=out,
            stderr=subprocess.STDOUT,
            timeout=1800,
        )
    assert result.returncode == 0, f"build failed: {log}\n{log.read_text()[-5000:]}"
    password = secrets.token_urlsafe(24)
    artifact_root = "/tmp/artifacts"
    try:
        run("docker", "network", "create", name)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            postgres,
            "--network",
            name,
            "--tmpfs",
            "/var/lib/postgresql/data",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "postgres:16-alpine",
        )
        run(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            name,
            "--platform",
            platform,
            "-e",
            f"POSTGRES_HOST={postgres}",
            "-e",
            "POSTGRES_USER=postgres",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "-e",
            f"MLFLOW_PG_PASS={password}",
            "-e",
            f"MLFLOW_ARTIFACTS_DESTINATION={artifact_root}",
            image,
        )
        probe = """
import json, urllib.request, urllib.error
for host, expected in [('localhost:5000', 200), ('127.0.0.1:5000', 200), ('localhost', 200), ('mlflow-server:5000', 200), ('untrusted.example:5000', 403)]:
    request = urllib.request.Request('http://127.0.0.1:5000/api/2.0/mlflow/experiments/search', data=b'{"max_results":10}', headers={'Host': host, 'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(request, timeout=10)
        status = response.status
        assert isinstance(json.load(response)['experiments'], list)
    except urllib.error.HTTPError as error:
        status = error.code
    assert status == expected, (host, status, expected)
print('localhost and internal API clients accepted; untrusted Host rejected')
"""
        deadline = time.monotonic() + 300
        while True:
            result = run("docker", "exec", name, "python", "-c", probe, check=False)
            if result.returncode == 0:
                break
            assert time.monotonic() < deadline, result.stderr[-3000:]
            time.sleep(5)
        print(platform, result.stdout.strip())
    finally:
        for container in (name, postgres):
            run("docker", "rm", "-f", container, check=False)
        run("docker", "network", "rm", name, check=False)
        run("docker", "image", "rm", image, check=False)
