"""Checkpoint 1 — test-isolation harness (PR #0, implementation plan Phase 1.5).

Covers the overlay activation contract, the per-base overlays, the standalone
destructive-target validator, and the fail-closed test-harness guard:

    U-42, U-43, U-44, U-45   fail-closed guard (tests/isolation.py)
    U-61                     guard binds to the CURRENT run-id
    U-66a                    standalone target validator, all four classes
    U-51                     per-base overlays leave no bare real resource
    U-55                     overlay activation; default path unchanged bar the
                             allow-listed mlflow->mlflow-server fix
    U-57                     overlays add no services
    U-58                     UC overlay keeps UC on embedded H2
    U-60                     activation is all-or-nothing
    U-64                     overlay isolated-bridge; base networking unchanged
    U-65                     overlay volumes are run-scoped

The compose-config tests shell out to `docker compose config`, which needs the
docker CLI (not the daemon). They skip when it is unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_DIR = REPO_ROOT / "tests" / "overlays"
OVERLAY_SH = REPO_ROOT / "scripts" / "lib" / "overlay.sh"
LAKEHOUSE = REPO_ROOT / "lakehouse"

sys.path.insert(0, str(REPO_ROOT / "tests"))
import isolation  # noqa: E402  (local test helper module)

RUNID = "ci0abcd1"
OTHER_RUNID = "otherrun"

# Base compose service -> the services it declares, and whether each ships with
# network_mode: host on `main` (used by U-64 to prove base networking is untouched).
BASE_SERVICES = {
    "spark41": ["spark-master-41", "spark-worker-41", "spark-connect-41"],
    "kafka": ["zookeeper", "kafka"],
    "unity-catalog": ["unity-catalog", "unity-catalog-ui"],
    "airflow": [
        "airflow-init",
        "airflow-webserver",
        "airflow-scheduler",
        "airflow-triggerer",
    ],
    "mlflow": ["mlflow", "mlflow-agent"],
    "notebooks": ["jupyter"],
}
BASE_IS_HOST_MODE = (
    {  # networking per base — all bridged after PR #13 CP2 (T-1.3/1.4/1.5)
        "spark41": False,
        "kafka": False,
        "unity-catalog": False,  # bridged on lakehouse-network since before CP2
        "airflow": False,
        "mlflow": False,
        "notebooks": False,
    }
)

pytestmark = pytest.mark.merge


def _has_docker_compose() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return True
    except Exception:
        return False


requires_compose = pytest.mark.skipif(
    not _has_docker_compose(), reason="docker compose CLI not available"
)


def _overlay_env(runid: str = RUNID, offset: str | None = None) -> dict:
    env = dict(os.environ)
    env["LAKEHOUSE_TEST_RUN_ID"] = runid
    env["LAKEHOUSE_OVERLAY_DIR"] = str(OVERLAY_DIR)
    env["LAKEHOUSE_RESOURCE_SUFFIX"] = runid
    env["COMPOSE_PROJECT_NAME"] = f"ol-test-{runid}"
    if offset is not None:
        env["LAKEHOUSE_PORT_OFFSET"] = offset
    else:
        env.pop("LAKEHOUSE_PORT_OFFSET", None)
    env.pop("LAKEHOUSE_ENV_FILE", None)
    return env


def _clean_env() -> dict:
    env = dict(os.environ)
    for k in (
        "LAKEHOUSE_TEST_RUN_ID",
        "LAKEHOUSE_OVERLAY_DIR",
        "LAKEHOUSE_RESOURCE_SUFFIX",
        "LAKEHOUSE_PORT_OFFSET",
        "LAKEHOUSE_ENV_FILE",
        "COMPOSE_PROJECT_NAME",
    ):
        env.pop(k, None)
    return env


def _render(svc: str, runid: str = RUNID, offset: str | None = None) -> dict:
    """Return the parsed `docker compose -f base -f overlay config` output."""
    base = f"docker-compose-{svc}.yml"
    overlay = OVERLAY_DIR / f"docker-compose-{svc}.test.yml"
    proc = subprocess.run(
        ["docker", "compose", "-f", base, "-f", str(overlay), "config"],
        cwd=REPO_ROOT,
        env=_overlay_env(runid, offset),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"render failed for {svc}: {proc.stderr}"
    return yaml.safe_load(proc.stdout)


def _service_names(args: list[str]) -> set[str]:
    proc = subprocess.run(
        ["docker", "compose", *args, "config", "--services"],
        cwd=REPO_ROOT,
        env=_overlay_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return {s for s in proc.stdout.splitlines() if s.strip()}


def _resolve(env: dict) -> tuple[int, dict, str]:
    """Run `./lakehouse __resolve`; return (rc, parsed key=value dict, stderr)."""
    proc = subprocess.run(
        [str(LAKEHOUSE), "__resolve"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    parsed = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            parsed[k] = v
    return proc.returncode, parsed, proc.stderr


def _validate_targets(runid: str, active: str, **classes: str) -> int:
    """Invoke overlay_validate_targets in scripts/lib/overlay.sh; return exit code."""
    args = ["overlay_validate_targets", "--runid", runid, "--active", active]
    for cls, value in classes.items():
        args += [f"--{cls}", value]
    quoted = " ".join(f"'{a}'" if " " in a else a for a in args)
    proc = subprocess.run(
        ["bash", "-c", f"source '{OVERLAY_SH}'; {quoted}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode


# ---------------------------------------------------------------------------------
# U-42..U-45, U-61 — the fail-closed guard (tests/isolation.py)
# ---------------------------------------------------------------------------------


class TestFailClosedGuard:
    def setup_method(self):
        os.environ[isolation.RUN_ID_ENV] = RUNID

    def teardown_method(self):
        os.environ.pop(isolation.RUN_ID_ENV, None)

    def test_u42_rejects_real_database_names(self):
        # Guard refuses every real DB; accepts only run-scoped ol_test_<runid>_*.
        for real in (
            "mlflow",
            "airflow",
            "iceberg_catalog",
            "unity_catalog",
            "postgres",
        ):
            with pytest.raises(isolation.IsolationError):
                isolation.assert_test_database(real)
        for good in isolation.expected_databases(RUNID):
            assert isolation.assert_test_database(good) == good

    def test_u43_rejects_real_buckets_and_inner_prefixes(self):
        with pytest.raises(isolation.IsolationError):
            isolation.assert_test_bucket("lakehouse")
        # A prefix INSIDE a real bucket must also be refused.
        with pytest.raises(isolation.IsolationError):
            isolation.assert_test_bucket("lakehouse/warehouse")
        assert isolation.assert_test_bucket(f"ol-test-{RUNID}") == f"ol-test-{RUNID}"

    def test_u44_unset_run_id_skips_never_falls_back(self):
        os.environ.pop(isolation.RUN_ID_ENV, None)
        assert isolation.current_run_id() is None
        # Every destructive helper raises rather than returning a real name.
        for fn, arg in (
            (isolation.assert_test_database, "mlflow"),
            (isolation.assert_test_bucket, "lakehouse"),
            (isolation.assert_test_volume, "open_lakehouse_mlflow-data"),
            (isolation.assert_test_container, "mlflow-server"),
        ):
            with pytest.raises(isolation.IsolationError):
                fn(arg)

    def test_u44_malformed_run_id_also_fails_closed(self):
        os.environ[isolation.RUN_ID_ENV] = "BAD"  # wrong format
        assert isolation.current_run_id() is None
        with pytest.raises(isolation.IsolationError):
            isolation.assert_test_database("ol_test_BAD_mlflow")

    def test_u45_rm_rf_target_must_be_under_tmpdir(self):
        import tempfile

        for forbidden in (
            "/tmp/seaweedfs",  # inside $TMPDIR on Linux, but NOT run-scoped
            "./data",
            str(REPO_ROOT),
            os.path.expanduser("~"),
        ):
            with pytest.raises(isolation.IsolationError):
                isolation.assert_temp_path(forbidden)
        # A bare temp dir is inside $TMPDIR but not run-scoped -> still refused.
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(isolation.IsolationError):
                isolation.assert_temp_path(d)
        # Only a run-scoped dir inside $TMPDIR is permitted.
        scoped = os.path.join(tempfile.gettempdir(), f"ol-test-{RUNID}_scratch")
        os.makedirs(scoped, exist_ok=True)
        try:
            assert isolation.assert_temp_path(scoped) == scoped
        finally:
            os.rmdir(scoped)

    def test_u61_guard_binds_to_current_run_id(self):
        # A resource matching the ol_test_/ol-test- family but a DIFFERENT run-id
        # must be refused — matching the prefix is not sufficient.
        with pytest.raises(isolation.IsolationError):
            isolation.assert_test_database(f"ol_test_{OTHER_RUNID}_mlflow")
        with pytest.raises(isolation.IsolationError):
            isolation.assert_test_bucket(f"ol-test-{OTHER_RUNID}")
        with pytest.raises(isolation.IsolationError):
            isolation.assert_test_volume(f"ol-test-{OTHER_RUNID}_mlflow-data")
        with pytest.raises(isolation.IsolationError):
            isolation.assert_test_container(f"mlflow-server-{OTHER_RUNID}")


# ---------------------------------------------------------------------------------
# U-66a — standalone target validator, parameterized over all FOUR classes
# ---------------------------------------------------------------------------------


class TestTargetValidator:
    GOOD = {
        "databases": f"ol_test_{RUNID}_mlflow ol_test_{RUNID}_airflow",
        "buckets": f"ol-test-{RUNID}",
        "volumes": f"ol-test-{RUNID}_mlflow-data ol-test-{RUNID}_spark-data",
        "containers": f"mlflow-server-{RUNID} unity-catalog-{RUNID}",
    }
    BAD = {
        "databases": "mlflow",
        "buckets": "lakehouse",
        "volumes": "open_lakehouse_mlflow-data",
        "containers": "mlflow-server",
    }

    def test_u66a_all_valid_accepts(self):
        assert _validate_targets(RUNID, "true", **self.GOOD) == 0

    @pytest.mark.parametrize(
        "bad_class", ["databases", "buckets", "volumes", "containers"]
    )
    def test_u66a_one_bad_class_rejects(self, bad_class):
        classes = dict(self.GOOD)
        classes[bad_class] = self.BAD[bad_class]
        assert (
            _validate_targets(RUNID, "true", **classes) == 1
        ), f"validator should reject a non-run-scoped {bad_class}"

    def test_u66a_overlay_inactive_is_unrestricted(self):
        # active=false => production reset semantics: accept anything (no 1.14.3 regression).
        assert _validate_targets(RUNID, "false", **self.BAD) == 0

    def test_u66a_other_runid_rejected(self):
        assert (
            _validate_targets(RUNID, "true", databases=f"ol_test_{OTHER_RUNID}_mlflow")
            == 1
        )


# ---------------------------------------------------------------------------------
# U-55, U-60 — CLI activation contract
# ---------------------------------------------------------------------------------


class TestActivationContract:
    def test_u55_default_path_baseline_when_vars_unset(self):
        rc, res, err = _resolve(_clean_env())
        assert rc == 0, err
        assert res["overlay_active"] == "false"
        # Container names are the base literals, EXCEPT the allow-listed mlflow fix.
        assert res["container.mlflow"] == "mlflow-server"  # T-1.5.11 allow-listed
        assert res["container.spark-master-41"] == "spark-master-41"
        assert res["container.unity-catalog"] == "unity-catalog"
        # Ports are the base literals.
        assert res["port.mlflow"] == "5000"
        assert res["port.unity_catalog"] == "8081"
        assert res["port.spark_connect"] == "15002"
        # Compose files are base-only (no overlay appended).
        assert res["compose.spark41"] == "-f docker-compose-spark41.yml"
        assert res["compose.mlflow"] == "-f docker-compose-mlflow.yml"

    def test_u55_overlay_values_when_vars_set(self):
        rc, res, err = _resolve(_overlay_env(offset="10000"))
        assert rc == 0, err
        assert res["overlay_active"] == "true"
        assert res["container.mlflow"] == f"mlflow-server-{RUNID}"
        assert res["container.spark-master-41"] == f"spark-master-41-{RUNID}"
        assert res["port.mlflow"] == "15000"  # 5000 + 10000
        assert res["port.spark_connect"] == "25002"  # 15002 + 10000
        assert "docker-compose-spark41.test.yml" in res["compose.spark41"]

    def test_u55_port_offset_optional(self):
        # With no offset, published ports equal the base ports even when active.
        rc, res, err = _resolve(_overlay_env(offset=None))
        assert rc == 0, err
        assert res["overlay_active"] == "true"
        assert res["port.mlflow"] == "5000"
        assert res["port.spark_connect"] == "15002"

    @requires_compose
    def test_u60_partial_config_aborts(self):
        # Only the run-id set: the other required vars are missing -> abort non-zero.
        env = _clean_env()
        env["LAKEHOUSE_TEST_RUN_ID"] = RUNID
        rc, _, err = _resolve(env)
        assert rc != 0
        assert "all-or-nothing" in err

    def test_u60_suffix_mismatch_aborts(self):
        env = _overlay_env()
        env["LAKEHOUSE_RESOURCE_SUFFIX"] = OTHER_RUNID  # != run-id
        rc, _, _ = _resolve(env)
        assert rc != 0

    def test_u60_bad_run_id_format_aborts(self):
        env = _overlay_env(runid=RUNID)
        env["LAKEHOUSE_TEST_RUN_ID"] = "BAD"
        env["LAKEHOUSE_RESOURCE_SUFFIX"] = "BAD"
        rc, _, _ = _resolve(env)
        assert rc != 0

    @requires_compose
    def test_u60_missing_overlay_file_aborts(self, tmp_path):
        env = _overlay_env()
        env["LAKEHOUSE_OVERLAY_DIR"] = str(tmp_path)  # empty dir: no overlay files
        rc, _, err = _resolve(env)
        assert rc != 0
        assert "missing" in err.lower()

    def test_u60_never_falls_back_to_default_stack(self):
        # A broken overlay config must NEVER silently resolve to the real stack.
        env = _clean_env()
        env["LAKEHOUSE_OVERLAY_DIR"] = str(OVERLAY_DIR)  # one var only
        rc, res, _ = _resolve(env)
        assert rc != 0
        assert res.get("overlay_active") != "false"  # no fallback output produced


# ---------------------------------------------------------------------------------
# U-51, U-57, U-58, U-64, U-65 — the per-base overlays
# ---------------------------------------------------------------------------------


@requires_compose
class TestPerBaseOverlays:
    FORBIDDEN_BARE = (
        "s3://lakehouse/",
        "@localhost:5432/",
        ":5432/airflow",
        ":5432/mlflow",
    )

    def test_u57_overlays_add_no_services(self):
        for svc, expected in BASE_SERVICES.items():
            base = f"docker-compose-{svc}.yml"
            overlay = str(OVERLAY_DIR / f"docker-compose-{svc}.test.yml")
            base_only = _service_names(["-f", base])
            with_overlay = _service_names(["-f", base, "-f", overlay])
            assert (
                base_only == with_overlay == set(expected)
            ), f"{svc}: overlay changed the service set"

    def test_u51_no_bare_real_resource_reachable(self):
        for svc, services in BASE_SERVICES.items():
            doc = _render(svc)
            for name in services:
                sdef = doc["services"][name]
                # container_name is run-scoped (not a bare base name).
                assert sdef["container_name"].endswith(
                    f"-{RUNID}"
                ), f"{svc}/{name}: container_name not run-scoped: {sdef['container_name']}"
                # No bare real DB/bucket reference survives in the service definition.
                dump = yaml.safe_dump(sdef)
                for bad in self.FORBIDDEN_BARE:
                    assert (
                        bad not in dump
                    ), f"{svc}/{name}: bare real resource {bad!r} present"

    def test_u58_uc_stays_on_embedded_h2(self):
        doc = _render("unity-catalog")
        dump = yaml.safe_dump(doc["services"]["unity-catalog"]).lower()
        for pg_marker in (
            "hibernate",
            "postgres",
            "jdbc",
            "mlflow_pg",
            "unity_catalog",
        ):
            assert (
                pg_marker not in dump
            ), f"UC overlay must not point UC at PostgreSQL (found {pg_marker!r})"

    def test_u64_overlay_bridge_base_networking_unchanged(self):
        # Base networking must be exactly what `main` ships. We assert on the base
        # file's own text — not a rendered/overlaid merge — since that is what proves
        # the overlay changed no base file: host-mode bases still declare host
        # networking and UC declares none.
        for svc in BASE_SERVICES:
            base_text = (REPO_ROOT / f"docker-compose-{svc}.yml").read_text()
            has_host = (
                "network_mode: host" in base_text or 'network_mode: "host"' in base_text
            )
            if BASE_IS_HOST_MODE[svc]:
                assert (
                    has_host
                ), f"{svc}: expected base to still declare network_mode host"
            else:
                assert (
                    "network_mode" not in base_text
                ), f"{svc}: base unexpectedly declares network_mode (UC is bridged)"
        # With the overlay, NO real service is host-mode; each is on a bridge network.
        for svc, services in BASE_SERVICES.items():
            ov_doc = _render(svc)
            for name in services:
                sdef = ov_doc["services"][name]
                assert (
                    sdef.get("network_mode") != "host"
                ), f"{svc}/{name}: overlay left host networking"
                assert (
                    "networks" in sdef and sdef["networks"]
                ), f"{svc}/{name}: overlay service not attached to a network"

    def test_u65_volumes_are_run_scoped(self):
        prefix = f"ol-test-{RUNID}_"
        saw_volume = False
        for svc in BASE_SERVICES:
            doc = _render(svc)
            for vol_key, vol_def in (doc.get("volumes") or {}).items():
                saw_volume = True
                name = (vol_def or {}).get("name", vol_key)
                assert name.startswith(
                    prefix
                ), f"{svc}: volume {name!r} not run-scoped (expected {prefix}*)"
                # No default-project volume leaks in.
                assert not name.startswith(
                    "open_lakehouse_"
                ), f"{svc}: default-project volume {name!r} present under overlay"
        assert saw_volume, "expected at least one named volume across the overlays"
