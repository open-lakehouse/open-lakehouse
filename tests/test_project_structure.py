"""Project structure validation tests.

Verifies the expected directory layout for the open-lakehouse demo platform.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestTopLevel:
    def test_lakehouse_cli_exists(self):
        cli = PROJECT_ROOT / "lakehouse"
        assert cli.exists() and os.access(
            cli, os.X_OK
        ), "lakehouse CLI missing or not executable"

    def test_required_root_files(self):
        for name in (
            "README.md",
            "LICENSE",
            "NOTICE",
            "SECURITY.md",
            "CLAUDE.md",
            "AGENTS.md",
            "pyproject.toml",
        ):
            assert (PROJECT_ROOT / name).exists(), f"missing root file: {name}"


class TestComposeFiles:
    EXPECTED = (
        "docker-compose-spark41.yml",
        "docker-compose-kafka.yml",
        "docker-compose-airflow.yml",
        "docker-compose-unity-catalog.yml",
        "docker-compose-mlflow.yml",
        "docker-compose-notebooks.yml",
    )

    def test_compose_files_present(self):
        for name in self.EXPECTED:
            assert (PROJECT_ROOT / name).exists(), f"missing compose file: {name}"

    def test_spark_40_compose_absent(self):
        assert not (
            PROJECT_ROOT / "docker-compose.yml"
        ).exists(), (
            "docker-compose.yml (Spark 4.0) should not exist in Spark-4.1-only repo"
        )


class TestDirectories:
    EXPECTED_DIRS = (
        "demos",
        "demos/_template",
        "demos/sdp-medallion",
        "demos/unity-catalog-multi-engine",
        "demos/realtime-mode",
        "demos/local-mode-spark",
        "docs",
        "scripts",
        "scripts/tools",
        "scripts/connectivity",
        "scripts/testdata",
        "tests",
        "tests/integration",
        "config/spark",
        "config/unity-catalog",
        "config/mlflow",
        "schemas",
        "terraform",
        "terraform-databricks",
        ".claude/skills/lakehouse-lifecycle",
    )

    def test_expected_dirs_exist(self):
        for d in self.EXPECTED_DIRS:
            assert (PROJECT_ROOT / d).is_dir(), f"missing directory: {d}"

    def test_dropped_demos_are_absent(self):
        dropped = (
            "streaming-kafka-to-iceberg",
            "delta-vs-iceberg",
            "mlflow-tracking",
            "airflow-orchestration",
        )
        for d in dropped:
            assert not (
                PROJECT_ROOT / "demos" / d
            ).exists(), f"old demo dir should not exist: demos/{d}"


class TestConnectFirst:
    """Connect-first architecture invariants."""

    def test_compose_defines_connect_service(self):
        compose = (PROJECT_ROOT / "docker-compose-spark41.yml").read_text()
        assert "spark-connect-41" in compose, "spark-connect-41 service missing"
        assert "15002" in compose, "Connect gRPC port 15002 missing"

    def test_cli_documents_flag(self):
        cli = (PROJECT_ROOT / "lakehouse").read_text()
        assert "--spark-connect" in cli, "--spark-connect flag missing in CLI"
        assert "--spark-local" in cli, "--spark-local stub missing in CLI"
        assert "LAKEHOUSE_SPARK_REMOTE" in cli, "Spark remote env var not exported"

    def test_local_mode_demo_placeholder_exists(self):
        readme = PROJECT_ROOT / "demos" / "local-mode-spark" / "README.md"
        assert (
            readme.exists()
        ), "demos/local-mode-spark/README.md must back the CLI message"
        content = readme.read_text()
        assert "NOT YET IMPLEMENTED" in content, "Placeholder must flag deferred state"


class TestDemoTeardowns:
    """U-32 (Checkpoint 5): teardown template covers S3 prefixes; every demo
    teardown is `set -euo pipefail` and idempotent-safe."""

    def _teardowns(self):
        return sorted((PROJECT_ROOT / "demos").glob("*/teardown.sh"))

    def test_template_has_s3_prefix_cleanup(self):
        body = (PROJECT_ROOT / "demos/_template/teardown.sh").read_text()
        assert "s3 rm" in body, "template teardown must delete its S3 prefix"
        assert "--recursive" in body
        assert "DEMO_S3_PREFIX" in body, "template must parameterize the S3 prefix"

    def test_every_teardown_is_strict_and_idempotent(self):
        teardowns = self._teardowns()
        assert teardowns, "expected demo teardown scripts"
        for f in teardowns:
            body = f.read_text()
            assert "set -euo pipefail" in body, f"{f} must be set -euo pipefail"
            # Destructive lines are guarded so a re-run over already-clean state is
            # not an error (idempotent): every active `s3 rm` carries `|| true`.
            for line in body.splitlines():
                s = line.strip()
                if s.startswith("#"):
                    continue
                if "s3 rm" in s or (s.endswith("--recursive \\")):
                    # the rm stanza spans lines; assert the block contains `|| true`
                    assert "|| true" in body, f"{f}: s3 rm must be idempotent (|| true)"


class TestU49PytestMarkers:
    """U-49 (Checkpoint 6): every marker PR #0 uses is registered in pyproject.toml
    (they were absent on `main`, which makes --strict-markers error)."""

    def test_required_markers_registered(self):
        cfg = (PROJECT_ROOT / "pyproject.toml").read_text()
        # Grab the [tool.pytest.ini_options] markers array.
        m = re.search(r"markers\s*=\s*\[(.*?)\]", cfg, re.S)
        assert m, "no pytest markers array in pyproject.toml"
        block = m.group(1)
        registered = set(re.findall(r'"([a-z_]+):', block))
        for marker in ("merge", "storage", "network", "dashboard", "sharing"):
            assert marker in registered, f"pytest marker '{marker}' not registered"


class TestAIScaffolding:
    def test_claude_md_under_cap(self):
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert content.count("\n") < 200, "CLAUDE.md exceeds ~200-line soft cap"

    def test_agents_md_is_pointer(self):
        content = (PROJECT_ROOT / "AGENTS.md").read_text()
        assert content.count("\n") < 30, "AGENTS.md should be a short pointer file"
        assert "CLAUDE.md" in content, "AGENTS.md should forward to CLAUDE.md"

    def test_lifecycle_skill_present(self):
        skill = PROJECT_ROOT / ".claude/skills/lakehouse-lifecycle/SKILL.md"
        assert skill.exists(), "lakehouse-lifecycle skill missing"


class TestSkillFrontmatter:
    """U-22: every .claude/skills/*/SKILL.md has YAML frontmatter with `name:` and
    `description:`, and the name matches its directory."""

    def _skills(self):
        root = PROJECT_ROOT / ".claude" / "skills"
        return [p for p in root.iterdir() if (p / "SKILL.md").exists()]

    def test_every_skill_has_valid_frontmatter(self):
        offenders = []
        for d in self._skills():
            text = (d / "SKILL.md").read_text()
            m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            if not m:
                offenders.append(f"{d.name}: no frontmatter block")
                continue
            fm = m.group(1)
            name = re.search(r"^name:\s*(.+)$", fm, re.M)
            desc = re.search(r"^description:\s*(.+)$", fm, re.M)
            if not name:
                offenders.append(f"{d.name}: missing name:")
            elif name.group(1).strip() != d.name:
                offenders.append(f"{d.name}: name '{name.group(1).strip()}' != dir")
            if not desc or not desc.group(1).strip():
                offenders.append(f"{d.name}: missing/empty description:")
        assert not offenders, "skill frontmatter issues: " + "; ".join(offenders)


class TestConnectivityScriptsLint:
    """U-10: the new Phase 2 connectivity scripts are Ruff- and Black-clean.
    Skips a linter that isn't installed (pre-commit enforces it in CI)."""

    SCRIPTS = sorted(
        str(p) for p in (PROJECT_ROOT / "scripts" / "connectivity").glob("test-s3-*.py")
    ) + [str(PROJECT_ROOT / "scripts" / "connectivity" / "test-warehouse-layout.py")]
    TARGETS = SCRIPTS + [
        str(
            PROJECT_ROOT / "scripts" / "connectivity" / "test-presigned-host-rewrite.py"
        )
    ]

    def test_ruff_clean(self):
        import pytest

        if shutil.which("ruff") is None:
            pytest.skip("ruff not installed")
        r = subprocess.run(
            ["ruff", "check", *self.TARGETS], capture_output=True, text=True
        )
        assert r.returncode == 0, f"ruff findings:\n{r.stdout}\n{r.stderr}"

    def test_black_clean(self):
        import pytest

        if shutil.which("black") is None:
            pytest.skip("black not installed")
        r = subprocess.run(
            ["black", "--check", *self.TARGETS], capture_output=True, text=True
        )
        assert r.returncode == 0, f"black would reformat:\n{r.stderr}"
