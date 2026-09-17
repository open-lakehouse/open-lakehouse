"""Reset skeleton unit tests (PR #0, Phase 1.5, Checkpoint 2).

    U-29  every stateful target is assigned or explicitly exempt
    U-30  `reset --dry-run` destroys nothing (and lists targets)
    U-46  UC backend detected from effective CONFIG, not volume topology
    U-47  reset target matrix — four distinct target sets
    U-52  flag validation
    U-53  named volumes are assigned to a reset mode (or never-destroy)
    U-54  production reset is NOT name-pattern restricted
    U-31  backup/restore argument contract (Checkpoint 4)
    U-48  backup covers PostgreSQL — pg_dump per DB + S3 sync, not volume-only (CP4)
    U-63  backup prints a ready-to-paste `restore --from` command (CP4)
    U-34  orphan classifier is a distinct code path — FOUR classes (Checkpoint 5)
    U-62  artifact-free MLflow runs are never flagged (Checkpoint 5)

All unit-level: static scans of `lakehouse` + running `reset --dry-run` (which
touches nothing). No Docker required.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LAKEHOUSE = REPO_ROOT / "lakehouse"
TEXT = LAKEHOUSE.read_text()


def _func_body(name: str) -> str:
    m = re.search(rf"^{re.escape(name)}\(\) \{{\n(.*?)^\}}", TEXT, re.M | re.S)
    assert m, f"function {name}() not found"
    return m.group(1)


def _run(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(LAKEHOUSE), *args],
        cwd=REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _plan(mode: str, *extra: str) -> list[dict]:
    """Run `reset <mode> --dry-run` and parse the PLAN tokens into dicts."""
    r = _run("reset", mode, *extra, "--dry-run")
    assert r.returncode == 0, f"dry-run failed: {r.stderr}"
    rows = []
    for line in r.stdout.splitlines():
        if line.startswith("PLAN "):
            rows.append(dict(kv.split("=", 1) for kv in line.split()[1:]))
    return rows


def _detect_uc_backend(props_path: str) -> str:
    """Invoke the detect_uc_backend bash function against a props file."""
    body = re.search(r"(^detect_uc_backend\(\) \{.*?^\})", TEXT, re.M | re.S).group(1)
    script = f'PROJECT_ROOT={REPO_ROOT}\n{body}\ndetect_uc_backend "{props_path}"'
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30
    ).stdout.strip()


def _dbname_ok(name: str) -> bool:
    """Return True iff pg_assert_valid_dbname (extracted from lakehouse) accepts name."""
    body = re.search(
        r"(^pg_assert_valid_dbname\(\) \{.*?^\})", TEXT, re.M | re.S
    ).group(1)
    script = f'RED=""; NC=""\n{body}\npg_assert_valid_dbname "$1"'
    return (
        subprocess.run(
            ["bash", "-c", script, "_", name],
            capture_output=True,
            text=True,
            timeout=30,
        ).returncode
        == 0
    )


# --- U-46 ------------------------------------------------------------------------


class TestU46UCBackendDetection:
    def test_commented_pg_block_is_h2(self):
        with tempfile.NamedTemporaryFile("w", suffix=".properties", delete=False) as f:
            f.write("server.port=8080\n")
            f.write(
                "# hibernate.connection.url=jdbc:postgresql://h/5432/unity_catalog\n"
            )
            p = f.name
        assert _detect_uc_backend(p) == "h2"

    def test_uncommented_pg_url_is_postgresql(self):
        with tempfile.NamedTemporaryFile("w", suffix=".properties", delete=False) as f:
            f.write(
                "hibernate.connection.url=jdbc:postgresql://localhost:5432/unity_catalog\n"
            )
            p = f.name
        assert _detect_uc_backend(p) == "postgresql:unity_catalog"

    def test_missing_config_defaults_to_h2(self):
        assert _detect_uc_backend("/nonexistent/server.properties") == "h2"

    def test_db_name_with_hyphen_is_not_truncated(self):
        # Regression: the trailing-junk trim must preserve '-' and '.' (legal in a
        # PostgreSQL db name); it previously truncated "iceberg-catalog" -> "iceberg".
        with tempfile.NamedTemporaryFile("w", suffix=".properties", delete=False) as f:
            f.write(
                "hibernate.connection.url=jdbc:postgresql://h:5432/iceberg-catalog\n"
            )
            p = f.name
        assert _detect_uc_backend(p) == "postgresql:iceberg-catalog"

    def test_db_name_strips_jdbc_params_and_whitespace(self):
        with tempfile.NamedTemporaryFile("w", suffix=".properties", delete=False) as f:
            f.write(
                "hibernate.connection.url=jdbc:postgresql://h:5432/unity_catalog?ssl=true\n"
            )
            p = f.name
        assert _detect_uc_backend(p) == "postgresql:unity_catalog"

    def test_detector_reads_config_not_volume_topology(self):
        body = _func_body("detect_uc_backend")
        # It must key off the properties file, never volume mount state.
        assert "server.properties" in body
        assert "uc-data" not in body and "volume" not in body.lower()

    def test_never_hardcodes_nonexistent_unitycatalog_db(self):
        assert "unitycatalog" not in _func_body("detect_uc_backend").replace(
            "unity_catalog", ""
        )


# --- REVIEW-HANDOFF #3: DB-name allowlist before SQL interpolation ---------------


class TestReview3DbNameSanitization:
    def test_legit_names_accepted(self):
        for name in (
            "mlflow",
            "airflow",
            "iceberg_catalog",
            "ol_test_run1234_mlflow",
            "iceberg-catalog",  # hyphen (finding-4 fix) stays legal
            "unity.catalog",  # dot legal
        ):
            assert _dbname_ok(name), f"{name!r} should be accepted"

    def test_injection_and_metachars_rejected(self):
        for name in (
            "",  # empty
            "x'; DROP DATABASE prod; --",  # quote/semicolon breakout
            'x" ; --',  # double-quote breakout
            "a b",  # space
            "db`whoami`",  # backtick
            "db$(id)",  # command sub
            "db;drop",  # semicolon
            "db\\x",  # backslash
        ):
            assert not _dbname_ok(name), f"{name!r} must be rejected"

    def test_drop_and_restore_guard_on_the_validator(self):
        # Both SQL-interpolating helpers must call the validator first.
        for fn in ("pg_drop_recreate", "pg_restore_db"):
            body = _func_body(fn)
            assert "pg_assert_valid_dbname" in body, f"{fn} must validate the db name"
            assert body.index("pg_assert_valid_dbname") < (
                body.index("datname=") if "datname=" in body else len(body)
            ), f"{fn} must validate BEFORE interpolating the name into SQL"


# --- REVIEW-HANDOFF #7 & #8: quiesce verification + S3-delete post-condition ------


class TestReviewLowQuiesceAndS3:
    def test_reset_stop_services_verifies_containers_down(self):
        # #7: after stopping, it must confirm the containers are actually not running.
        body = _func_body("reset_stop_services")
        assert "is_container_running" in body
        assert "cmd_stop" in body
        assert body.index("cmd_stop") < body.index(
            "is_container_running"
        ), "must stop THEN verify"

    def test_reset_execute_aborts_before_deletion_on_quiesce_failure(self):
        # #7: an incomplete quiesce must abort BEFORE any deletion.
        body = _func_body("reset_execute")
        q = body.index("reset_quiesce")
        d = body.index("reset_do_deletions")
        assert "if ! reset_quiesce" in body, "quiesce failure must be checked"
        assert q < d, "quiesce check precedes deletions"

    def test_backup_and_restore_abort_on_incomplete_quiesce(self):
        # #7: backup/restore must not snapshot/mutate if a writer stayed up.
        for fn in ("cmd_backup", "cmd_restore"):
            body = _func_body(fn)
            assert (
                "if ! backup_quiesce_writers" in body
            ), f"{fn} must abort on incomplete quiesce"

    def test_backup_quiesce_writers_reports_failure(self):
        body = _func_body("backup_quiesce_writers")
        # stops, then re-checks is_container_running and returns rc.
        assert body.count("is_container_running") >= 2, "must verify post-stop"
        assert 'return "$rc"' in body

    def test_data_delete_has_s3_empty_post_condition(self):
        # #8: after rm, verify the prefixes are actually empty (permission errors that
        # leave objects must fail-stop, not silently succeed).
        body = _func_body("reset_delete_data")
        assert "remain" in body, "must re-check object count after delete"
        assert body.index("aws_s3 rm") < body.index(
            "remain"
        ), "post-condition runs after the delete"


# --- U-52 ------------------------------------------------------------------------


class TestU52FlagValidation:
    def test_requires_exactly_one_mode(self):
        assert _run("reset", "--dry-run").returncode == 2
        assert _run("reset", "--data", "--metadata", "--dry-run").returncode == 2
        assert _run("reset", "--data", "--all", "--dry-run").returncode == 2

    def test_keep_mlflow_only_with_metadata(self):
        assert _run("reset", "--all", "--keep-mlflow", "--dry-run").returncode == 2
        assert _run("reset", "--data", "--keep-mlflow", "--dry-run").returncode == 2
        assert _run("reset", "--metadata", "--keep-mlflow", "--dry-run").returncode == 0

    def test_valid_single_modes_accepted(self):
        for mode in ("--data", "--metadata", "--all"):
            assert _run("reset", mode, "--dry-run").returncode == 0


# --- U-30 ------------------------------------------------------------------------


class TestU30DryRunInert:
    def test_dry_run_lists_targets_and_makes_no_changes(self):
        r = _run("reset", "--all", "--dry-run")
        assert r.returncode == 0
        assert "DRY RUN" in r.stdout
        assert "No changes made (dry-run)." in r.stdout
        assert any(line.startswith("PLAN ") for line in r.stdout.splitlines())

    def test_dry_run_code_path_issues_no_destructive_ops(self):
        # The enumeration body must contain no docker/psql/rm destructive verbs.
        body = _func_body("reset_emit_plan")
        for forbidden in ("docker ", "psql", "rm -rf", "DROP DATABASE", "volume rm"):
            assert forbidden not in body, f"dry-run path contains {forbidden!r}"

    def test_dry_run_returns_before_destructive_execute(self):
        # cmd_reset returns from the --dry-run branch before reset_execute is called.
        body = _func_body("cmd_reset")
        dry_idx = body.index('dry_run" = true')
        exec_idx = body.index("reset_execute")
        assert dry_idx < exec_idx, "dry-run branch must precede reset_execute"

    def test_plan_does_not_advertise_unimplemented_kafka_reset(self):
        # REVIEW-HANDOFF #4: the engine quiesces Kafka but deletes no topics/
        # checkpoints, so the plan must NOT claim a kafka reset (--dry-run must not
        # lie). Deferred to a follow-up PR.
        for mode in ("--data", "--all"):
            rows = _plan(mode)
            assert not any(
                r["target"] == "kafka" for r in rows
            ), f"{mode} plan must not advertise an unimplemented kafka reset"


# --- U-47 ------------------------------------------------------------------------


class TestU47TargetMatrix:
    def _names(self, rows, cls, action=None):
        return {
            r["name"]
            for r in rows
            if r["target"] == cls and (action is None or r.get("action") == action)
        }

    def test_four_modes_are_distinct(self):
        sigs = set()
        for mode in ("--data", "--metadata", "--all"):
            rows = _plan(mode)
            sigs.add(frozenset((r["target"], r["name"], r["action"]) for r in rows))
        rows_km = _plan("--metadata", "--keep-mlflow")
        sigs.add(frozenset((r["target"], r["name"], r["action"]) for r in rows_km))
        assert len(sigs) == 4, "the four modes must produce four distinct plans"

    def test_data_deletes_objects_and_referencing_rows_not_databases(self):
        rows = _plan("--data")
        assert self._names(rows, "s3", "delete")  # objects deleted
        assert "iceberg_catalog-rows" in self._names(rows, "rows", "clear")
        assert "uc-table-registrations" in self._names(rows, "rows", "clear")
        assert "mlflow-run-records" in self._names(rows, "rows", "clear")
        assert not self._names(rows, "database"), "--data must not drop databases"

    def test_metadata_resets_dbs_incl_iceberg_not_objects(self):
        rows = _plan("--metadata")
        dbs = self._names(rows, "database", "drop-recreate")
        assert {"airflow", "iceberg_catalog", "mlflow"} <= dbs
        assert not self._names(rows, "s3"), "--metadata must not delete S3 objects"

    def test_keep_mlflow_excludes_mlflow_db_and_preserves_volume(self):
        rows = _plan("--metadata", "--keep-mlflow")
        assert "mlflow" not in self._names(rows, "database")
        assert {"airflow", "iceberg_catalog"} <= self._names(rows, "database")
        preserved = self._names(rows, "volume", "preserve")
        assert "mlflow-data" in preserved

    def test_all_is_both(self):
        rows = _plan("--all")
        assert self._names(rows, "s3", "delete")
        assert {"airflow", "iceberg_catalog", "mlflow"} <= self._names(
            rows, "database", "drop-recreate"
        )


# --- U-29 & U-53 -----------------------------------------------------------------


class TestU29U53TargetInventory:
    def _declared_volumes(self) -> set[str]:
        vols = set()
        for f in sorted(REPO_ROOT.glob("docker-compose-*.yml")):
            if f.name.endswith(".test.yml"):
                continue
            in_vol = False
            for line in f.read_text().splitlines():
                if re.match(r"^volumes:", line):
                    in_vol = True
                    continue
                if re.match(r"^[^\s#]", line):
                    in_vol = False
                if in_vol and re.match(r"^\s+[A-Za-z0-9_-]+:\s*$", line):
                    vols.add(line.strip().rstrip(":"))
        return vols

    def test_every_declared_volume_is_assigned_or_never_destroy(self):
        declared = self._declared_volumes()
        assert declared, "expected some declared volumes"
        rows = _plan("--all")
        planned = {r["name"] for r in rows if r["target"] == "volume"}
        # Every declared volume appears in the --all plan (removed or preserved).
        assert declared <= planned, f"unaccounted volumes: {declared - planned}"

    def test_uc_logs_is_never_destroyed(self):
        rows = _plan("--all")
        uc_logs = [
            r for r in rows if r["target"] == "volume" and r["name"] == "uc-logs"
        ]
        assert uc_logs and uc_logs[0]["action"] == "preserve"
        assert uc_logs[0].get("reason") == "never-destroy"

    def test_db_targets_are_real_never_unitycatalog(self):
        dbs = {r["name"] for r in _plan("--all") if r["target"] == "database"}
        assert {"mlflow", "airflow", "iceberg_catalog"} <= dbs
        assert "unitycatalog" not in dbs  # the non-existent DB (plan 1.13.2)

    def test_inventory_excludes_overlay_volumes(self):
        # Discovery globs docker-compose-*.yml but skips *.test.yml (plan 1.16.6).
        body = _func_body("reset_discover_volumes")
        assert "*.test.yml" in body


# --- U-54 ------------------------------------------------------------------------


class TestU54ProductionResetUnrestricted:
    def test_cmd_reset_has_no_ol_test_pattern_guard(self):
        body = _func_body("cmd_reset")
        assert "ol_test_" not in body, (
            "production cmd_reset must not carry the test-harness ^ol_test_ guard "
            "(plan 1.14.3) — it resolves real configured targets"
        )

    def test_cmd_reset_resolves_real_configured_targets(self):
        # The plan enumerates real names / the configured bucket, not test-scoped ones.
        rows = _plan("--all")
        s3 = {r["name"] for r in rows if r["target"] == "s3"}
        assert any("lakehouse" in n for n in s3)  # default S3_BUCKET
        dbs = {r["name"] for r in rows if r["target"] == "database"}
        assert "mlflow" in dbs and "airflow" in dbs


# --- U-33 & U-56 (Checkpoint 3): --keep-mlflow semantics -------------------------


class TestU33U56KeepMlflow:
    def test_u33_keep_mlflow_excludes_mlflow_db_only(self):
        dbs = {
            r["name"]
            for r in _plan("--metadata", "--keep-mlflow")
            if r["target"] == "database"
        }
        assert "mlflow" not in dbs, "--keep-mlflow must exclude the mlflow DB"
        assert {"airflow", "iceberg_catalog"} <= dbs

    def test_u56_metadata_warns_unrecoverable_mlflow(self):
        out = _run("reset", "--metadata", "--dry-run").stdout
        assert "UNRECOVERABLE" in out and "MLflow artifacts" in out
        # A byte-size figure accompanies the unrecoverable class.
        assert re.search(r"mlflow-artifacts/ \(.+\)", out)

    def test_u56_keep_mlflow_suppresses_unrecoverable_class(self):
        out = _run("reset", "--metadata", "--keep-mlflow", "--dry-run").stdout
        assert (
            "UNRECOVERABLE" not in out
        ), "--keep-mlflow preserves artifacts; they must not be labelled orphans"
        # The other two classes remain.
        assert "recoverable" in out and "doubtful" in out

    def test_warning_never_names_sync_to_uc(self):
        out = _run("reset", "--metadata", "--dry-run").stdout
        assert "sync_to_uc" not in out  # absent in PR #0 (plan 1.14.6)


# --- U-59: reset inventory excludes overlays -------------------------------------


class TestU59InventoryExcludesOverlays:
    def test_discover_skips_test_yml_and_overlay_dir(self):
        # reset_discover_volumes globs docker-compose-*.yml at the repo root and
        # skips *.test.yml; overlay files live under tests/overlays/ (a different
        # path) so they are excluded by location too (plan 1.16.6).
        body = _func_body("reset_discover_volumes")
        assert "*.test.yml" in body
        assert "docker-compose-*.yml" in body

    def test_plan_contains_no_overlay_only_volume(self):
        # ol-test-* / *.test.yml volumes must never appear in a production plan.
        vols = {r["name"] for r in _plan("--all") if r["target"] == "volume"}
        assert not any(v.startswith("ol-test-") for v in vols)
        assert vols <= {
            "mlflow-data",
            "uc-data",
            "uc-logs",
            "spark-data",
            "spark-logs",
            "postgres-data",
            "seaweedfs-data",
            "delta-sharing-certs",
        }


# --- U-66b: the semantic gate is wired into reset --------------------------------


def _run_gate(env_extra: dict) -> int:
    """Run reset_semantic_gate (extracted from lakehouse) under a given env."""
    funcs = "".join(
        _extract(name)
        for name in (
            "detect_uc_backend",
            "reset_discover_volumes",
            "reset_effective_bucket",
            "reset_effective_db",
            "reset_effective_volume",
            "reset_semantic_gate",
        )
    )
    script = (
        f'PROJECT_ROOT="{REPO_ROOT}"; cd "$PROJECT_ROOT"; RED=""; NC="";\n'
        f"source scripts/lib/overlay.sh\n{funcs}\nreset_semantic_gate\n"
    )
    env = {**os.environ, **env_extra}
    return subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60
    ).returncode


def _extract(name: str) -> str:
    m = re.search(rf"(^{re.escape(name)}\(\) \{{.*?^\}})", TEXT, re.M | re.S)
    assert m, f"{name} not found"
    return m.group(1) + "\n"


class TestU66bGateWiredIntoReset:
    RID = "gate0001"
    GOOD = {
        "OVERLAY_ACTIVE": "true",
        "LAKEHOUSE_TEST_RUN_ID": RID,
        "LAKEHOUSE_RESOURCE_SUFFIX": RID,
        "COMPOSE_PROJECT_NAME": f"ol-test-{RID}",
    }

    def test_reset_execute_calls_gate_before_deletions(self):
        body = _func_body("reset_execute")
        assert body.index("reset_semantic_gate") < body.index(
            "reset_do_deletions"
        ), "the semantic gate must run before any deletion"

    def test_backup_calls_gate_before_snapshot(self):
        # REVIEW-HANDOFF #1: backup quiesces containers and snapshots the effective
        # bucket/DBs; under an overlay with LAKEHOUSE_ENV_FILE unset those could
        # resolve to production names. cmd_backup must run the gate before it
        # quiesces or snapshots anything.
        body = _func_body("cmd_backup")
        assert "reset_semantic_gate" in body, "cmd_backup must run the semantic gate"
        assert body.index("reset_semantic_gate") < body.index(
            "backup_quiesce_writers"
        ), "the gate must run before backup quiesces/snapshots"

    def test_restore_calls_gate_before_mutation(self):
        # Companion assertion: restore already gates; keep it guarded so the trio
        # (reset/backup/restore) stay symmetric.
        body = _func_body("cmd_restore")
        assert "reset_semantic_gate" in body
        assert body.index("reset_semantic_gate") < body.index(
            "backup_quiesce_writers"
        ), "the gate must run before restore quiesces/mutates"

    def test_restore_validates_manifest_targets_before_mutation(self):
        # REVIEW-HANDOFF #2: production restore must verify the MANIFEST's targets
        # belong to this stack before touching services, so a swapped artifact can't
        # drive pg_restore/s3 sync --delete at arbitrary names.
        body = _func_body("cmd_restore")
        assert (
            "restore_validate_targets" in body
        ), "restore must validate MANIFEST targets"
        assert body.index("restore_validate_targets") < body.index(
            "backup_quiesce_writers"
        ), "MANIFEST target validation must run before any service is touched"

    def test_restore_validator_compares_against_effective_helpers(self):
        # The validator derives expected targets from the same effective helpers the
        # engine uses, so it enforces run-scoping under an overlay AND stack-identity
        # in production.
        body = _func_body("restore_validate_targets")
        assert "reset_effective_bucket" in body
        assert "reset_effective_db" in body
        assert "reset_effective_volume" in body
        assert '"$force"' in body or "force" in body

    def test_good_targets_pass(self):
        assert _run_gate(self.GOOD) == 0

    def test_overlay_inactive_is_unrestricted(self):
        assert _run_gate({"OVERLAY_ACTIVE": "false"}) == 0

    def test_bad_bucket_class_aborts(self):
        assert _run_gate({**self.GOOD, "S3_BUCKET": "lakehouse"}) != 0

    def test_bad_database_class_aborts(self):
        assert _run_gate({**self.GOOD, "MLFLOW_PG_DB": "mlflow"}) != 0

    def test_bad_volume_class_aborts(self):
        assert _run_gate({**self.GOOD, "COMPOSE_PROJECT_NAME": "ol-test-other999"}) != 0

    def test_bad_container_class_aborts(self):
        assert _run_gate({**self.GOOD, "LAKEHOUSE_RESOURCE_SUFFIX": "other999"}) != 0


# --- U-31 (Checkpoint 4): backup/restore argument contract -----------------------


class TestU31BackupRestoreArgs:
    def test_restore_without_from_exits_nonzero(self):
        assert _run("restore").returncode != 0

    def test_restore_missing_artifact_exits_nonzero(self):
        assert _run("restore", "--from", "/nonexistent/backup/dir").returncode != 0

    def test_restore_incomplete_artifact_exits_nonzero(self, tmp_path):
        # A directory without a MANIFEST is not a complete backup.
        d = tmp_path / "half"
        d.mkdir()
        assert _run("restore", "--from", str(d)).returncode != 0

    def test_restore_requires_yes_non_interactive(self, tmp_path):
        # A complete-looking artifact still must not be applied without --yes
        # when stdin is not a TTY (the test harness).
        d = tmp_path / "art"
        d.mkdir()
        (d / "MANIFEST").write_text(
            "lakehouse-backup\nbucket=x\ndatabases=\nvolumes=\nuc_backend=h2\n"
        )
        r = _run("restore", "--from", str(d))
        assert r.returncode != 0
        assert "without --yes" in (r.stdout + r.stderr)

    def test_backup_rejects_unknown_flag(self):
        assert _run("backup", "--bogus").returncode == 2


# --- U-48 (Checkpoint 4): backup covers PostgreSQL, not volume-only --------------


class TestU48BackupCoversPostgres:
    def test_snapshot_dumps_every_database(self):
        body = _func_body("backup_take_snapshot")
        # It iterates the platform databases and calls pg_dump_db on each.
        assert "pg_dump_db" in body
        for db in ("airflow", "iceberg_catalog", "mlflow"):
            assert db in body, f"backup must cover the {db} database"

    def test_snapshot_syncs_s3_and_is_not_volume_only(self):
        body = _func_body("backup_take_snapshot")
        assert "s3_sync download" in body, "backup must sync S3 objects"
        assert "volume_backup" in body, "backup must also archive named volumes"
        # Not volume-only: PostgreSQL + S3 coverage present alongside volumes.
        assert "pg_dump_db" in body and "s3_sync" in body

    def test_pg_dump_uses_create_for_ownership(self):
        # --create carries CREATE DATABASE ... OWNER + grants (I-29 ownership).
        assert "--create" in _func_body("pg_dump_db")

    def test_uc_h2_captured_via_docker_cp(self):
        # UC state is backed up by docker cp of the H2 file (plan 1.15.1), not a
        # PostgreSQL dump of a non-existent unity_catalog DB by default.
        assert "docker cp" in _func_body("uc_h2_backup")


# --- U-63 (Checkpoint 4): backup prints the restore command ----------------------


class TestU63BackupPrintsRestoreCommand:
    def test_cmd_backup_prints_artifact_path_and_restore_command(self):
        body = _func_body("cmd_backup")
        # Prints the artifact path ($out) and a ready-to-paste restore invocation.
        assert "restore --from" in body
        assert "${out}" in body

    def test_restore_accepts_only_from(self):
        # Covered behaviourally by U-31 (bare restore exits non-zero); assert the
        # flag surface too: --from is the only positional-bearing option.
        body = _func_body("cmd_restore")
        assert "--from" in body
        assert "--from <path> is required" in body


# --- U-34 & U-62 (Checkpoint 5): the orphan classifier ---------------------------


def _classify(inventory: str) -> list[dict]:
    """Feed normalized inventory lines to doctor_classify (extracted from lakehouse)
    and parse the emitted DOCTOR tokens. No Docker: a pure code path (U-34)."""
    body = re.search(r"(^doctor_classify\(\) \{.*?^\})", TEXT, re.M | re.S).group(1)
    script = f"{body}\ndoctor_classify"
    r = subprocess.run(
        ["bash", "-c", script],
        input=inventory,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    rows = []
    for line in r.stdout.splitlines():
        if line.startswith("DOCTOR "):
            # name= is last and may contain '='; split only the class token.
            parts = line[len("DOCTOR ") :]
            cls = parts.split(" ", 1)[0].split("=", 1)[1]
            name = parts.split("name=", 1)[1] if "name=" in parts else ""
            rows.append({"class": cls, "name": name})
    return rows


class TestU34OrphanClassifier:
    def _classes(self, rows):
        return {r["class"] for r in rows}

    def test_delta_prefix_unregistered_is_recoverable(self):
        rows = _classify("prefix type=delta registered=no name=s3://b/warehouse/d1\n")
        assert rows == [{"class": "recoverable-delta", "name": "s3://b/warehouse/d1"}]

    def test_iceberg_prefix_unregistered_is_doubtful(self):
        rows = _classify("prefix type=iceberg registered=no name=s3://b/warehouse/i1\n")
        assert self._classes(rows) == {"doubtful-iceberg"}

    def test_registered_prefix_is_not_flagged(self):
        rows = _classify(
            "prefix type=delta registered=yes name=s3://b/warehouse/d1\n"
            "prefix type=iceberg registered=yes name=s3://b/warehouse/i1\n"
        )
        assert rows == []

    def test_mlflow_artifact_without_run_is_unrecoverable(self):
        rows = _classify(
            "artifact run_known=no name=s3://b/mlflow-artifacts/1/deadbeef/artifacts/f\n"
        )
        assert self._classes(rows) == {"unrecoverable-mlflow"}

    def test_uc_row_empty_location_is_dangling(self):
        rows = _classify("uc-row objects=NA location_empty=yes name=cat.s.t\n")
        assert self._classes(rows) == {"dangling-catalog-entry"}

    def test_uc_row_zero_objects_is_dangling(self):
        rows = _classify("uc-row objects=0 location_empty=no name=cat.s.t\n")
        assert self._classes(rows) == {"dangling-catalog-entry"}

    def test_uc_row_with_objects_is_not_flagged(self):
        rows = _classify("uc-row objects=5 location_empty=no name=cat.s.t\n")
        assert rows == []

    def test_name_value_containing_a_token_is_not_misclassified(self):
        # Regression: classification must key off the metadata tokens only, never the
        # trailing name= value. An unregistered Delta prefix whose S3 path literally
        # contains "registered=yes" (or "type=iceberg") must still be classified from
        # its real tokens, not the path text.
        rows = _classify(
            "prefix type=delta registered=no "
            "name=s3://b/warehouse/registered=yes/type=iceberg/t\n"
        )
        assert rows == [
            {
                "class": "recoverable-delta",
                "name": "s3://b/warehouse/registered=yes/type=iceberg/t",
            }
        ]

    def test_objects_unknown_is_never_flagged(self):
        # A UC row whose object count could not be determined (S3 unreachable) must
        # NOT be reported as dangling (guards the doctor_inventory_uc F3 fix).
        rows = _classify("uc-row objects=unknown location_empty=no name=cat.s.t\n")
        assert rows == []

    def test_all_four_classes_are_distinct_paths(self):
        rows = _classify(
            "prefix type=delta registered=no name=s3://b/warehouse/d1\n"
            "prefix type=iceberg registered=no name=s3://b/warehouse/i1\n"
            "artifact run_known=no name=s3://b/mlflow-artifacts/1/dead/artifacts/f\n"
            "uc-row objects=0 location_empty=no name=cat.s.t\n"
        )
        assert self._classes(rows) == {
            "recoverable-delta",
            "doubtful-iceberg",
            "unrecoverable-mlflow",
            "dangling-catalog-entry",
        }

    def test_no_fifth_class_exists(self):
        # There is no class keyed on a run record whose bytes are gone (undecidable,
        # plan 1.19.1). The classifier must never emit anything but the four.
        body = _func_body("doctor_classify")
        emitted = set(re.findall(r"class=([a-z-]+) ", body))
        assert emitted == {
            "recoverable-delta",
            "doubtful-iceberg",
            "unrecoverable-mlflow",
            "dangling-catalog-entry",
        }


class TestU62ArtifactFreeRunsUnflagged:
    def test_healthy_run_with_no_artifact_is_never_flagged(self):
        # A healthy artifact-free run produces NO artifact inventory line at all
        # (nothing under mlflow-artifacts/ for it) and no other class references it,
        # so the classifier emits nothing. Guards against reintroducing the removed
        # fifth "suspected missing artifacts" class.
        rows = _classify(
            "artifact run_known=yes name=s3://b/mlflow-artifacts/1/live/artifacts/f\n"
        )
        assert rows == []


class TestSharingQuiescedOnReset:
    """Delta Sharing reads warehouse/sharing/, so reset must quiesce it (and
    restart it via share_restore), while never entering `start all` / `stop all`."""

    def test_running_set_includes_sharing(self):
        body = _func_body("reset_running_services")
        assert "delta-sharing" in body
        assert 'up="$up sharing"' in body

    def test_quiesce_stops_sharing_all_modes(self):
        body = _func_body("reset_quiesce")
        for mode in ("data)", "metadata)", "all)"):
            seg = body.split(mode, 1)[1].split(";;", 1)[0]
            assert "sharing" in seg, f"sharing missing from reset_quiesce {mode}"

    def test_quiesce_containers_for_sharing(self):
        body = _func_body("quiesce_containers_for")
        assert "sharing)" in body and "delta-sharing" in body

    def test_cmd_stop_has_sharing_arm(self):
        assert "sharing)" in _func_body("cmd_stop")

    def test_start_has_no_sharing_arm(self):
        # sharing is not startable via the CLI dispatch (restore uses share_restore),
        # so `start all` / `start sharing` never bring it up.
        assert "sharing)" not in _func_body("cmd_start")

    def test_sharing_not_in_stop_all_validset(self):
        body = _func_body("cmd_stop")
        assert "mlflow|notebooks)" in body  # shared valid-set unchanged
        assert "mlflow|notebooks|sharing)" not in body  # not appended to stop-all

    def test_certs_volume_still_never(self):
        body = _func_body("reset_volume_mode")
        seg = body.split("delta-sharing-certs)", 1)[1].split(";;", 1)[0]
        assert '"never"' in seg
