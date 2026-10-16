"""Regression checks for Airflow's container installation and initialization."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class ComposeLoader(yaml.SafeLoader):
    pass


ComposeLoader.add_constructor(
    "!override", lambda loader, node: loader.construct_sequence(node)
)
ComposeLoader.add_constructor("!reset", lambda loader, node: None)


def compose(overlay=False):
    name = (
        "tests/overlays/docker-compose-airflow.test.yml"
        if overlay
        else "docker-compose-airflow.yml"
    )
    return yaml.load((ROOT / name).read_text(), Loader=ComposeLoader)


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


@pytest.mark.parametrize("overlay", [False, True])
@pytest.mark.parametrize(
    "users,create",
    [
        ([], True),
        ([{"username": "admin"}], False),
        ([{"username": "administrator", "roles": ["Admin"]}], True),
        ([{"username": "another", "email": "admin@localhost"}], True),
    ],
)
def test_init_matches_exact_username(tmp_path, overlay, users, create):
    executable(tmp_path / "psql", "#!/bin/sh\necho 1\n")
    executable(
        tmp_path / "airflow",
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['CALLS'], 'a') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:3] == ['users', 'list']:\n"
        "    if '--output' in sys.argv:\n"
        "        print(os.environ['USERS'])\n"
        "    else:\n"
        "        print('id | username | email | roles')\n"
        "        for user in json.loads(os.environ['USERS']):\n"
        "            print(user['username'], user.get('email', ''), user.get('roles', []))\n",
    )
    script = compose(overlay)["services"]["airflow-init"]["command"][-1]
    # Compose interpolation precedes shell execution in production.
    for key, value in {
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": tmp_path.name,
    }.items():
        script = script.replace("${" + key + "}", value)
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{Path(sys.executable).parent}:{os.environ['PATH']}",
            "CALLS": str(calls),
            "USERS": json.dumps(users),
            "AIRFLOW_ADMIN_USER": "admin",
            "LAKEHOUSE_RESOURCE_SUFFIX": "installation",
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    assert any(c[:2] == ["users", "create"] for c in commands) is create


@pytest.mark.parametrize("overlay", [False, True])
def test_init_stops_after_failed_migration(tmp_path, overlay):
    executable(tmp_path / "psql", "#!/bin/sh\necho 1\n")
    executable(
        tmp_path / "airflow",
        '#!/bin/sh\n[ "$1 $2" != "db migrate" ] || exit 19\n' 'touch "$CREATED"\n',
    )
    script = compose(overlay)["services"]["airflow-init"]["command"][-1]
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": tmp_path.name,
            "LAKEHOUSE_RESOURCE_SUFFIX": "installation",
            "CREATED": str(tmp_path / "created"),
        },
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 19
    assert not (tmp_path / "created").exists()


def test_connections_use_compose_addresses(tmp_path):
    executable(
        tmp_path / "airflow",
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['CALLS'], 'a') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n",
    )
    calls = tmp_path / "calls"
    subprocess.run(
        ["bash", str(ROOT / "config/airflow/setup_connections.sh")],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{Path(sys.executable).parent}:{os.environ['PATH']}",
            "CALLS": str(calls),
        },
        check=True,
        capture_output=True,
        timeout=10,
    )
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    connections = {c[2]: c[3:] for c in commands if c[:2] == ["connections", "add"]}
    for name, host, port in (
        ("spark_local", "spark://spark-master-41", "7078"),
        ("postgres_default", "postgres", "5432"),
        ("unity_catalog", "unity-catalog", "8080"),
        ("mlflow", "mlflow-server", "5000"),
    ):
        args = connections[name]
        assert args[args.index("--conn-host") + 1] == host
        assert args[args.index("--conn-port") + 1] == port
    kafka = connections["kafka_default"]
    assert (
        json.loads(kafka[kafka.index("--conn-extra") + 1])["bootstrap.servers"]
        == "kafka:9092"
    )
    assert ["variables", "set", "kafka_bootstrap_servers", "kafka:9092"] in commands
    assert [
        "variables",
        "set",
        "uc_endpoint",
        "http://unity-catalog:8080/api/2.1/unity-catalog/iceberg",
    ] in commands


def test_auth_manager_supports_configured_users():
    env = compose()["x-airflow-common"]["environment"]
    assert (
        env["AIRFLOW__CORE__AUTH_MANAGER"]
        == "airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager"
    )
    assert "AIRFLOW__API__AUTH_BACKENDS" not in env


def test_dag_processor_inherits_database_and_network():
    services = compose()["services"]
    processor = services["airflow-dag-processor"]
    assert processor["command"] == "dag-processor"
    assert "DagProcessorJob" in str(processor["healthcheck"]["test"])
    assert processor["environment"] == services["airflow-scheduler"]["environment"]
    assert processor["networks"] == services["airflow-scheduler"]["networks"]
    assert (
        processor["depends_on"]["airflow-init"]["condition"]
        == "service_completed_successfully"
    )
    isolated = compose(True)["services"]["airflow-dag-processor"]
    assert "${LAKEHOUSE_RESOURCE_SUFFIX}" in isolated["container_name"]


@pytest.mark.parametrize(
    "component", [None, "metadatabase", "scheduler", "triggerer", "dag_processor"]
)
def test_health_requires_every_component(component):
    health = {
        c: {"status": "healthy"}
        for c in ("metadatabase", "scheduler", "triggerer", "dag_processor")
    }
    if component:
        health[component]["status"] = "unhealthy"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/tools/check-airflow-health.py")],
        input=json.dumps(health),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == (1 if component else 0)


@pytest.mark.parametrize("payload", ["", "{}", "null", "<html>Not Found</html>"])
def test_health_rejects_missing_or_invalid_response(payload):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/tools/check-airflow-health.py")],
        input=payload,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 1


def test_build_has_no_amd64_only_java_path_or_legacy_sources_file():
    dockerfile = (ROOT / "docker/airflow/Dockerfile").read_text()
    assert "/etc/apt/sources.list " not in dockerfile
    assert "/usr/lib/jvm/java-17-openjdk-amd64" not in dockerfile
    assert "$(dpkg --print-architecture)" in dockerfile
    assert '"apache-airflow==${AIRFLOW_VERSION}"' in dockerfile
