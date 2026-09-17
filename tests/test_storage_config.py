"""Static checks for the Composed storage layer (PR #13 / Phase 1).

Covers the no-Docker slice of the Checkpoint 1 verification:
  U-16  the SeaweedFS s3conf.json generator is valid (identities + 5 actions)
  U-17  UC server.properties invariants (bucket-root path, non-empty session token)
  U-19  `storage` is registered across the CLI sites
        (+ the reset volume-mode decision for the Composed volumes)

The live checks (S-10 anonymous-403, S-11 bootstrap idempotency, `start storage`)
require a running Docker daemon and run under tests/integration/.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STORAGE_COMPOSE = REPO_ROOT / "docker-compose-storage.yml"
# server.properties is gitignored (developer-local), so on a fresh CI clone only
# the committed .example exists — assert the U-17 invariants against that
# (the CLI copies it to server.properties on first `start unity-catalog`).
UC_PROPS = REPO_ROOT / "config" / "unity-catalog" / "server.properties.example"
CLI = REPO_ROOT / "lakehouse"
INIT_SCRIPT = REPO_ROOT / "scripts" / "tools" / "init-storage.sh"


@pytest.mark.storage
class TestStorageComposeFile:
    def test_exists_and_declares_both_services(self):
        text = STORAGE_COMPOSE.read_text()
        assert re.search(r"^\s{2}postgres:", text, re.M), "postgres service missing"
        assert re.search(r"^\s{2}seaweedfs:", text, re.M), "seaweedfs service missing"

    def test_named_volumes_not_bind(self):
        text = STORAGE_COMPOSE.read_text()
        assert "postgres-data:/var/lib/postgresql/data" in text
        assert "seaweedfs-data:/data" in text
        # Named volumes are declared (not host binds — §2.5 Colima gotcha).
        assert re.search(r"^volumes:\s*$", text, re.M)
        for vol in ("postgres-data", "seaweedfs-data"):
            assert re.search(rf"^\s{{2}}{vol}:", text, re.M)

    def test_on_shared_bridge_network(self):
        text = STORAGE_COMPOSE.read_text()
        assert text.count("lakehouse-network") >= 3  # both services + the network def

    def test_publishes_host_ports(self):
        text = STORAGE_COMPOSE.read_text()
        assert '"5432:5432"' in text
        assert '"8333:8333"' in text


@pytest.mark.storage
class TestU16S3ConfGenerator:
    def test_s3conf_written_in_container_from_env(self):
        text = STORAGE_COMPOSE.read_text()
        # Generated inside the container (not bind-mounted) from the S3 creds.
        assert "s3conf.json" in text
        assert "$${S3_ACCESS_KEY}" in text and "$${S3_SECRET_KEY}" in text

    def test_s3conf_has_credentials_and_five_actions(self):
        text = STORAGE_COMPOSE.read_text()
        assert '"accessKey"' in text and '"secretKey"' in text
        for action in ("Admin", "Read", "Write", "List", "Tagging"):
            assert f'"{action}"' in text, f"missing S3 action {action}"

    def test_seaweedfs_serves_with_the_generated_config(self):
        text = STORAGE_COMPOSE.read_text()
        assert re.search(
            r"weed server -s3.*-s3\.config=/etc/seaweedfs/s3conf\.json", text, re.S
        )


@pytest.mark.storage
class TestU17UcServerProperties:
    def test_bucket_path_is_bucket_root(self):
        text = UC_PROPS.read_text()
        m = re.search(r"^s3\.bucketPath\.0=(.+)$", text, re.M)
        assert m, "s3.bucketPath.0 missing"
        val = m.group(1).strip()
        # Bucket root: s3://<bucket> with no trailing sub-prefix (§2.5).
        assert re.fullmatch(r"s3://[^/]+/?", val), f"not a bucket root: {val}"

    def test_session_token_non_empty(self):
        text = UC_PROPS.read_text()
        m = re.search(r"^s3\.sessionToken\.0=(.+)$", text, re.M)
        assert m and m.group(1).strip(), "s3.sessionToken.0 must be non-empty (§2.5)"


@pytest.mark.storage
class TestU19StorageCliRegistration:
    def test_start_stop_register_storage(self):
        text = CLI.read_text()
        # `storage` appears in the start & stop service dispatch + their guards.
        assert re.search(r"cmd_start\(\)", text)
        assert "storage)" in text
        # guard case lists storage
        assert re.search(r"storage\|spark\|kafka\|all", text)

    def test_logs_registers_postgres_and_seaweedfs(self):
        text = CLI.read_text()
        assert "postgres|postgresql)" in text
        assert "seaweedfs|s3)" in text

    def test_help_lists_storage(self):
        text = CLI.read_text()
        assert re.search(r"start \[service\].*storage", text)
        assert re.search(r"^\s*storage\s+SeaweedFS", text, re.M)

    def test_port_preflight_has_storage_case(self):
        text = CLI.read_text()
        # Storage ports are fixed (never offset — storage has no test overlay),
        # so the preflight checks the literal 5432 for PostgreSQL.
        assert 'check_port_available "5432"' in text
        assert "Port 5432 (PostgreSQL)" in text
        assert 'check_port_available "8333"' in text
        assert "Port 8333 (SeaweedFS S3)" in text

    def test_init_storage_is_executable_and_shellcheck_shape(self):
        assert INIT_SCRIPT.exists()
        assert INIT_SCRIPT.stat().st_mode & 0o111, "init-storage.sh not executable"
        text = INIT_SCRIPT.read_text()
        assert text.startswith("#!"), "missing shebang"
        assert "set -euo pipefail" in text


@pytest.mark.storage
class TestStorageVolumeResetMode:
    """The Composed storage volumes (postgres-data / seaweedfs-data) are NEVER
    removed by any reset mode (PR #13 T-1.20a, review fix): reset does not quiesce
    the storage services, so a `docker volume rm` would fail anyway, and their
    CONTENT is reset in place by the DB drop-recreate + S3 bucket-clear steps.
    Marking them "never" keeps `--dry-run` honest (it must not report a volume
    removal that never happens)."""

    def test_postgres_and_seaweedfs_volumes_never_removed(self):
        text = CLI.read_text()
        # reset_volume_mode maps both to "never" (content reset in place, not by
        # volume removal — dry-run must not over-promise).
        assert re.search(r'postgres-data\)\s*echo "never"', text)
        assert re.search(r'seaweedfs-data\)\s*echo "never"', text)


@pytest.mark.storage
class TestWarehouseLayoutLint:
    """U-17 / S-09 (static half): the warehouse-layout lint's collision detector
    must flag an object at `x` that is also a prefix `x/…` (SeaweedFS's one real
    S3 incompatibility, §2.3), and leave clean Delta/Iceberg layouts + explicit
    directory markers alone. The live half runs in tests/integration/."""

    def _find_collisions(self):
        import importlib.util

        path = REPO_ROOT / "scripts" / "connectivity" / "test-warehouse-layout.py"
        spec = importlib.util.spec_from_file_location("wl_lint", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.find_collisions

    def test_flags_file_vs_directory_collision(self):
        fc = self._find_collisions()
        assert fc(["warehouse/x", "warehouse/x/y"]) == [
            ("warehouse/x", "warehouse/x/y")
        ]

    def test_clean_delta_layout_has_no_collision(self):
        fc = self._find_collisions()
        assert (
            fc(["warehouse/t/_delta_log/00000.json", "warehouse/t/part-0.parquet"])
            == []
        )

    def test_explicit_directory_marker_is_not_a_collision(self):
        fc = self._find_collisions()
        assert fc(["warehouse/d/", "warehouse/d/f"]) == []
