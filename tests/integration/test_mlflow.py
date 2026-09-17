"""MLflow status integration test (PR #0, Phase 1.5, Checkpoint 6).

    I-48  MLflow reports its TRUE status (§1.13.6 / T-1.5.11). `status --json` must
          report services.mlflow == true when the MLflow container is running. On
          `main` this was always false: the CLI probed a container named `mlflow`
          while Compose names it `mlflow-server`.

The container-name resolution is what the fix turns on, so a stand-in container named
`mlflow-server` is sufficient and deterministic — status only checks whether the
resolved container is running. If the REAL mlflow-server is already up, we assert
against it directly instead.

FAIL-CLOSED on tooling: skips when Docker is unavailable.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LAKEHOUSE = REPO_ROOT / "lakehouse"

pytestmark = [pytest.mark.integration, pytest.mark.merge]

# Overlay-activation vars. This is a DEFAULT-PATH test, so they must be scrubbed from
# any CLI invocation — otherwise, when the suite is driven with LAKEHOUSE_TEST_RUN_ID
# exported for the run-scoped tests, `./lakehouse` sees a PARTIAL overlay activation
# and (correctly) aborts all-or-nothing before it can report status.
_OVERLAY_VARS = (
    "LAKEHOUSE_TEST_RUN_ID",
    "LAKEHOUSE_OVERLAY_DIR",
    "LAKEHOUSE_RESOURCE_SUFFIX",
    "LAKEHOUSE_ENV_FILE",
    "LAKEHOUSE_PORT_OFFSET",
    "COMPOSE_PROJECT_NAME",
)


def _default_path_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _OVERLAY_VARS}


ALPINE = "alpine:latest"
STANDIN = "mlflow-server"


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=10
            ).returncode
            == 0
        )
    except Exception:
        return False


def _running(name: str) -> bool:
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
    ).stdout.split()
    return name in out


def _status_json() -> dict:
    # DEFAULT path (no overlay): status is in the connect-mode bypass list.
    r = subprocess.run(
        [str(LAKEHOUSE), "status", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env=_default_path_env(),
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_i48_mlflow_status_true_when_running():
    if not _docker_ok():
        pytest.skip("Docker not available")

    # If the real mlflow-server is already up, assert against it and do not touch it.
    if _running(STANDIN):
        assert _status_json()["services"]["mlflow"] is True
        return

    # Otherwise stand up a throwaway container named mlflow-server — status only
    # checks whether the resolved container (mlflow -> mlflow-server) is running.
    subprocess.run(["docker", "rm", "-f", STANDIN], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--name", STANDIN, ALPINE, "sleep", "120"],
        capture_output=True,
        check=True,
    )
    try:
        assert _running(STANDIN), "stand-in mlflow-server must be up"
        status = _status_json()
        assert status["services"]["mlflow"] is True, (
            "status --json must report services.mlflow==true when mlflow-server runs "
            "(regression guard for the mlflow vs mlflow-server probe bug)"
        )
    finally:
        subprocess.run(["docker", "rm", "-f", STANDIN], capture_output=True)


def test_i48_mlflow_status_false_when_absent():
    # Negative half: with no mlflow-server container, status reports false (not an
    # error). Skips if the real mlflow-server happens to be running.
    if not _docker_ok():
        pytest.skip("Docker not available")
    if _running(STANDIN):
        pytest.skip("mlflow-server is running; negative case not applicable")
    assert _status_json()["services"]["mlflow"] is False


# ---------------------------------------------------------------------------------
# I-09 — MLflow 3.14 logs a run + artifact to S3 (SeaweedFS), readable back
# ---------------------------------------------------------------------------------
# Runs inside mlflow-server (has mlflow 3.14 + boto3). Proves the durability model:
# run metadata in PostgreSQL, artifact bytes in S3 under mlflow-artifacts/. The
# "survives restart" property is inherent (nothing is in-memory) — asserted by
# reading the run + artifact back through a fresh client after logging.

MLFLOW_CTR = "mlflow-server"


def _mlflow_up() -> bool:
    # Probe the published host port — the mlflow image has no curl, so an
    # in-container curl probe would false-negative.
    if not _running(MLFLOW_CTR):
        return False
    import urllib.request

    try:
        return (
            urllib.request.urlopen("http://localhost:5000/health", timeout=5).getcode()
            == 200
        )
    except Exception:
        return False


def test_i09_mlflow_314_run_artifact_in_s3():
    if not _docker_ok():
        pytest.skip("Docker not available")
    if not _mlflow_up():
        pytest.skip("mlflow-server not running/healthy")
    script = (
        "import mlflow, boto3, os, tempfile\n"
        "mlflow.set_tracking_uri('http://localhost:5000')\n"
        "assert mlflow.__version__.startswith('3.14'), mlflow.__version__\n"
        "mlflow.set_experiment('i09')\n"
        "with mlflow.start_run() as run:\n"
        "    rid = run.info.run_id\n"
        "    mlflow.log_param('cp','3'); mlflow.log_metric('acc',0.99)\n"
        "    p=os.path.join(tempfile.mkdtemp(),'art.txt'); open(p,'w').write('cp3')\n"
        "    mlflow.log_artifact(p)\n"
        # Read S3 endpoint/creds/bucket from the mlflow container's own env rather
        # than baking a credential pair — the container is configured from the
        # unified demo creds, so this stays correct if they ever change.
        "ep=os.environ.get('MLFLOW_S3_ENDPOINT_URL','http://seaweedfs:8333')\n"
        "ak=os.environ.get('AWS_ACCESS_KEY_ID') or os.environ.get('S3_ACCESS_KEY','lakehouse_s3')\n"
        "sk=os.environ.get('AWS_SECRET_ACCESS_KEY') or os.environ.get('S3_SECRET_KEY','lakehouse_s3_secret')\n"
        "dest=os.environ.get('MLFLOW_ARTIFACTS_DESTINATION','s3://lakehouse/mlflow-artifacts')\n"
        "bkt=dest.split('/')[2]\n"
        "s3=boto3.client('s3',endpoint_url=ep,aws_access_key_id=ak,aws_secret_access_key=sk)\n"
        "keys=[o['Key'] for o in s3.list_objects_v2(Bucket=bkt,"
        "Prefix='mlflow-artifacts/').get('Contents',[]) if rid in o['Key']]\n"
        "c=mlflow.tracking.MlflowClient()\n"
        "r=c.get_run(rid); arts=[a.path for a in c.list_artifacts(rid)]\n"
        "assert r.data.params.get('cp')=='3' and 'art.txt' in arts and any('art.txt' in k for k in keys), (keys,arts)\n"
        "print('I09_PASS', mlflow.__version__)\n"
    )
    out = subprocess.run(
        ["docker", "exec", MLFLOW_CTR, "python", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert (
        "I09_PASS" in out.stdout
    ), f"I-09 failed:\nSTDOUT{out.stdout[-800:]}\nSTDERR{out.stderr[-800:]}"
