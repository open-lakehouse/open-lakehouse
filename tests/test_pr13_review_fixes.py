"""Regression tests for the PR #13 review fixes (network + storage foundation).

Each test here would have caught one of the review findings:

  * overlay Kafka advertised-listener names use the INTERNAL/EXTERNAL scheme
    (a bare PLAINTEXT advertised listener no longer matches the base KAFKA_LISTENERS
    and the broker fails to start);
  * the Spark overlay worker/connect commands still export a NON-loopback
    SPARK_LOCAL_IP (dropping it re-introduced advertise-loopback on E-07);
  * the base Spark compose resolves SPARK_LOCAL_IP with the non-loopback filter
    (a bare `hostname -i | cut` can hand back 127.0.1.1 first);
  * `overlay_set_compose_args storage` under an active overlay uses only the base
    file — storage is intentionally unscoped and ships no overlay file;
  * a cold `./lakehouse preflight` does NOT demand live storage;
  * the U-17 UC-properties invariants assert against the committed .example file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_DIR = REPO_ROOT / "tests" / "overlays"
OVERLAY_SH = REPO_ROOT / "scripts" / "lib" / "overlay.sh"
LAKEHOUSE = REPO_ROOT / "lakehouse"

SPARK_BASE = REPO_ROOT / "docker-compose-spark41.yml"
SPARK_OVERLAY = OVERLAY_DIR / "docker-compose-spark41.test.yml"
KAFKA_OVERLAY = OVERLAY_DIR / "docker-compose-kafka.test.yml"

# The non-loopback IP filter ported from terraform/spark-ecs/docker/entrypoint.sh.
NON_LOOPBACK_FILTER = "grep -vE '^127\\.'"

RUNID = "ci0abcd1"

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


def _overlay_env(env_file: str | None = None) -> dict:
    """A full, valid overlay activation env (all-or-nothing contract)."""
    env = dict(os.environ)
    env["LAKEHOUSE_TEST_RUN_ID"] = RUNID
    env["LAKEHOUSE_RESOURCE_SUFFIX"] = RUNID
    env["LAKEHOUSE_OVERLAY_DIR"] = str(OVERLAY_DIR)
    env["COMPOSE_PROJECT_NAME"] = f"ol-test-{RUNID}"
    env.pop("LAKEHOUSE_PORT_OFFSET", None)
    if env_file is not None:
        env["LAKEHOUSE_ENV_FILE"] = env_file
    else:
        env.pop("LAKEHOUSE_ENV_FILE", None)
    return env


# ---------------------------------------------------------------------------------
# Spark SPARK_LOCAL_IP — non-loopback filter on base + overlay (findings #6 / P0.2)
# ---------------------------------------------------------------------------------


class TestSparkLocalIpFilter:
    def test_base_spark_uses_non_loopback_filter_on_all_three(self):
        text = SPARK_BASE.read_text()
        # master + worker + connect each resolve SPARK_LOCAL_IP with the filter.
        assert text.count(NON_LOOPBACK_FILTER) >= 3, (
            "base Spark compose must resolve SPARK_LOCAL_IP with the non-loopback "
            "filter on master, worker, and connect"
        )
        # The stale form that can pick 127.0.1.1 first must be gone.
        assert "hostname -i | cut -d' ' -f1" not in text

    def test_overlay_worker_and_connect_export_non_loopback_ip(self):
        text = SPARK_OVERLAY.read_text()
        # Both the worker and the connect command must export SPARK_LOCAL_IP again.
        assert text.count("export SPARK_LOCAL_IP=") >= 2, (
            "Spark overlay worker/connect commands must export SPARK_LOCAL_IP "
            "(dropping it re-introduces advertise-loopback)"
        )
        assert text.count(NON_LOOPBACK_FILTER) >= 2


# ---------------------------------------------------------------------------------
# Kafka overlay advertised listeners (finding P0.2)
# ---------------------------------------------------------------------------------


class TestKafkaOverlayListeners:
    def test_advertised_listener_uses_internal_scheme_run_scoped(self):
        text = KAFKA_OVERLAY.read_text()
        assert (
            "INTERNAL://kafka-${LAKEHOUSE_RESOURCE_SUFFIX}:9092" in text
        ), "overlay must advertise the INTERNAL listener with the run-scoped name"

    def test_no_stale_bare_plaintext_advertised_listener(self):
        text = KAFKA_OVERLAY.read_text()
        # The base file switched to INTERNAL/EXTERNAL, so a bare PLAINTEXT advertised
        # listener would no longer match KAFKA_LISTENERS and the broker would fail.
        assert "KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://" not in text


# ---------------------------------------------------------------------------------
# Kafka overlay must NOT publish host ports (follow-up bug #2 — MEDIUM)
# ---------------------------------------------------------------------------------


class TestKafkaOverlayResetsPublishedPorts:
    def test_overlay_file_resets_ports_and_drops_external_advertise(self):
        text = KAFKA_OVERLAY.read_text()
        # Both zookeeper (2181:2181) and kafka (9092:19092) reset the base's ports.
        assert (
            text.count("ports: !reset null") >= 2
        ), "both zookeeper and kafka overlays must reset published ports"
        # The advertised-listeners DIRECTIVE (ignore explanatory comments) must be
        # INTERNAL-only — with nothing published, advertising EXTERNAL would be a lie.
        adv = [
            ln.split(":", 1)[1].strip()
            for ln in text.splitlines()
            if ln.strip().startswith("KAFKA_ADVERTISED_LISTENERS:")
        ]
        assert adv, "KAFKA_ADVERTISED_LISTENERS directive missing"
        for value in adv:
            assert (
                "EXTERNAL" not in value
            ), f"overlay must not advertise EXTERNAL: {value}"
            assert value.startswith("INTERNAL://kafka-"), value

    @requires_compose
    def test_render_publishes_no_host_9092_or_2181(self):
        base = "docker-compose-kafka.yml"
        overlay = str(OVERLAY_DIR / "docker-compose-kafka.test.yml")
        proc = subprocess.run(
            ["docker", "compose", "-f", base, "-f", overlay, "config"],
            cwd=REPO_ROOT,
            env=_overlay_env(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, f"kafka overlay render failed: {proc.stderr}"
        doc = yaml.safe_load(proc.stdout)
        published: list[str] = []
        for svc in (doc.get("services") or {}).values():
            for p in svc.get("ports") or []:
                if isinstance(p, dict):
                    if p.get("published") is not None:
                        published.append(str(p["published"]))
                else:
                    published.append(str(p).split(":")[0])
        assert (
            "9092" not in published
        ), f"overlay must not publish host 9092 (hijacks production Kafka): {published}"
        assert (
            "2181" not in published
        ), f"overlay must not publish host 2181 (hijacks production ZK): {published}"


# ---------------------------------------------------------------------------------
# Storage Postgres/SeaweedFS containers stay UNSCOPED under overlay (bug #1 — HIGH)
# ---------------------------------------------------------------------------------


def _eval_after_sourcing_lakehouse(exprs: dict[str, str]) -> dict[str, str]:
    """Source ./lakehouse under a valid ACTIVE overlay (its dispatch runs the
    harmless `help`), then echo each requested shell expression. The overlay is
    active, so resolve_container_name WOULD run-scope — proving the storage
    helpers stay unscoped is the point of the test."""
    lines = "".join(f'echo "{k}=$({expr})"\n' for k, expr in exprs.items())
    script = "{ source ./lakehouse; } >/dev/null 2>&1\n" + lines
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        env=_overlay_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, _, val = line.partition("=")
            out[k] = val
    return out


class TestStoragePostgresContainerUnscoped:
    def test_storage_containers_stay_unscoped_under_active_overlay(self):
        res = _eval_after_sourcing_lakehouse(
            {
                "overlay_active": "echo ${OVERLAY_ACTIVE:-unset}",
                "storage_pg": "get_storage_postgres_container",
                "storage_s3": "get_storage_seaweedfs_container",
                "scoped_pg": "resolve_container_name postgres",
            }
        )
        # The overlay really is active, so resolve_container_name run-scopes...
        assert res.get("overlay_active") == "true", res
        assert res.get("scoped_pg") == f"postgres-{RUNID}", res
        # ...but the storage helpers must stay the FIXED, unscoped names, so
        # `docker exec` / `docker logs` hit the container that actually exists.
        assert res.get("storage_pg") == "postgres", res
        assert res.get("storage_s3") == "seaweedfs", res

    def test_cli_never_run_scopes_the_storage_containers(self):
        text = LAKEHOUSE.read_text()
        # No storage docker exec/logs/ps may go through resolve_container_name.
        assert "resolve_container_name postgres" not in text
        assert "resolve_container_name seaweedfs" not in text
        # wait_for_postgres_ready (the pg_isready gate) uses the unscoped helper.
        assert "ctr=$(get_storage_postgres_container)" in text


# ---------------------------------------------------------------------------------
# Storage is unscoped: overlay_set_compose_args storage needs no overlay file (P0.2)
# ---------------------------------------------------------------------------------


def _compose_args(svc: str, overlay_dir: Path) -> tuple[int, list[str], str]:
    """Source overlay.sh with an ACTIVE overlay and return
    (rc, OVERLAY_COMPOSE_ARGS, stderr) for `overlay_set_compose_args <svc>`."""
    script = (
        f"source '{OVERLAY_SH}'; "
        "OVERLAY_ACTIVE=true; "
        f"LAKEHOUSE_TEST_RUN_ID={RUNID}; "
        f"LAKEHOUSE_RESOURCE_SUFFIX={RUNID}; "
        f"LAKEHOUSE_OVERLAY_DIR='{overlay_dir}'; "
        f"overlay_set_compose_args {svc}; rc=$?; "
        'echo "RC=$rc"; printf "ARG:%s\\n" "${OVERLAY_COMPOSE_ARGS[@]}"'
    )
    proc = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=60
    )
    rc = 1
    args: list[str] = []
    for line in proc.stdout.splitlines():
        if line.startswith("RC="):
            rc = int(line[3:])
        elif line.startswith("ARG:"):
            args.append(line[4:])
    return rc, args, proc.stderr


class TestStorageUnscopedUnderOverlay:
    def test_storage_uses_base_file_only_even_with_empty_overlay_dir(self, tmp_path):
        # tmp_path has NO docker-compose-storage.test.yml — the special-case must
        # still succeed with just the base file.
        rc, args, err = _compose_args("storage", tmp_path)
        assert rc == 0, f"storage under overlay should succeed; stderr={err}"
        assert args == ["-f", "docker-compose-storage.yml"], args
        assert "missing" not in err.lower()

    def test_storage_special_case_holds_against_the_real_overlay_dir(self):
        # Even when a populated overlay dir exists, storage must NOT pick up an
        # overlay file (there is none, and it must never require one).
        rc, args, _ = _compose_args("storage", OVERLAY_DIR)
        assert rc == 0
        assert args == ["-f", "docker-compose-storage.yml"], args

    def test_non_storage_service_still_requires_its_overlay_file(self, tmp_path):
        # Control: a scoped service under an active overlay with an empty overlay
        # dir must still fail — proving the special-case is specific to storage.
        rc, _, err = _compose_args("mlflow", tmp_path)
        assert rc != 0
        assert "missing" in err.lower()


# ---------------------------------------------------------------------------------
# Cold preflight must not demand live storage (finding #7 / Bugbot #157)
# ---------------------------------------------------------------------------------


class TestColdPreflight:
    def test_preflight_passes_when_storage_is_down(self, tmp_path):
        # Point storage at definitely-closed ports and run a cold preflight. It must
        # report "not running yet" and STILL exit 0 (storage is what `start` brings
        # up — a cold preflight must not require it already be live).
        env_file = tmp_path / "cold.env"
        env_file.write_text(
            "POSTGRES_HOST=localhost\n"
            "POSTGRES_PORT=59991\n"
            "POSTGRES_USER=postgres\n"
            "POSTGRES_PASSWORD=x\n"
            "S3_ENDPOINT=http://localhost:59992\n"
        )
        # LAKEHOUSE_ENV_FILE replaces .env, but setting it trips the all-or-nothing
        # overlay contract, so supply a full, valid overlay activation set too.
        env = dict(os.environ)
        env.update(
            {
                "LAKEHOUSE_TEST_RUN_ID": RUNID,
                "LAKEHOUSE_RESOURCE_SUFFIX": RUNID,
                "LAKEHOUSE_OVERLAY_DIR": str(OVERLAY_DIR),
                "LAKEHOUSE_ENV_FILE": str(env_file),
            }
        )
        env.pop("LAKEHOUSE_PORT_OFFSET", None)
        proc = subprocess.run(
            [str(LAKEHOUSE), "preflight"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            proc.returncode == 0
        ), f"cold preflight must pass\n{proc.stdout}\n{proc.stderr}"
        assert "not running yet" in proc.stdout
        # And it must not have hard-failed the storage probes.
        assert "PostgreSQL connection failed" not in proc.stdout


# ---------------------------------------------------------------------------------
# U-17 asserts against the committed .example (finding #3)
# ---------------------------------------------------------------------------------


class TestUcPropertiesExampleCommitted:
    def test_example_is_committed_and_gitignored_live_file_is_not(self):
        example = REPO_ROOT / "config" / "unity-catalog" / "server.properties.example"
        assert example.exists(), "server.properties.example must be committed for CI"
        # The live file is developer-local (gitignored); assert git ignores it so the
        # U-17 checks never depend on a file a fresh clone lacks.
        proc = subprocess.run(
            ["git", "check-ignore", "config/unity-catalog/server.properties"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, "server.properties should be gitignored"


# ---------------------------------------------------------------------------------
# Backup/restore must never touch the live Composed storage volumes (/code-review
# HIGH: restore_apply wiping postgres-data / seaweedfs-data under the running store).
# ---------------------------------------------------------------------------------

import re  # noqa: E402


class TestBackupRestoreSkipStorageVolumes:
    """postgres-data / seaweedfs-data hold the metastore + object store; their
    services stay live during backup/restore, and their content is captured by
    pg_dump + s3 sync. Volume-archiving or volume-restoring them corrupts the running
    store, so both paths must skip every "never"-mode volume (the guard reset honors).
    """

    TEXT = LAKEHOUSE.read_text()

    def _body(self, name: str) -> str:
        m = re.search(rf"\n{name}\(\) \{{(.*?)\n\}}\n", self.TEXT, re.S)
        assert m, f"function {name}() not found in lakehouse"
        return m.group(1)

    def test_reset_volume_mode_marks_storage_never(self):
        body = self._body("reset_volume_mode")
        for vol in ("postgres-data", "seaweedfs-data"):
            assert re.search(
                rf'{re.escape(vol)}\)\s*echo "never"', body
            ), f"{vol} must map to 'never' so backup/restore skip it"

    def test_backup_skips_never_mode_volumes(self):
        body = self._body("backup_take_snapshot")
        # The volume loop must consult reset_volume_mode and skip "never" volumes
        # BEFORE volume_backup, so a "never" volume never lands in the MANIFEST.
        assert (
            'reset_volume_mode "$v"' in body
        ), "backup must check reset_volume_mode per volume"
        assert (
            '"never"' in body and "continue" in body
        ), "backup_take_snapshot must skip never-mode volumes before volume_backup"

    def test_restore_skips_never_mode_volumes(self):
        body = self._body("restore_apply")
        # The MANIFEST stores EFFECTIVE (project-prefixed) volume names, so restore must
        # compare against reset_effective_volume of the never-mode volumes (not the base
        # names reset_volume_mode keys on) before volume_restore.
        assert (
            "reset_effective_volume" in body and '"never"' in body
        ), "restore_apply must skip never-mode volumes (by effective name) before volume_restore"
        assert (
            "volume_restore" in body
        ), "sanity: restore_apply still restores non-storage volumes"


# ---------------------------------------------------------------------------------
# Notebooks lifecycle: `stop notebooks` existed but `start notebooks` did not, and
# `reset` stopped Jupyter without restarting it (/code-review findings).
# ---------------------------------------------------------------------------------


class TestNotebooksLifecycle:
    TEXT = LAKEHOUSE.read_text()

    def _body(self, name: str) -> str:
        m = re.search(rf"\n{name}\(\) \{{(.*?)\n\}}\n", self.TEXT, re.S)
        assert m, f"function {name}() not found in lakehouse"
        return m.group(1)

    def test_cmd_start_accepts_notebooks(self):
        body = self._body("cmd_start")
        assert re.search(
            r"\n\s+notebooks\)\s*\n", body
        ), "cmd_start needs a notebooks) arm"
        assert re.search(
            r"\|mlflow\|notebooks[|)]", body
        ), "notebooks must be in the cmd_start valid-set"
        assert re.search(
            r"notebooks\|[\w|-]*all\]", body
        ), "the start usage string should list notebooks"

    def test_start_notebooks_is_optin_not_in_all(self):
        body = self._body("cmd_start")
        # notebooks must NOT be bundled into a `start all` case arm (opt-in only).
        assert (
            "notebooks|all)" not in body and "all|notebooks)" not in body
        ), "notebooks must be opt-in, not part of `start all`"

    def test_reset_running_services_probes_jupyter(self):
        body = self._body("reset_running_services")
        assert (
            "resolve_container_name jupyter" in body
        ), "reset must detect a running Jupyter so it can restart it"
        assert (
            'up="$up notebooks"' in body
        ), "reset_running_services must add 'notebooks' to the restart set"


# ---------------------------------------------------------------------------------
# The reset/backup dockerized aws-cli must be version-pinned (not :latest), matching
# init-storage.sh / demos/_lib and the CLAUDE.md pin (/code-review finding).
# ---------------------------------------------------------------------------------


class TestAwsCliPinned:
    TEXT = LAKEHOUSE.read_text()

    def test_no_unpinned_aws_cli_latest(self):
        assert (
            "amazon/aws-cli:latest" not in self.TEXT
        ), "the reset/backup dockerized aws-cli must be pinned (2.24.6), not :latest"

    def test_aws_cli_pinned_and_overridable(self):
        # aws_s3 and s3_sync both default to 2.24.6, still overridable via the env var.
        assert (
            self.TEXT.count("LAKEHOUSE_AWSCLI_IMAGE:-amazon/aws-cli:2.24.6") >= 2
        ), "aws_s3 and s3_sync should default to amazon/aws-cli:2.24.6 (env-overridable)"
