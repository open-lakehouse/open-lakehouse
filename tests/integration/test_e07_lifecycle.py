"""E-07 — agent build -> demo -> teardown -> rebuild, end to end (PR #0, Checkpoint 7).

The open-lakehouse philosophy is that an agent can build an environment, run a demo,
tear it all down, and rebuild it clean and identical. E-07 proves that cycle.

Per the plan it runs ON THE TEST OVERLAY ONLY (§1.15.5) — every resource is run-scoped
(ol_test_<runid>_* / ol-test-<runid>), and the destructive step is the PRODUCTION CLI
(`reset --all --yes`) driven under the active overlay, exercising the runtime semantic
gate that guards R-38. It uses a DEDICATED lifecycle fixture, NOT `sdp-medallion`
(which is internally incoherent and needs a PR #1 capability — §1.18.7).

The "demo" is a minimal, overlay-aware Unity Catalog artifact: a catalog/schema/table
plus its S3 warehouse object. Unity Catalog is brought up through the OVERLAY COMPOSE
(the same mechanism `./lakehouse start` uses) so that reset's quiesce — a
`docker compose down` — genuinely removes the run-scoped UC container and wipes its
embedded-H2 catalog state, then restarts it fresh.

Cycle: start -> build+verify -> reset --all --yes -> assert APPLICATION-empty
(§1.17.5) -> rebuild -> assert clean and identical.

FAIL-CLOSED: skips unless LAKEHOUSE_TEST_RUN_ID is set (isolation guard), Docker + aws
are available, and host PostgreSQL + SeaweedFS are reachable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LAKEHOUSE = REPO_ROOT / "lakehouse"
OVERLAY_DIR = REPO_ROOT / "tests" / "overlays"

sys.path.insert(0, str(REPO_ROOT / "tests"))
import isolation  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.merge, pytest.mark.slow]

PG_USER = os.environ.get("POSTGRES_USER", "lakehouse")
PG_PASS = os.environ.get("POSTGRES_PASSWORD", "lakehouse_pw")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
S3_KEY = os.environ.get("S3_ACCESS_KEY", "lakehouse_s3")
S3_SECRET = os.environ.get("S3_SECRET_KEY", "lakehouse_s3_secret")
S3_ENDPOINT_HOST = "http://localhost:8333"
PG_IMAGE = os.environ.get("LAKEHOUSE_PG_CLIENT_IMAGE", "postgres:15-alpine")
PY_IMAGE = os.environ.get("LAKEHOUSE_HTTP_IMAGE", "python:3-alpine")

CAT, SCH, TBL = "e07", "s1", "orders"


def _psql(db: str, sql: str, tuples: bool = False) -> subprocess.CompletedProcess:
    flag = "-tAc" if tuples else "-c"
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--add-host=host.docker.internal:host-gateway",
            "-e",
            f"PGPASSWORD={PG_PASS}",
            PG_IMAGE,
            "psql",
            "-h",
            "host.docker.internal",
            "-p",
            PG_PORT,
            "-U",
            PG_USER,
            "-d",
            db,
            flag,
            sql,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _aws(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["aws", "--endpoint-url", S3_ENDPOINT_HOST, "s3", *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=90,
        env={
            **os.environ,
            "AWS_ACCESS_KEY_ID": S3_KEY,
            "AWS_SECRET_ACCESS_KEY": S3_SECRET,
        },
    )


def _aws_retry(*args: str, stdin: str | None = None, tries: int = 6) -> bool:
    """Run an aws s3 command, retrying transient SeaweedFS hiccups. Local SeaweedFS
    can return a transient InternalError — e.g. if the host sleeps mid-run (a laptop
    lid-close pauses the container + drops the connection), or needs a moment after a
    bucket is created before it accepts writes; a bounded retry keeps E-07
    deterministic without masking a real failure (the last rc is asserted by caller)."""
    for i in range(tries):
        r = _aws(*args, stdin=stdin)
        if r.returncode == 0:
            return True
        time.sleep(1 + i)
    return False


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


def _compose(env, *args) -> subprocess.CompletedProcess:
    base = REPO_ROOT / "docker-compose-unity-catalog.yml"
    overlay = OVERLAY_DIR / "docker-compose-unity-catalog.test.yml"
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            env["overlay"]["LAKEHOUSE_ENV_FILE"],
            "-f",
            str(base),
            "-f",
            str(overlay),
            *args,
        ],
        cwd=REPO_ROOT,
        env=env["overlay"],
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def env():
    rid = isolation.current_run_id()
    if rid is None:
        pytest.skip("LAKEHOUSE_TEST_RUN_ID unset/invalid — E-07 skips (fail-closed)")
    if not (_docker_ok() and shutil.which("aws") and shutil.which("docker")):
        pytest.skip("Docker/aws not available")
    if _psql("postgres", "SELECT 1", tuples=True).returncode != 0:
        pytest.skip("host PostgreSQL not reachable")
    # Retry the reachability probe: SeaweedFS can hiccup for a beat (or the host may
    # briefly sleep mid-run), and a one-shot check would turn that into a SPURIOUS
    # skip (a skip blocks approval, §1.17.8). Only skip if S3 is durably unreachable.
    if not _aws_retry("ls"):
        pytest.skip("host SeaweedFS/S3 not reachable")

    bucket = f"ol-test-{rid}"
    uc = f"unity-catalog-{rid}"
    envfile = REPO_ROOT / ".smoke" / f"env-e07-{rid}"
    envfile.parent.mkdir(exist_ok=True)
    envfile.write_text(
        f"POSTGRES_USER={PG_USER}\nPOSTGRES_PASSWORD={PG_PASS}\n"
        f"POSTGRES_HOST=host.docker.internal\nPOSTGRES_PORT={PG_PORT}\n"
        f"S3_ENDPOINT=http://host.docker.internal:8333\n"
        f"S3_ACCESS_KEY={S3_KEY}\nS3_SECRET_KEY={S3_SECRET}\nS3_BUCKET={bucket}\n"
    )
    overlay = {
        **os.environ,
        "LAKEHOUSE_TEST_RUN_ID": rid,
        "LAKEHOUSE_OVERLAY_DIR": str(OVERLAY_DIR),
        "LAKEHOUSE_RESOURCE_SUFFIX": rid,
        "LAKEHOUSE_ENV_FILE": str(envfile),
        "COMPOSE_PROJECT_NAME": bucket,
    }
    dbs = {k: f"ol_test_{rid}_{k}" for k in ("airflow", "iceberg_catalog", "mlflow")}
    e = {"rid": rid, "overlay": overlay, "bucket": bucket, "uc": uc, "dbs": dbs}
    yield e

    # teardown: bring the overlay UC down, drop run-scoped DBs + bucket + volumes
    _compose(e, "down", "-v")
    subprocess.run(["docker", "rm", "-f", uc], capture_output=True)
    for db in dbs.values():
        _psql("postgres", f'DROP DATABASE IF EXISTS "{db}"')
    _aws("rb", f"s3://{bucket}", "--force")
    for v in subprocess.run(
        ["docker", "volume", "ls", "-q"], capture_output=True, text=True
    ).stdout.split():
        if v.startswith(f"{bucket}_"):
            subprocess.run(["docker", "volume", "rm", v], capture_output=True)
    envfile.unlink(missing_ok=True)


# --- overlay-aware UC helpers (netns transport, run-scoped) ----------------------


def _uc_py(env, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            f"container:{env['uc']}",
            "--entrypoint",
            "python3",
            PY_IMAGE,
            "-",
        ],
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _uc_ready(env, tries: int = 40) -> bool:
    probe = (
        "import urllib.request;urllib.request.urlopen("
        "'http://localhost:8080/api/2.1/unity-catalog/catalogs', timeout=3)"
    )
    for _ in range(tries):
        if _uc_py(env, probe).returncode == 0:
            return True
        time.sleep(3)
    return False


def _catalogs(env) -> list[str]:
    script = (
        "import json,urllib.request;"
        "d=json.load(urllib.request.urlopen("
        "'http://localhost:8080/api/2.1/unity-catalog/catalogs', timeout=10));"
        "print(json.dumps(sorted(c['name'] for c in d.get('catalogs', []))))"
    )
    r = _uc_py(env, script)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return []


def _demo_tables(env) -> list[str]:
    script = f"""
import json, urllib.request
try:
    d = json.load(urllib.request.urlopen(
        'http://localhost:8080/api/2.1/unity-catalog/tables'
        '?catalog_name={CAT}&schema_name={SCH}', timeout=10))
    print(json.dumps([t['name'] for t in d.get('tables', [])]))
except Exception:
    print('[]')
"""
    r = _uc_py(env, script)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return []


def _build_demo(env) -> None:
    """The 'demo': a UC catalog/schema/table + its S3 warehouse object."""
    script = f"""
import json, urllib.request
api = "http://localhost:8080/api/2.1/unity-catalog"
def post(path, body):
    r = urllib.request.Request(api + path, data=json.dumps(body).encode(),
        headers={{"Content-Type": "application/json"}}, method="POST")
    urllib.request.urlopen(r, timeout=10)
# UC 0.5.0 validates the column type descriptor — an empty type_json 400s.
tj = json.dumps({{"name": "id", "type": "integer", "nullable": True, "metadata": {{}}}})
post("/catalogs", {{"name": "{CAT}"}})
post("/schemas", {{"name": "{SCH}", "catalog_name": "{CAT}"}})
post("/tables", {{"name": "{TBL}", "catalog_name": "{CAT}", "schema_name": "{SCH}",
    "table_type": "EXTERNAL", "data_source_format": "DELTA",
    "storage_location": "s3://{env['bucket']}/warehouse/{TBL}",
    "columns": [{{"name": "id", "type_text": "int", "type_name": "INT",
                 "type_json": tj, "position": 0, "nullable": True}}]}})
print("built")
"""
    r = _uc_py(env, script)
    assert r.stdout.strip().endswith(
        "built"
    ), f"demo build failed: {r.stdout} {r.stderr}"
    assert _aws_retry(
        "cp", "-", f"s3://{env['bucket']}/warehouse/{TBL}/_delta_log/0.json", stdin="x"
    ), "demo warehouse object write failed after retries"


def _warehouse_objects(env) -> int:
    r = _aws("ls", f"s3://{env['bucket']}/warehouse/", "--recursive")
    return len([ln for ln in r.stdout.splitlines() if ln.strip()])


def _seed_baseline(env) -> None:
    for db in env["dbs"].values():
        _psql("postgres", f'DROP DATABASE IF EXISTS "{db}"')
        assert (
            _psql("postgres", f'CREATE DATABASE "{db}" OWNER "{PG_USER}"').returncode
            == 0
        )
    # mb then confirm the bucket is writable (SeaweedFS accepts writes a beat after
    # create) so the first demo build is not racing bucket readiness.
    _aws("mb", f"s3://{env['bucket']}")
    assert _aws_retry(
        "cp", "-", f"s3://{env['bucket']}/.ready", stdin="x"
    ), "run-scoped bucket did not become writable"
    _aws("rm", f"s3://{env['bucket']}/.ready")


def _reset_all(env) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(LAKEHOUSE), "reset", "--all", "--yes"],
        cwd=REPO_ROOT,
        env=env["overlay"],
        capture_output=True,
        text=True,
        timeout=300,
    )


# --- E-07 ------------------------------------------------------------------------


def test_e07_build_demo_teardown_rebuild(env):
    # STEP 1 — "start.md": baseline resources + UC up via the overlay compose.
    _seed_baseline(env)
    assert _compose(env, "up", "-d").returncode == 0, "overlay UC must start"
    assert _uc_ready(env), "run-scoped UC must become ready"

    # STEP 2 — build the demo and verify it is present.
    _build_demo(env)
    assert _demo_tables(env) == [TBL], "demo table must be registered"
    assert CAT in _catalogs(env)
    assert _warehouse_objects(env) == 1

    # STEP 3 — teardown via the PRODUCTION CLI under the active overlay. This is the
    # R-38 path: reset resolves real targets and the runtime semantic gate must let it
    # through because every target is run-scoped.
    r = _reset_all(env)
    assert r.returncode == 0, f"reset --all must succeed under the overlay: {r.stderr}"
    assert "Reset complete" in r.stdout
    assert _uc_ready(env), "UC must be restarted by reset (running set restored)"

    # STEP 4 — APPLICATION-empty assertion (§1.17.5): not raw table count, but that
    # the user-created demo is gone. Databases still EXIST (recreated), object store
    # warehouse is empty, and the demo catalog is gone (fresh H2 keeps only the
    # image's default 'unity' catalog).
    assert CAT not in _catalogs(env), "demo catalog must be gone after reset --all"
    assert _demo_tables(env) == [], "demo table must be gone after reset --all"
    assert _warehouse_objects(env) == 0, "S3 warehouse must be empty after reset"
    for db in env["dbs"].values():
        r2 = _psql(
            "postgres", f"SELECT 1 FROM pg_database WHERE datname='{db}'", tuples=True
        )
        assert r2.stdout.strip() == "1", f"{db} must still exist after reset"

    # STEP 5 — rebuild: the SECOND build must be clean and identical to the first.
    _build_demo(env)
    assert _demo_tables(env) == [TBL], "rebuild must reproduce the demo table"
    assert CAT in _catalogs(env)
    assert _warehouse_objects(env) == 1, "rebuild must reproduce the warehouse object"
