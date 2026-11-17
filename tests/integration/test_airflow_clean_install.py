"""Opt-in clean Airflow install; no existing containers, volumes or env files."""

import base64
import json
import os
import platform as platform_info
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import yaml

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
def test_airflow_clean_install(tmp_path):
    native = "arm64" if platform_info.machine() in ("arm64", "aarch64") else "amd64"
    platform = os.environ.get("LAKEHOUSE_TEST_PLATFORM", "linux/" + native)
    project = "airflow-install-" + uuid.uuid4().hex[:10]
    image = project + ":test"
    env = {
        **os.environ,
        "POSTGRES_USER": "installation",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "AIRFLOW_ADMIN_USER": "admin",
        "AIRFLOW_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "AIRFLOW_FERNET_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "S3_ACCESS_KEY": "installation",
        "S3_SECRET_KEY": secrets.token_urlsafe(24),
    }

    def run(*args, timeout=120, check=True):
        return subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=check,
            timeout=timeout,
        )

    # No .env from a working installation is loaded; only the tracked Compose
    # definition and an empty PostgreSQL tmpfs are used.
    config = yaml.safe_load((ROOT / "docker-compose-airflow.yml").read_text())
    dags = tmp_path / "dags"
    dags.mkdir()
    (dags / "installation_check.py").write_text(
        "from airflow.sdk import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "with DAG('installation_check', schedule=None) as dag:\n"
        "    EmptyOperator(task_id='ready')\n"
    )
    for service in config["services"].values():
        service.pop("build", None)
        service.pop("container_name", None)
        service["image"] = image
        service["platform"] = platform
        service["env_file"] = []
        service["ports"] = []
        service["volumes"] = [
            f"{dags}:/opt/airflow/dags:ro",
            f"{ROOT / 'config/airflow'}:/opt/airflow/config:ro",
        ]
        # Copy the anchor's environment before extending it.
        service["environment"] = dict(service["environment"])
        for key in (
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "AIRFLOW_ADMIN_USER",
            "AIRFLOW_ADMIN_PASSWORD",
        ):
            service["environment"][key] = "${" + key + "}"
        service["environment"]["AIRFLOW__DAG_PROCESSOR__REFRESH_INTERVAL"] = "5"
    config["services"]["airflow-init"]["depends_on"] = {
        "postgres": {"condition": "service_healthy"}
    }
    config["services"]["postgres"] = {
        "image": "postgres:16-alpine",
        "environment": {
            k: "${" + k + "}" for k in ("POSTGRES_USER", "POSTGRES_PASSWORD")
        },
        "tmpfs": ["/var/lib/postgresql/data"],
        "networks": ["lakehouse-network"],
        "healthcheck": {
            "test": ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"],
            "interval": "2s",
            "timeout": "5s",
            "retries": 30,
        },
    }
    config.pop("x-airflow-common", None)
    path = tmp_path / "compose.yml"
    path.write_text(yaml.safe_dump(config))
    cmd = (
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "-p",
        project,
        "-f",
        str(path),
    )
    log = tmp_path / "build.log"
    # Build from the requested architecture, without reusing application layers.
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
                "docker/airflow/Dockerfile",
                "-t",
                image,
                ".",
            ],
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            timeout=2400,
        )
    assert result.returncode == 0, f"build failed: {log}\n{log.read_text()[-5000:]}"
    try:
        run(*cmd, "up", "-d", "--no-build", timeout=600)
        versions = run(
            *cmd,
            "exec",
            "-T",
            "airflow-scheduler",
            "bash",
            "-c",
            "java -version && spark-submit --version && airflow version",
        )
        assert "4.1.0" in versions.stdout + versions.stderr
        assert "3.1.6" in versions.stdout
        # This must be idempotent, with an exact username lookup.
        run(*cmd, "run", "--rm", "airflow-init", timeout=180)
        run(
            *cmd,
            "exec",
            "-T",
            "airflow-scheduler",
            "bash",
            "/opt/airflow/config/setup_connections.sh",
        )
        probe = """
import json, os, urllib.request
base = 'http://localhost:8085'
health = json.load(urllib.request.urlopen(base + '/api/v2/monitor/health', timeout=5))
assert all(health[c]['status'] == 'healthy' for c in ('metadatabase', 'scheduler', 'triggerer', 'dag_processor')), health
request = urllib.request.Request(base + '/auth/token', data=json.dumps({'username': os.environ['AIRFLOW_ADMIN_USER'], 'password': os.environ['AIRFLOW_ADMIN_PASSWORD']}).encode(), headers={'Content-Type': 'application/json'})
token = json.load(urllib.request.urlopen(request, timeout=10))['access_token']
request = urllib.request.Request(base + '/api/v2/dags/installation_check', headers={'Authorization': 'Bearer ' + token})
assert json.load(urllib.request.urlopen(request, timeout=10))['dag_id'] == 'installation_check'
print('All four Airflow components healthy; authenticated API and parsed DAG verified')
"""
        deadline = time.monotonic() + 600
        while True:
            probe_result = run(
                *cmd,
                "exec",
                "-T",
                "airflow-webserver",
                "python",
                "-c",
                probe,
                check=False,
            )
            if probe_result.returncode == 0:
                break
            assert time.monotonic() < deadline, probe_result.stderr[-3000:]
            time.sleep(5)
        run(
            *cmd,
            "exec",
            "-T",
            "airflow-scheduler",
            "airflow",
            "connections",
            "export",
            "/tmp/install-connections.json",
        )
        connections = json.loads(
            run(
                *cmd,
                "exec",
                "-T",
                "airflow-scheduler",
                "cat",
                "/tmp/install-connections.json",
            ).stdout
        )
        assert connections["postgres_default"]["host"] == "postgres"
        assert connections["unity_catalog"]["host"] == "unity-catalog"
        assert connections["unity_catalog"]["port"] == 8080
        assert connections["mlflow"]["host"] == "mlflow-server"
        print(platform, probe_result.stdout.strip())
    finally:
        # Only this randomly named project is removed; no volume deletion flags.
        run(*cmd, "down", "--remove-orphans", timeout=180, check=False)
        run("docker", "image", "rm", image, check=False)
