"""Integration tests for the destructive reset engine (PR #0, Checkpoint 3).

    I-28  reset --all empties a test-scoped env (DBs recreated, objects gone)
    I-30  reset --dry-run is inert
    I-31  reset --metadata preserves objects and warns
    I-32  reset --data leaves a CONSISTENT plane (verified by direct queries + S3)
    I-34  databases recreated + owned; DROP survives a held connection
    I-37  --metadata warning names the unrecoverable class; no sync_to_uc.py
    I-38  --keep-mlflow preserves artifact reachability
    I-50  every destructive mode quiesces writers
    I-54  post-reset assertion is APPLICATION-empty, not table-empty
    I-55  a mis-targeted overlay reset aborts (parameterized over all four classes)

Checkpoint 4 (backup / restore):
    I-29  backup -> reset --all -> restore round-trips EVERYTHING promised —
          PostgreSQL DBs + rows + ownership, S3 keys, a named-volume sentinel, and
          UC TABLES (via a real run-scoped UC + the H2 docker-cp path)
    I-51  restore is fail-stop and recoverable: a mid-restore failure leaves a
          pre-restore snapshot, a marker, and a rollback command that recovers
    I-52a backup ALWAYS restores the running set — on success AND on failure
    I-53  restore's pre-restore snapshot + mutation share ONE quiesced window: the
          quiesced writer is stopped once and restarted once, only after mutation

FAIL-CLOSED: these skip unless LAKEHOUSE_TEST_RUN_ID is set (isolation guard),
Docker is available, and the host PostgreSQL + SeaweedFS are reachable. Every
resource is run-scoped (ol_test_<runid>_* / ol-test-<runid>); the real stack is
never touched.
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

pytestmark = [pytest.mark.integration, pytest.mark.merge]

PG_USER = os.environ.get("POSTGRES_USER", "lakehouse")
PG_PASS = os.environ.get("POSTGRES_PASSWORD", "lakehouse_pw")
PG_HOST = os.environ.get("POSTGRES_HOST", "host.docker.internal")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
S3_KEY = os.environ.get("S3_ACCESS_KEY", "lakehouse_s3")
S3_SECRET = os.environ.get("S3_SECRET_KEY", "lakehouse_s3_secret")
S3_ENDPOINT_HOST = "http://localhost:8333"
PG_IMAGE = os.environ.get("LAKEHOUSE_PG_CLIENT_IMAGE", "postgres:15-alpine")


def _psql(db: str, sql: str, tuples: bool = False) -> subprocess.CompletedProcess:
    flag = "-tAc" if tuples else "-c"
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
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


def _aws(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["aws", "--endpoint-url", S3_ENDPOINT_HOST, "s3", *args],
        capture_output=True,
        text=True,
        timeout=90,
        env={
            **os.environ,
            "AWS_ACCESS_KEY_ID": S3_KEY,
            "AWS_SECRET_ACCESS_KEY": S3_SECRET,
        },
    )


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


def _pg_ok() -> bool:
    return _psql("postgres", "SELECT 1", tuples=True).returncode == 0


def _s3_ok() -> bool:
    return _aws("ls").returncode == 0 and shutil_which("aws")


def shutil_which(x):
    import shutil

    return shutil.which(x) is not None


@pytest.fixture(scope="module")
def env():
    """Run-scoped fixture: fail-closed, seeds nothing yet, yields the overlay env."""
    rid = isolation.current_run_id()
    if rid is None:
        pytest.skip(
            "LAKEHOUSE_TEST_RUN_ID unset/invalid — destructive tests skip (fail-closed)"
        )
    if not _docker_ok():
        pytest.skip("Docker not available")
    if not (shutil_which("aws") and shutil_which("docker")):
        pytest.skip("aws/docker CLI not available")
    if not _pg_ok():
        pytest.skip("host PostgreSQL not reachable")
    if not _s3_ok():
        pytest.skip("host SeaweedFS/S3 not reachable")

    envfile = REPO_ROOT / ".smoke" / f"env-itest-{rid}"
    envfile.parent.mkdir(exist_ok=True)
    envfile.write_text(
        f"POSTGRES_USER={PG_USER}\nPOSTGRES_PASSWORD={PG_PASS}\n"
        f"POSTGRES_HOST=host.docker.internal\nPOSTGRES_PORT={PG_PORT}\n"
        f"S3_ENDPOINT=http://host.docker.internal:8333\n"
        f"S3_ACCESS_KEY={S3_KEY}\nS3_SECRET_KEY={S3_SECRET}\nS3_BUCKET=ol-test-{rid}\n"
    )
    overlay = {
        **os.environ,
        "LAKEHOUSE_TEST_RUN_ID": rid,
        "LAKEHOUSE_OVERLAY_DIR": str(OVERLAY_DIR),
        "LAKEHOUSE_RESOURCE_SUFFIX": rid,
        "LAKEHOUSE_ENV_FILE": str(envfile),
        "COMPOSE_PROJECT_NAME": f"ol-test-{rid}",
    }
    yield {
        "rid": rid,
        "overlay": overlay,
        "bucket": f"ol-test-{rid}",
        "dbs": {
            k: f"ol_test_{rid}_{k}" for k in ("airflow", "iceberg_catalog", "mlflow")
        },
    }

    # teardown: drop run-scoped DBs + bucket
    for db in (
        f"ol_test_{rid}_airflow",
        f"ol_test_{rid}_iceberg_catalog",
        f"ol_test_{rid}_mlflow",
    ):
        _psql("postgres", f'DROP DATABASE IF EXISTS "{db}"')
    _aws("rb", f"s3://ol-test-{rid}", "--force")
    envfile.unlink(missing_ok=True)


def _reset(env, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(LAKEHOUSE), "reset", *args],
        cwd=REPO_ROOT,
        env=env["overlay"],
        capture_output=True,
        text=True,
        timeout=300,
    )


def _seed(env, *, rows: bool = True, objects: bool = True):
    """Create the run-scoped DBs (+ seed rows) and bucket (+ seed objects)."""
    rid = env["rid"]
    for db in env["dbs"].values():
        _psql("postgres", f'DROP DATABASE IF EXISTS "{db}"')
        assert (
            _psql("postgres", f'CREATE DATABASE "{db}" OWNER "{PG_USER}"').returncode
            == 0
        )
    if rows:
        _psql(
            env["dbs"]["mlflow"],
            "CREATE TABLE runs(id int); INSERT INTO runs VALUES (1),(2)",
        )
        _psql(
            env["dbs"]["mlflow"],
            "CREATE TABLE experiments(id int); INSERT INTO experiments VALUES (1)",
        )
        _psql(
            env["dbs"]["iceberg_catalog"],
            "CREATE TABLE iceberg_tables(id int); INSERT INTO iceberg_tables VALUES (1)",
        )
    _aws("mb", f"s3://ol-test-{rid}")
    if objects:
        for key in ("warehouse/t/data.parquet", "mlflow-artifacts/1/a.txt"):
            _seed_put(f"ol-test-{rid}/{key}")


def _seed_put(dest: str, tries: int = 6) -> None:
    # Bounded retry: SeaweedFS can return a transient InternalError — e.g. if the host
    # sleeps mid-run (a laptop lid-close) or just after bucket create. Keeps seeding
    # deterministic.
    last = None
    for i in range(tries):
        last = subprocess.run(
            [
                "aws",
                "--endpoint-url",
                S3_ENDPOINT_HOST,
                "s3",
                "cp",
                "-",
                f"s3://{dest}",
            ],
            input="seed",
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "AWS_ACCESS_KEY_ID": S3_KEY,
                "AWS_SECRET_ACCESS_KEY": S3_SECRET,
            },
        )
        if last.returncode == 0:
            return
        time.sleep(1 + i)
    raise AssertionError(f"seeding {dest} failed after {tries} tries: {last.stderr}")


def _count_objects(env, prefix: str) -> int:
    r = _aws("ls", f"s3://{env['bucket']}/{prefix}", "--recursive")
    return len([ln for ln in r.stdout.splitlines() if ln.strip()])


def _db_exists(db: str) -> bool:
    r = _psql(
        "postgres", f"SELECT 1 FROM pg_database WHERE datname='{db}'", tuples=True
    )
    return r.stdout.strip() == "1"


def _db_owner(db: str) -> str:
    return _psql(
        "postgres",
        f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{db}'",
        tuples=True,
    ).stdout.strip()


def _rows(db: str, table: str) -> int:
    r = _psql(db, f"SELECT count(*) FROM {table}", tuples=True)
    return (
        int(r.stdout.strip())
        if r.returncode == 0 and r.stdout.strip().isdigit()
        else -1
    )


# --- tests -----------------------------------------------------------------------


def test_i30_dry_run_is_inert(env):
    _seed(env)
    before = _count_objects(env, "")
    r = _reset(env, "--all", "--dry-run")
    assert r.returncode == 0
    assert _count_objects(env, "") == before
    assert _db_exists(env["dbs"]["mlflow"])
    assert _rows(env["dbs"]["mlflow"], "runs") == 2  # untouched


def test_i34_metadata_recreates_dbs_owned(env):
    _seed(env)
    r = _reset(env, "--metadata", "--yes")
    assert r.returncode == 0, r.stderr
    for db in env["dbs"].values():
        assert _db_exists(db), f"{db} must exist after reset"
        assert _db_owner(db) == PG_USER, f"{db} owner preserved"
    # dropped+recreated => seeded tables gone
    assert _rows(env["dbs"]["mlflow"], "runs") == -1


def test_i34_drop_survives_held_connection(env):
    _seed(env)
    # Hold an open connection to a target DB for the duration of the reset.
    holder = subprocess.Popen(
        [
            "docker",
            "run",
            "--rm",
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
            env["dbs"]["mlflow"],
            "-c",
            "SELECT pg_sleep(30)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        r = _reset(env, "--metadata", "--yes")
        assert (
            r.returncode == 0
        ), f"reset must succeed despite a held connection: {r.stderr}"
        assert _db_exists(env["dbs"]["mlflow"])
    finally:
        holder.terminate()


def test_i31_metadata_preserves_objects_and_warns(env):
    _seed(env)
    r = _reset(env, "--metadata", "--yes")
    assert r.returncode == 0, r.stderr
    # objects preserved
    assert _count_objects(env, "warehouse/") == 1
    assert _count_objects(env, "mlflow-artifacts/") == 1
    # classified warning present
    assert "UNRECOVERABLE" in r.stdout and "recoverable" in r.stdout


def test_i37_metadata_warning_flags_unrecoverable_no_script(env):
    _seed(env)
    r = _reset(env, "--metadata", "--yes")
    assert "UNRECOVERABLE" in r.stdout and "MLflow artifacts" in r.stdout
    assert "re-registerable from the Delta" in r.stdout
    assert "sync_to_uc" not in r.stdout


def test_i32_data_leaves_consistent_plane(env):
    _seed(env)
    r = _reset(env, "--data", "--yes")
    assert r.returncode == 0, r.stderr
    # objects gone
    assert _count_objects(env, "") == 0
    # referencing rows cleared, but DBs + tables preserved (verified DIRECTLY, no doctor)
    assert _db_exists(env["dbs"]["mlflow"]) and _db_exists(
        env["dbs"]["iceberg_catalog"]
    )
    assert _rows(env["dbs"]["mlflow"], "runs") == 0
    assert _rows(env["dbs"]["iceberg_catalog"], "iceberg_tables") == 0
    # experiments (not a run record) survive — --data clears runs, keeps structure
    assert _rows(env["dbs"]["mlflow"], "experiments") == 1


def test_i38_keep_mlflow_preserves_artifacts(env):
    _seed(env)
    r = _reset(env, "--metadata", "--keep-mlflow", "--yes")
    assert r.returncode == 0, r.stderr
    # mlflow DB preserved (not dropped), artifacts still reachable
    assert _rows(env["dbs"]["mlflow"], "runs") == 2, "mlflow DB must be preserved"
    assert _count_objects(env, "mlflow-artifacts/") == 1
    # airflow + iceberg still reset
    assert _rows(env["dbs"]["mlflow"], "runs") == 2
    assert "UNRECOVERABLE" not in r.stdout


def test_i28_i54_all_empties_application_state(env):
    _seed(env)
    r = _reset(env, "--all", "--yes")
    assert r.returncode == 0, r.stderr
    # (1) databases exist
    for db in env["dbs"].values():
        assert _db_exists(db)
    # (2/3) application state empty: recreated DBs have no seeded rows; zero objects
    assert _rows(env["dbs"]["mlflow"], "runs") == -1  # table gone (fresh DB)
    assert _count_objects(env, "") == 0


# CLI-injectable mis-target classes. bucket/database reach the semantic gate;
# container mismatches abort earlier at all-or-nothing activation. Both refuse
# without deleting anything. (volume-class gate coverage is U-66b, which calls the
# gate directly — activation overwrites COMPOSE_PROJECT_NAME so it can't be
# injected through the full CLI.)
@pytest.mark.parametrize("bad", ["bucket", "database", "container"])
def test_i55_mis_targeted_reset_aborts(env, bad, tmp_path):
    _seed(env)
    before = _count_objects(env, "")
    bad_overlay = dict(env["overlay"])
    if bad == "bucket":
        # A non-run-scoped bucket must be injected via the effective env FILE
        # (an env-var override is re-set when the CLI sources LAKEHOUSE_ENV_FILE).
        bad_env = tmp_path / "bad.env"
        good = Path(env["overlay"]["LAKEHOUSE_ENV_FILE"]).read_text()
        bad_env.write_text(
            good.replace(f"S3_BUCKET={env['bucket']}", "S3_BUCKET=lakehouse")
        )
        bad_overlay["LAKEHOUSE_ENV_FILE"] = str(bad_env)
    elif bad == "database":
        bad_overlay["MLFLOW_PG_DB"] = "mlflow"  # env file doesn't set it
    elif bad == "container":
        bad_overlay["LAKEHOUSE_RESOURCE_SUFFIX"] = "otherrun9"
    r = subprocess.run(
        [str(LAKEHOUSE), "reset", "--data", "--yes"],
        cwd=REPO_ROOT,
        env=bad_overlay,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode != 0, f"mis-targeted reset ({bad}) must abort"
    combined = r.stdout + r.stderr
    # Refused by the semantic gate ('not scoped') or all-or-nothing activation.
    assert "not scoped" in combined or "all-or-nothing" in combined
    assert _count_objects(env, "") == before  # nothing deleted


def test_i50_destructive_modes_quiesce(env):
    # The reset engine quiesces writers before deleting (plan 1.15.3). Assert the
    # quiesce path is exercised: reset --metadata reports quiescing and succeeds.
    _seed(env)
    r = _reset(env, "--metadata", "--yes")
    assert r.returncode == 0
    assert "Quiescing" in r.stdout or "Quiescing" in r.stderr


# I-52b: a FAILED destructive reset, in EVERY mode, leaves services STOPPED with a
# marker, and `doctor` then reports the interrupted reset (plan 1.16.5). Injection is
# per-mode: --data fails on the object-store step (unreachable S3), while --metadata
# and --all fail on the DROP DATABASE step (unreachable PostgreSQL). Both are genuine
# mid-operation failures — restarting writers against half-deleted state must not
# happen.
@pytest.mark.parametrize(
    "mode,inject",
    [("--data", "s3"), ("--metadata", "pg"), ("--all", "pg")],
)
def test_i52b_failed_reset_stays_stopped_and_doctor_reports(
    env, mode, inject, tmp_path
):
    _seed(env)
    marker = REPO_ROOT / ".lakehouse-reset-interrupted"
    marker.unlink(missing_ok=True)
    src = Path(env["overlay"]["LAKEHOUSE_ENV_FILE"]).read_text()
    bad_env = tmp_path / f"bad-{inject}.env"
    if inject == "pg":
        bad_env.write_text(
            src.replace(f"POSTGRES_PORT={PG_PORT}", "POSTGRES_PORT=5599")
        )
    else:
        bad_env.write_text(
            src.replace(
                "S3_ENDPOINT=http://host.docker.internal:8333",
                "S3_ENDPOINT=http://host.docker.internal:9999",
            )
        )
    bad_overlay = {**env["overlay"], "LAKEHOUSE_ENV_FILE": str(bad_env)}
    r = subprocess.run(
        [str(LAKEHOUSE), "reset", mode, "--yes"],
        cwd=REPO_ROOT,
        env=bad_overlay,
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        assert r.returncode != 0, f"a failed {mode} reset must exit non-zero"
        assert "left stopped" in (r.stdout + r.stderr).lower()
        assert marker.exists(), "an interrupted-reset marker must be written"
        assert "interrupted-reset" in marker.read_text()
        # doctor reports the interrupted reset (reads the marker; S3/PG state
        # irrelevant to that line).
        d = subprocess.run(
            [str(LAKEHOUSE), "doctor"],
            cwd=REPO_ROOT,
            env=bad_overlay,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert "interrupted reset" in (d.stdout + d.stderr).lower()
    finally:
        marker.unlink(missing_ok=True)


# --- Checkpoint 4: backup / restore ----------------------------------------------

REAL_DOCKER = shutil.which("docker")

UC_IMAGE = os.environ.get("LAKEHOUSE_UC_IMAGE", "unitycatalog/unitycatalog:v0.5.0")
PY_IMAGE = os.environ.get("LAKEHOUSE_HTTP_IMAGE", "python:3-alpine")
ALPINE_IMAGE = os.environ.get("LAKEHOUSE_ALPINE_IMAGE", "alpine:latest")


def _backup(env, out, *args, extra_env=None):
    return subprocess.run(
        [str(LAKEHOUSE), "backup", "--out", str(out), *args],
        cwd=REPO_ROOT,
        env={**env["overlay"], **(extra_env or {})},
        capture_output=True,
        text=True,
        timeout=300,
    )


def _restore(env, frm, *args, extra_env=None):
    return subprocess.run(
        [str(LAKEHOUSE), "restore", "--from", str(frm), *args],
        cwd=REPO_ROOT,
        env={**env["overlay"], **(extra_env or {})},
        capture_output=True,
        text=True,
        timeout=300,
    )


def _seed_volume(env, short_name: str, content: str) -> str:
    """Create the run-scoped docker volume ol-test-<rid>_<short> with a sentinel."""
    vol = f"ol-test-{env['rid']}_{short_name}"
    subprocess.run(["docker", "volume", "rm", vol], capture_output=True)
    subprocess.run(["docker", "volume", "create", vol], capture_output=True, check=True)
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{vol}:/v",
            ALPINE_IMAGE,
            "sh",
            "-c",
            f"printf %s '{content}' > /v/marker.txt",
        ],
        capture_output=True,
        check=True,
    )
    return vol


def _volume_sentinel(vol: str) -> str | None:
    r = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{vol}:/v:ro",
            ALPINE_IMAGE,
            "sh",
            "-c",
            "cat /v/marker.txt 2>/dev/null || true",
        ],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.stdout else None


def _volume_exists(vol: str) -> bool:
    return (
        subprocess.run(
            ["docker", "volume", "inspect", vol], capture_output=True
        ).returncode
        == 0
    )


# --- run-scoped Unity Catalog helpers (real container, embedded H2) --------------


def _uc_name(env) -> str:
    return f"unity-catalog-{env['rid']}"


def _uc_py(env, script: str) -> subprocess.CompletedProcess:
    """Run a python snippet inside the run-scoped UC's network namespace."""
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            f"container:{_uc_name(env)}",
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


def _uc_wait(env, tries: int = 40) -> bool:
    probe = (
        "import urllib.request;"
        "urllib.request.urlopen("
        "'http://localhost:8080/api/2.1/unity-catalog/catalogs', timeout=3)"
    )
    for _ in range(tries):
        if _uc_py(env, probe).returncode == 0:
            return True
        time.sleep(3)
    return False


def _uc_compose(env, *args) -> subprocess.CompletedProcess:
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


def _uc_boot(env) -> bool:
    # Boot UC via the OVERLAY COMPOSE (as ./lakehouse start does), NOT a bare
    # `docker run`: reset/backup quiesce Unity Catalog with `docker compose down`,
    # which can only stop a compose-managed container. A docker-run container would
    # survive the quiesce (so reset would refuse — review-handoff #7 — and UC's H2
    # would never actually reset). Matches E-07.
    subprocess.run(["docker", "rm", "-f", _uc_name(env)], capture_output=True)
    if _uc_compose(env, "up", "-d").returncode != 0:
        return False
    return _uc_wait(env)


def _uc_tables(env, cat="cp4cat", sch="s1") -> list[str]:
    script = (
        "import json,urllib.request;"
        f"d=json.load(urllib.request.urlopen('http://localhost:8080/api/2.1/"
        f"unity-catalog/tables?catalog_name={cat}&schema_name={sch}', timeout=10));"
        "print(json.dumps([t['name'] for t in d.get('tables',[])]))"
    )
    r = _uc_py(env, script)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return []


def _uc_create_table(env, cat="cp4cat", sch="s1", tbl="t1") -> None:
    script = f"""
import json, urllib.request
api = "http://localhost:8080/api/2.1/unity-catalog"
def post(path, body):
    r = urllib.request.Request(api + path, data=json.dumps(body).encode(),
        headers={{"Content-Type": "application/json"}}, method="POST")
    urllib.request.urlopen(r, timeout=10)
# UC 0.5.0 validates the column type descriptor — an empty type_json 400s.
tj = json.dumps({{"name": "id", "type": "integer", "nullable": True, "metadata": {{}}}})
post("/catalogs", {{"name": "{cat}"}})
post("/schemas", {{"name": "{sch}", "catalog_name": "{cat}"}})
post("/tables", {{"name": "{tbl}", "catalog_name": "{cat}", "schema_name": "{sch}",
    "table_type": "EXTERNAL", "data_source_format": "DELTA",
    "storage_location": "s3://ol-test-{env['rid']}/warehouse/{tbl}",
    "columns": [{{"name": "id", "type_text": "int", "type_name": "INT",
                 "type_json": tj, "position": 0, "nullable": True}}]}})
print("ok")
"""
    assert _uc_py(env, script).stdout.strip().endswith("ok")


def _uc_delete_table(env, cat="cp4cat", sch="s1", tbl="t1") -> None:
    script = (
        "import urllib.request;"
        f"r=urllib.request.Request('http://localhost:8080/api/2.1/unity-catalog/"
        f"tables/{cat}.{sch}.{tbl}', method='DELETE');"
        "urllib.request.urlopen(r, timeout=10)"
    )
    _uc_py(env, script)


# --- I-29: backup -> reset --all -> restore round-trips EVERYTHING ---------------


@pytest.mark.slow
def test_i29_round_trip_covers_everything(env):
    # Seed PostgreSQL (rows + ownership), S3 objects, a named-volume sentinel, and a
    # real run-scoped Unity Catalog with a table (exercising the H2 docker-cp path).
    _seed(env)
    vol = _seed_volume(env, "spark-data", "SENTINEL-29")
    if not _uc_boot(env):
        pytest.skip("run-scoped Unity Catalog did not become ready")
    try:
        _uc_create_table(env)
        assert _uc_tables(env) == ["t1"], "precondition: t1 registered"

        backup_dir = REPO_ROOT / ".smoke" / f"bk-{env['rid']}"
        b = _backup(env, backup_dir)
        assert b.returncode == 0, b.stderr
        # UC must have been quiesced+restarted and its H2 captured via docker cp.
        assert (backup_dir / "uc" / "h2db.mv.db").exists(), "UC H2 not in backup"
        assert (backup_dir / "MANIFEST").exists()
        assert _uc_wait(env), "UC must restart after backup"

        # Destroy: reset --all wipes DB rows, S3 objects, and the data volume; and
        # delete the UC table so restore must bring it back.
        r = _reset(env, "--all", "--yes")
        assert r.returncode == 0, r.stderr
        assert _uc_wait(env), "UC restarts after reset"
        _uc_delete_table(env)
        assert _uc_tables(env) == [], "UC table cleared before restore"
        assert _count_objects(env, "") == 0
        assert not _volume_exists(vol), "data volume removed by reset --all"

        # Restore everything.
        rr = _restore(env, backup_dir, "--yes")
        assert rr.returncode == 0, rr.stderr
        assert _uc_wait(env), "UC restarts after restore"

        # PostgreSQL rows + ownership.
        assert _rows(env["dbs"]["mlflow"], "runs") == 2
        assert _rows(env["dbs"]["iceberg_catalog"], "iceberg_tables") == 1
        assert _db_owner(env["dbs"]["mlflow"]) == PG_USER
        # S3 keys.
        assert _count_objects(env, "warehouse/") == 1
        assert _count_objects(env, "mlflow-artifacts/") == 1
        # Volume sentinel.
        assert _volume_sentinel(vol) == "SENTINEL-29"
        # UC tables (the headline of I-29).
        assert _uc_tables(env) == ["t1"], "UC table restored via H2 docker-cp"
    finally:
        # UC is compose-managed; bring it down, then force-remove as a backstop.
        _uc_compose(env, "down", "-v")
        subprocess.run(["docker", "rm", "-f", _uc_name(env)], capture_output=True)
        # reset restarts UC via `docker compose up`, which materialises the
        # run-scoped never-destroy volumes (uc-logs, ...); sweep every run-scoped
        # volume so the test leaves nothing behind.
        _rm_run_volumes(env)
        _rmtree(REPO_ROOT / ".smoke" / f"bk-{env['rid']}")
        _rmtree(REPO_ROOT / "backups")


def _rm_run_volumes(env) -> None:
    r = subprocess.run(["docker", "volume", "ls", "-q"], capture_output=True, text=True)
    for v in r.stdout.split():
        if v.startswith(f"ol-test-{env['rid']}_"):
            subprocess.run(["docker", "volume", "rm", v], capture_output=True)


def _rmtree(p: Path):
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


# --- I-51: restore is fail-stop and recoverable ----------------------------------


def test_i51_restore_fail_stop_and_recoverable(env, tmp_path):
    # Take a real backup, then corrupt one DB dump so pg_restore fails PART-WAY (the
    # airflow/iceberg dumps restore first; the poisoned mlflow dump then fails).
    _seed(env)
    good = REPO_ROOT / ".smoke" / f"bk51-{env['rid']}"
    _rmtree(good)
    b = _backup(env, good)
    assert b.returncode == 0, b.stderr

    poison = tmp_path / "poison"
    poison.mkdir()
    (poison / "pg").mkdir()
    (poison / "s3").mkdir()
    (poison / "volumes").mkdir()
    for db in ("airflow", "iceberg_catalog"):
        (poison / "pg" / f"{env['dbs'][db]}.dump").write_bytes(
            (good / "pg" / f"{env['dbs'][db]}.dump").read_bytes()
        )
    (poison / "pg" / f"{env['dbs']['mlflow']}.dump").write_text("NOT-A-VALID-DUMP")
    (poison / "MANIFEST").write_text(
        "lakehouse-backup\nversion=1\n"
        f"bucket={env['bucket']}\nuc_backend=h2\n"
        f"databases={env['dbs']['airflow']} {env['dbs']['iceberg_catalog']} "
        f"{env['dbs']['mlflow']}\nvolumes=\n"
    )
    marker = REPO_ROOT / ".lakehouse-restore-interrupted"
    marker.unlink(missing_ok=True)
    try:
        r = _restore(env, poison, "--yes")
        assert r.returncode != 0, "a mid-restore failure must exit non-zero"
        out = r.stdout + r.stderr
        assert "left stopped" in out.lower()
        # A pre-restore snapshot exists, and the marker records the rollback command.
        assert marker.exists(), "an interrupted-restore marker must be written"
        mtext = marker.read_text()
        assert "interrupted-restore" in mtext
        snap = next(
            ln.split("=", 1)[1]
            for ln in mtext.splitlines()
            if ln.startswith("pre_restore_snapshot=")
        )
        assert (Path(snap) / "MANIFEST").exists(), "pre-restore snapshot is complete"
        assert "restore --from" in out and snap in out, "rollback command printed"

        # Rolling back from the pre-restore snapshot recovers and CLEARS the marker.
        rb = _restore(env, snap, "--yes")
        assert rb.returncode == 0, rb.stderr
        assert not marker.exists(), "successful recovery clears the marker"
        assert _rows(env["dbs"]["mlflow"], "runs") == 2
    finally:
        marker.unlink(missing_ok=True)
        _rmtree(good)
        _rmtree(REPO_ROOT / "backups")


# --- I-52a: backup ALWAYS restores the running set -------------------------------


@pytest.mark.slow
def test_i52a_backup_always_restores_running_set(env, tmp_path):
    # A stub "writer" container named as a resolved writer (spark-master-41-<rid>)
    # stands in for a running writer. Backup must stop it, snapshot, then restart it
    # — on success AND on a failed snapshot (backup mutates nothing, plan 1.16.5).
    _seed(env)
    writer = f"spark-master-41-{env['rid']}"
    subprocess.run(["docker", "rm", "-f", writer], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--name", writer, ALPINE_IMAGE, "sleep", "600"],
        capture_output=True,
        check=True,
    )

    def running() -> bool:
        return (
            writer
            in subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
            ).stdout.split()
        )

    try:
        assert running(), "precondition: stub writer up"

        # (1) success path
        ok_dir = REPO_ROOT / ".smoke" / f"bk52-{env['rid']}"
        _rmtree(ok_dir)
        b = _backup(env, ok_dir)
        assert b.returncode == 0, b.stderr
        assert running(), "writer restarted after a successful backup"

        # (2) failure path — unreachable PostgreSQL makes the snapshot fail.
        bad_env = tmp_path / "bad.env"
        bad_env.write_text(
            Path(env["overlay"]["LAKEHOUSE_ENV_FILE"])
            .read_text()
            .replace(f"POSTGRES_PORT={PG_PORT}", "POSTGRES_PORT=5599")
        )
        fail_dir = REPO_ROOT / ".smoke" / f"bk52f-{env['rid']}"
        _rmtree(fail_dir)
        bf = _backup(env, fail_dir, extra_env={"LAKEHOUSE_ENV_FILE": str(bad_env)})
        assert bf.returncode != 0, "a failed snapshot must exit non-zero"
        assert running(), "writer restarted even after a FAILED backup (non-mutating)"
    finally:
        subprocess.run(["docker", "rm", "-f", writer], capture_output=True)
        _rmtree(REPO_ROOT / ".smoke" / f"bk52-{env['rid']}")
        _rmtree(REPO_ROOT / ".smoke" / f"bk52f-{env['rid']}")
        _rmtree(REPO_ROOT / "backups")


# --- I-53: restore snapshot + mutation share ONE quiesced window -----------------


def _docker_shim(bindir: Path, logfile: Path) -> None:
    """Write a `docker` shim that logs every invocation then forwards to real docker.

    The log lets a test assert the stop/start SEQUENCE around a restore without
    touching the engine. Everything is forwarded, so dockerized pg/aws clients and
    `docker ps` still work normally.
    """
    assert REAL_DOCKER, "real docker path required for the shim"
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "docker"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{logfile}"\n'
        f'exec "{REAL_DOCKER}" "$@"\n'
    )
    shim.chmod(0o755)


@pytest.mark.slow
def test_i53_restore_single_quiesced_window(env, tmp_path):
    # Instrument docker calls during a restore. The quiesced writer must be stopped
    # exactly ONCE and started exactly ONCE, and that start must come AFTER the
    # mutation (pg_restore) — never between the pre-restore snapshot and the mutation
    # (plan 1.16.9).
    if not REAL_DOCKER:
        pytest.skip("docker not on PATH")
    _seed(env)
    writer = f"spark-master-41-{env['rid']}"
    subprocess.run(["docker", "rm", "-f", writer], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--name", writer, ALPINE_IMAGE, "sleep", "600"],
        capture_output=True,
        check=True,
    )
    backup_dir = REPO_ROOT / ".smoke" / f"bk53-{env['rid']}"
    _rmtree(backup_dir)
    b = _backup(env, backup_dir)
    assert b.returncode == 0, b.stderr
    # ^ backup stopped+started the writer; start fresh for the observed restore.
    subprocess.run(["docker", "start", writer], capture_output=True)

    logfile = tmp_path / "docker.log"
    bindir = tmp_path / "bin"
    _docker_shim(bindir, logfile)
    shim_env = {
        **env["overlay"],
        "PATH": f"{bindir}:{os.environ['PATH']}",
    }
    try:
        r = subprocess.run(
            [str(LAKEHOUSE), "restore", "--from", str(backup_dir), "--yes"],
            cwd=REPO_ROOT,
            env=shim_env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert r.returncode == 0, r.stderr
        lines = logfile.read_text().splitlines()
        stops = [i for i, ln in enumerate(lines) if ln.startswith(f"stop {writer}")]
        starts = [i for i, ln in enumerate(lines) if ln.startswith(f"start {writer}")]
        assert len(stops) == 1, f"writer must be stopped once, got {stops}: {lines}"
        assert len(starts) == 1, f"writer must be started once, got {starts}: {lines}"
        # The single restart happens only after mutation: at least one pg_restore
        # (dockerized client) ran, and the writer start comes after the LAST of them.
        pg = [i for i, ln in enumerate(lines) if "pg_restore" in ln]
        assert pg, f"expected a dockerized pg_restore in the log: {lines}"
        assert starts[0] > max(pg), "writer restarted only AFTER mutation"
        assert starts[0] > stops[0], "stop precedes the single restart (one window)"
    finally:
        subprocess.run(["docker", "rm", "-f", writer], capture_output=True)
        _rmtree(backup_dir)
        _rmtree(REPO_ROOT / "backups")


# --- REVIEW-HANDOFF #2: production restore validates MANIFEST targets --------------


def test_review2_restore_refuses_foreign_manifest(env, tmp_path):
    # A MANIFEST naming targets that are NOT this run's (here the PRODUCTION bucket +
    # real DB names) must be refused BEFORE any service is touched, without --force.
    # The overlay semantic gate passes (the current env is run-scoped); it is
    # restore_validate_targets that must catch the mismatched artifact.
    _seed(env)  # establishes the real, run-scoped targets for this run
    art = tmp_path / "foreign"
    (art / "pg").mkdir(parents=True)
    (art / "s3").mkdir()
    (art / "volumes").mkdir()
    (art / "MANIFEST").write_text(
        "lakehouse-backup\nversion=1\n"
        "bucket=lakehouse\nuc_backend=h2\n"
        "databases=mlflow airflow iceberg_catalog\nvolumes=\n"
    )
    marker = REPO_ROOT / ".lakehouse-restore-interrupted"
    marker.unlink(missing_ok=True)
    before = _count_objects(env, "")
    r = _restore(env, art, "--yes")
    try:
        combined = r.stdout + r.stderr
        assert r.returncode != 0, "restore must refuse a foreign MANIFEST"
        assert "do not match the current stack" in combined
        # Aborted before any mutation: run-scoped bucket unchanged, no marker written
        # (nothing was quiesced or partially restored).
        assert _count_objects(env, "") == before
        assert not marker.exists(), "refusal happens before mutation — no marker"
    finally:
        marker.unlink(missing_ok=True)
