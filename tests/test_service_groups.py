"""Exercise real CLI service dispatch without touching the running installation."""

import os
import re
import secrets
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "lakehouse").read_text()
CORE = ["storage", "spark41", "kafka"]
ALL = CORE + ["unity-catalog", "mlflow", "airflow", "notebooks", "sharing", "dashboard"]


def function(name):
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}", SOURCE, re.M | re.S)
    assert match, name
    return match.group()


@pytest.fixture
def run_cli(tmp_path):
    (tmp_path / ".env").touch()
    config = tmp_path / "config/unity-catalog"
    config.mkdir(parents=True)
    (config / "server.properties").touch()
    trace = tmp_path / "trace"
    stubs = r"""
set -e
record() { printf '%s\n' "$*" >> "$TRACE"; }
header() { :; }
get_spark_port() { echo 7078; }
get_spark_connect_port() { echo 15002; }
get_spark_ui_port() { echo 8082; }
get_spark_master_container() { echo spark-master-41; }
get_spark_remote() { echo sc://localhost:15002; }
resolve_container_name() { echo "$1${TEST_SUFFIX:-}"; }
ensure_local_credentials() { record credentials; }
check_ports_for_service() { record "ports|$1"; }
overlay_set_compose_args() {
    CURRENT_COMPOSE=$1
    OVERLAY_COMPOSE_ARGS=(-f "docker-compose-$1.yml")
    record "overlay|$1"
    [ "${FAIL_OVERLAY:-}" != "$1" ]
}
docker() {
    if [ "$1" = ps ]; then
        printf '%s\n' zookeeper kafka spark-master-41
        return 0
    fi
    local action=up arg
    for arg in "$@"; do
        [ "$arg" != down ] || action=down
    done
    record "$action|$CURRENT_COMPOSE|$*"
    [ "${FAIL_COMPOSE:-}" != "$CURRENT_COMPOSE" ]
}
wait_for_postgres_ready() { record postgres-ready; [ "${FAIL_POSTGRES:-}" != 1 ]; }
wait_for_service() { record "ready|$1|$2"; [ "${FAIL_READY:-}" != "$1" ]; }
wait_for_services() { record cluster-ready; [ "${FAIL_CLUSTER:-}" != 1 ]; }
bash() { record bootstrap; [ "${FAIL_BOOTSTRAP:-}" != 1 ]; }
is_service_healthy() { return 0; }
share_write_profile() { record profile; [ "${FAIL_PROFILE:-}" != 1 ]; }
share_endpoint() { echo https://localhost:8443/delta-sharing; }
sleep() { record pause; }
"""
    functions = "\n".join(
        function(name)
        for name in ("lifecycle_group_services", "cmd_start", "cmd_stop", "cmd_share")
    )

    def run(action="start", group="all", *, extra="", dispatch=False, **settings):
        trace.write_text("")
        env = {
            **os.environ,
            "PROJECT_ROOT": str(tmp_path),
            "TRACE": str(trace),
            "DELTA_SHARING_TOKEN": secrets.token_hex(24),
        }
        for key in (
            "FAIL_OVERLAY",
            "FAIL_COMPOSE",
            "FAIL_POSTGRES",
            "FAIL_READY",
            "FAIL_CLUSTER",
            "FAIL_BOOTSTRAP",
            "FAIL_PROFILE",
            "TEST_SUFFIX",
            "LAKEHOUSE_ENV_FILE",
        ):
            env.pop(key, None)
        env.update(settings)
        if dispatch:
            command = SOURCE[SOURCE.rindex("case ${1:-help} in") :]
            prefix = [action, group]
        else:
            command = "if cmd_" + action + ' "$1"; then exit 0; else exit $?; fi'
            prefix = [group]
        result = subprocess.run(
            [
                "bash",
                "-c",
                stubs + "\n" + functions + "\n" + extra + "\n" + command,
                "fixture",
                *prefix,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result, trace.read_text().splitlines()

    return run


def actions(trace, action):
    return [line.split("|")[1] for line in trace if line.startswith(action + "|")]


@pytest.mark.parametrize("group, expected", [("core", CORE), ("all", ALL)])
def test_start_groups_use_dependency_order(run_cli, group, expected):
    result, trace = run_cli(group=group)
    assert result.returncode == 0, result.stderr
    assert actions(trace, "up") == expected
    assert trace.count("bootstrap") == 1
    assert trace.index("bootstrap") < next(
        i for i, line in enumerate(trace) if line.startswith("up|spark41|")
    )
    if group == "all":
        assert "profile" in trace
        assert any(line.startswith("ready|Jupyter|") for line in trace)
        assert any(line.startswith("ready|Dashboard|") for line in trace)
    else:
        assert "profile" not in trace
        assert not any("dashboard" in line or "notebooks" in line for line in trace)


@pytest.mark.parametrize("group, expected", [("core", CORE), ("all", ALL)])
def test_stop_groups_reverse_dependencies_and_preserve_volumes(
    run_cli, group, expected
):
    result, trace = run_cli(action="stop", group=group)
    assert result.returncode == 0, result.stderr
    assert actions(trace, "down") == list(reversed(expected))
    assert not any(" -v" in line or "--volumes" in line for line in trace)
    assert "credentials" not in trace


@pytest.mark.parametrize("group, expected", [("core", CORE), ("all", ALL)])
def test_restart_uses_same_stop_and_start_groups(run_cli, group, expected):
    result, trace = run_cli(action="restart", group=group, dispatch=True)
    assert result.returncode == 0, result.stderr
    assert actions(trace, "down") == list(reversed(expected))
    assert actions(trace, "up") == expected
    assert trace.index("pause") > max(
        i for i, line in enumerate(trace) if line.startswith("down|")
    )
    assert trace.index("pause") < next(
        i for i, line in enumerate(trace) if line.startswith("up|")
    )


@pytest.mark.parametrize("service", ALL)
def test_compose_failure_aborts_full_start_even_with_errexit_suppressed(
    run_cli, service
):
    result, trace = run_cli(FAIL_COMPOSE=service)
    assert result.returncode != 0
    assert actions(trace, "up") == ALL[: ALL.index(service) + 1]
    assert "remaining services were not started" in result.stderr
    if ALL.index(service) <= ALL.index("sharing"):
        assert "profile" not in trace


@pytest.mark.parametrize(
    "stage",
    [
        "SeaweedFS S3",
        "Spark Connect",
        "Unity Catalog",
        "MLflow",
        "Airflow",
        "Jupyter",
        "Delta Sharing",
        "Dashboard",
    ],
)
def test_failed_readiness_does_not_report_group_success(run_cli, stage):
    result, trace = run_cli(FAIL_READY=stage)
    assert result.returncode != 0
    assert "remaining services were not started" in result.stderr
    if stage != "Dashboard":
        assert "dashboard" not in actions(trace, "up")
    if stage == "Delta Sharing":
        assert "profile" not in trace


@pytest.mark.parametrize(
    "setting", ["FAIL_POSTGRES", "FAIL_BOOTSTRAP", "FAIL_CLUSTER", "FAIL_PROFILE"]
)
def test_bootstrap_and_profile_failures_abort_group(run_cli, setting):
    result, trace = run_cli(**{setting: "1"})
    assert result.returncode != 0
    assert "dashboard" not in actions(trace, "up")


def test_stop_failure_keeps_dependencies_running(run_cli):
    result, trace = run_cli(action="stop", FAIL_COMPOSE="mlflow")
    assert result.returncode != 0
    assert actions(trace, "down") == list(reversed(ALL))[:5]
    assert "dependencies were left running" in result.stderr


def test_new_readiness_probes_resolve_container_names(run_cli):
    result, trace = run_cli(TEST_SUFFIX="-isolated-test")
    assert result.returncode == 0, result.stderr
    assert any("docker exec jupyter-isolated-test " in line for line in trace)
    assert any("docker exec dashboard-isolated-test " in line for line in trace)


def test_existing_cluster_readiness_failure_is_propagated(run_cli):
    result, _ = run_cli(
        group="spark", FAIL_READY="Kafka", extra=function("wait_for_services")
    )
    assert result.returncode != 0


def test_individual_sharing_start_retains_share_interface(run_cli):
    result, trace = run_cli(group="sharing")
    assert result.returncode == 0, result.stderr
    assert actions(trace, "up") == ["sharing"]
    assert "profile" in trace
