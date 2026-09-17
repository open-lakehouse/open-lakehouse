"""Integration tests for `./lakehouse doctor` (PR #0, Checkpoint 5).

    I-33  doctor detects both orphan directions: an S3 prefix with no UC entry, and
          a UC row whose storage_location resolves to nothing.
    I-36  doctor classifies orphans into FOUR classes (plan 1.19.1). The fixture
          MANUFACTURES each class (plan 1.17.7):
            - recoverable Delta   : a Delta prefix (has _delta_log/) with no UC row
            - doubtful Iceberg    : an Iceberg layout in S3 (metadata/*.metadata.json),
                                    NEVER via the UC API which rejects ICEBERG (1.18.5)
            - unrecoverable MLflow: an artifact whose run record is absent
            - dangling catalog    : a UC row whose valid URI resolves to zero objects
          Negatives: a registered Delta prefix, an artifact whose run record exists,
          and a healthy run that never logged an artifact are all unflagged.

FAIL-CLOSED: skips unless LAKEHOUSE_TEST_RUN_ID is set (isolation guard), Docker is
available, and host PostgreSQL + SeaweedFS are reachable. Every resource is run-scoped
(ol_test_<runid>_* / ol-test-<runid>); the real stack is never touched.

NOTE: the UC image ships sample `unity.default.*` tables whose locations resolve to
zero objects in a test bucket, so they legitimately appear as dangling. Assertions
therefore check for the MANUFACTURED entries specifically, never exclusivity/counts.
"""

from __future__ import annotations

import os
import re
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
UC_IMAGE = os.environ.get("LAKEHOUSE_UC_IMAGE", "unitycatalog/unitycatalog:v0.5.0")
PY_IMAGE = os.environ.get("LAKEHOUSE_HTTP_IMAGE", "python:3-alpine")


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


def _put(bucket: str, key: str, body: str = "x", tries: int = 6) -> None:
    # Bounded retry: local SeaweedFS can return a transient InternalError — e.g. if
    # the host sleeps mid-run (a laptop lid-close) — without this a transient hiccup
    # fails class manufacture.
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
                f"s3://{bucket}/{key}",
            ],
            input=body,
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
    raise AssertionError(f"seeding {key} failed after {tries} tries: {last.stderr}")


def _which(x: str) -> bool:
    return shutil.which(x) is not None


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


@pytest.fixture(scope="module")
def env():
    rid = isolation.current_run_id()
    if rid is None:
        pytest.skip(
            "LAKEHOUSE_TEST_RUN_ID unset/invalid — doctor tests skip (fail-closed)"
        )
    if not (_docker_ok() and _which("aws") and _which("docker")):
        pytest.skip("Docker/aws not available")
    if _psql("postgres", "SELECT 1", tuples=True).returncode != 0:
        pytest.skip("host PostgreSQL not reachable")
    if _aws("ls").returncode != 0:
        pytest.skip("host SeaweedFS/S3 not reachable")

    bucket = f"ol-test-{rid}"
    mldb = f"ol_test_{rid}_mlflow"
    uc = f"unity-catalog-{rid}"
    envfile = REPO_ROOT / ".smoke" / f"env-doctor-{rid}"
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
    _aws("mb", f"s3://{bucket}")
    yield {"rid": rid, "overlay": overlay, "bucket": bucket, "mldb": mldb, "uc": uc}

    # teardown
    subprocess.run(["docker", "rm", "-f", uc], capture_output=True)
    _psql("postgres", f'DROP DATABASE IF EXISTS "{mldb}"')
    _aws("rb", f"s3://{bucket}", "--force")
    for v in subprocess.run(
        ["docker", "volume", "ls", "-q"], capture_output=True, text=True
    ).stdout.split():
        if v.startswith(f"{bucket}_"):
            subprocess.run(["docker", "volume", "rm", v], capture_output=True)
    envfile.unlink(missing_ok=True)


# --- UC helpers (real run-scoped container, embedded H2) --------------------------


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


def _uc_boot(env) -> bool:
    subprocess.run(["docker", "rm", "-f", env["uc"]], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            env["uc"],
            "-e",
            "JAVA_OPTS=-Xmx1g",
            UC_IMAGE,
        ],
        capture_output=True,
        check=True,
    )
    probe = (
        "import urllib.request;urllib.request.urlopen("
        "'http://localhost:8080/api/2.1/unity-catalog/catalogs', timeout=3)"
    )
    for _ in range(40):
        if _uc_py(env, probe).returncode == 0:
            return True
        time.sleep(3)
    return False


def _uc_register(env, cat, sch, tbl, location) -> None:
    """Register an EXTERNAL Delta table at `location` (idempotent on catalog/schema)."""
    script = f"""
import json, urllib.request
api = "http://localhost:8080/api/2.1/unity-catalog"
def post(path, body, ok_conflict=True):
    r = urllib.request.Request(api + path, data=json.dumps(body).encode(),
        headers={{"Content-Type": "application/json"}}, method="POST")
    try:
        urllib.request.urlopen(r, timeout=10)
    except urllib.error.HTTPError as e:
        if not (ok_conflict and e.code in (400, 409)):
            raise
# UC 0.5.0 validates the column type descriptor — an empty type_json 400s.
tj = json.dumps({{"name": "id", "type": "integer", "nullable": True, "metadata": {{}}}})
post("/catalogs", {{"name": "{cat}"}})
post("/schemas", {{"name": "{sch}", "catalog_name": "{cat}"}})
post("/tables", {{"name": "{tbl}", "catalog_name": "{cat}", "schema_name": "{sch}",
    "table_type": "EXTERNAL", "data_source_format": "DELTA",
    "storage_location": "{location}",
    "columns": [{{"name": "id", "type_text": "int", "type_name": "INT",
                 "type_json": tj, "position": 0, "nullable": True}}]}},
    ok_conflict=False)
print("ok")
"""
    r = _uc_py(env, script)
    assert r.stdout.strip().endswith("ok"), f"UC register failed: {r.stdout} {r.stderr}"


# --- doctor runner + output parser ------------------------------------------------


def _doctor(env) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(LAKEHOUSE), "doctor"],
        cwd=REPO_ROOT,
        env=env["overlay"],
        capture_output=True,
        text=True,
        timeout=120,
    )


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _sections(stdout: str) -> dict[str, list[str]]:
    """Parse doctor output into {class: [item, ...]} from the `[class]` headers and
    the `  - item` lines beneath each. Strips ANSI colour codes first — doctor always
    colourises (no TTY check), so the `[class]` header is escape-prefixed."""
    out: dict[str, list[str]] = {}
    cur = None
    for line in stdout.splitlines():
        s = _ANSI.sub("", line).strip()
        if s.startswith("[") and "]" in s:
            cur = s[1 : s.index("]")]
            out.setdefault(cur, [])
        elif s.startswith("- ") and cur:
            out[cur].append(s[2:].strip())
    return out


# --- I-33 -------------------------------------------------------------------------


def test_i33_detects_both_directions(env):
    if not _uc_boot(env):
        pytest.skip("run-scoped Unity Catalog did not become ready")
    # (a) an S3 Delta prefix with NO UC entry
    _put(env["bucket"], "warehouse/lonely/_delta_log/00000000000000000000.json")
    _put(env["bucket"], "warehouse/lonely/part-0.parquet")
    # (b) a UC row whose valid URI resolves to ZERO objects (plan 1.16.8; the
    # empty-location branch is unit-covered by U-34)
    _uc_register(
        env, "docz", "s", "ghost", f"s3://{env['bucket']}/warehouse/ghost-empty"
    )

    r = _doctor(env)
    assert r.returncode == 0, r.stderr
    sec = _sections(r.stdout)
    assert any(
        "warehouse/lonely" in x for x in sec.get("recoverable-delta", [])
    ), "an S3 prefix with no UC entry must be reported"
    assert "docz.s.ghost" in sec.get(
        "dangling-catalog-entry", []
    ), "a UC row resolving to zero objects must be reported as dangling"


# --- I-36 -------------------------------------------------------------------------


def test_i36_four_classes_with_negatives(env):
    if not _uc_boot(env):
        pytest.skip("run-scoped Unity Catalog did not become ready")
    b = env["bucket"]

    # (1) recoverable Delta: prefix with _delta_log/, no UC row
    _put(b, "warehouse/reco/_delta_log/00000000000000000000.json")
    _put(b, "warehouse/reco/part-0.parquet")
    # (2) doubtful Iceberg: manufactured directly in S3, never via the UC API
    _put(b, "warehouse/ice/metadata/v1.metadata.json")
    _put(b, "warehouse/ice/data/d-0.parquet")
    # (3) unrecoverable MLflow: an artifact whose run record is ABSENT. Seed a runs
    # table holding a DIFFERENT (known) run so the table exists and is decidable.
    assert (
        _psql(
            "postgres", f'CREATE DATABASE "{env["mldb"]}" OWNER "{PG_USER}"'
        ).returncode
        == 0
    )
    _psql(
        env["mldb"],
        "CREATE TABLE runs(run_uuid varchar); "
        "INSERT INTO runs VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')",
    )
    gone = "b" * 32
    _put(b, f"mlflow-artifacts/1/{gone}/artifacts/model.txt")
    # (4) dangling catalog entry: a UC row whose URI resolves to zero objects
    _uc_register(env, "docz", "s", "empty", f"s3://{b}/warehouse/empty-prefix")

    # Negatives:
    # - a REGISTERED Delta prefix (populated) must NOT be recoverable
    _put(b, "warehouse/kept/_delta_log/00000000000000000000.json")
    _put(b, "warehouse/kept/part-0.parquet")
    _uc_register(env, "docz", "s", "kept", f"s3://{b}/warehouse/kept")
    # - an artifact whose run record EXISTS must NOT be unrecoverable
    known = "a" * 32
    _put(b, f"mlflow-artifacts/1/{known}/artifacts/ok.txt")
    # - a healthy run that never logged an artifact (row only, no S3 object) — nothing
    #   to flag; asserted implicitly by the unrecoverable set below.
    _psql(env["mldb"], "INSERT INTO runs VALUES ('cccccccccccccccccccccccccccccccc')")

    r = _doctor(env)
    assert r.returncode == 0, r.stderr
    sec = _sections(r.stdout)

    # All four classes present with the manufactured entries.
    assert any("warehouse/reco" in x for x in sec.get("recoverable-delta", []))
    assert any("warehouse/ice" in x for x in sec.get("doubtful-iceberg", []))
    assert any(gone in x for x in sec.get("unrecoverable-mlflow", []))
    assert "docz.s.empty" in sec.get("dangling-catalog-entry", [])

    # Negatives.
    assert not any(
        "warehouse/kept" in x for x in sec.get("recoverable-delta", [])
    ), "a registered Delta prefix must not be flagged recoverable"
    assert not any(
        known in x for x in sec.get("unrecoverable-mlflow", [])
    ), "an artifact whose run record exists must not be flagged unrecoverable"
    # The healthy artifact-free run 'cccc...' has no artifact object, so it cannot
    # appear anywhere (U-62). Confirm no class references it.
    assert not any("cccccccc" in x for items in sec.values() for x in items)
