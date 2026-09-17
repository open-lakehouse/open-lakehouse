"""Doc-truth tests (PR #0, Phase 1.5, Checkpoint 6).

    U-27  No doc claims `down -v` reaches SeaweedFS / host PostgreSQL (§1.10):
          - no "PostgreSQL-backed" S3 claim in stop.md / SKILL.md / CLAUDE.md
          - no no-op `volume ls | grep seaweedfs` clean-slate recipe
          - the start-fresh / full-teardown guidance points at `./lakehouse reset`
    U-41  No doc claims UC supports Iceberg WRITES (T-1.5.12): any line pairing
          "iceberg write" with a Unity Catalog reference must be a NEGATIVE statement.

Pure static scans of the repo docs/skills/compose — no Docker, no stack.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STOP_MD = PROJECT_ROOT / ".claude/skills/lakehouse-lifecycle/stop.md"
SKILL_MD = PROJECT_ROOT / ".claude/skills/lakehouse-lifecycle/SKILL.md"
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"

pytestmark = pytest.mark.merge


# --- U-27 ------------------------------------------------------------------------


class TestU27TeardownDocsAreTruthful:
    TEARDOWN_DOCS = (STOP_MD, SKILL_MD, CLAUDE_MD)

    def test_no_postgresql_backed_s3_claim(self):
        for f in self.TEARDOWN_DOCS:
            body = f.read_text().lower()
            assert (
                "postgresql-backed" not in body
            ), f"{f.name}: SeaweedFS does not live in a PostgreSQL-backed S3 store"
            assert "postgres-backed s3" not in body

    def test_no_noop_grep_seaweedfs_recipe(self):
        # The old "clean slate" recipe (`docker volume ls | grep seaweedfs`) is a
        # no-op — SeaweedFS is not a Compose volume. It must be gone.
        for f in self.TEARDOWN_DOCS:
            body = f.read_text()
            assert not re.search(
                r"volume ls.*grep\s+seaweedfs", body
            ), f"{f.name}: the no-op grep-seaweedfs clean-slate recipe must be removed"

    def test_start_fresh_points_at_reset(self):
        # stop.md's destructive / start-fresh guidance must route to `./lakehouse
        # reset`, not raw `down -v`.
        body = STOP_MD.read_text()
        assert "./lakehouse reset" in body, "stop.md must point at ./lakehouse reset"
        # And it must warn that — since storage is Composed (PR #13) — `down -v` now
        # WIPES the storage volumes (the opposite of the old host-installed claim).
        low = body.lower()
        assert "down -v" in low and (
            "postgres-data" in low and "seaweedfs-data" in low
        ), "stop.md must explain down -v now wipes postgres-data + seaweedfs-data"

    def test_skill_rule5_and_claude_rule4_route_to_reset(self):
        assert (
            "./lakehouse reset" in SKILL_MD.read_text()
        ), "SKILL.md Golden Rule #5 must route start-fresh to ./lakehouse reset"
        assert (
            "./lakehouse reset" in CLAUDE_MD.read_text()
        ), "CLAUDE.md Golden Rule #4 must point at ./lakehouse reset"


# --- U-41 ------------------------------------------------------------------------

_UC = re.compile(r"\b(uc|unity[- ]?catalog|unitycatalog|unity)\b", re.I)
_ICEBERG_WRITE = re.compile(r"iceberg\s+write", re.I)
_NEGATION = re.compile(
    r"\b(no|not|never|without|lacks?|rejects?|read[- ]only|unsupported|"
    r"not\s+supported|disabled)\b",
    re.I,
)


def _scan_files():
    files = []
    files += sorted(PROJECT_ROOT.glob("docker-compose-*.yml"))
    files += [CLAUDE_MD]
    for base in ("docs", ".claude/skills"):
        for p in (PROJECT_ROOT / base).rglob("*.md"):
            # docs/merge/* are meta-analysis that intentionally QUOTE the old false
            # claims in order to refute them — out of scope for this truth check.
            if "merge" in p.relative_to(PROJECT_ROOT).parts:
                continue
            files.append(p)
    return [f for f in files if not f.name.endswith(".test.yml")]


class TestU41NoUCIcebergWriteClaims:
    def test_uc_iceberg_write_lines_are_all_negative(self):
        offenders = []
        for f in _scan_files():
            for i, line in enumerate(f.read_text().splitlines(), 1):
                if _ICEBERG_WRITE.search(line) and _UC.search(line):
                    if not _NEGATION.search(line):
                        offenders.append(
                            f"{f.relative_to(PROJECT_ROOT)}:{i}: {line.strip()}"
                        )
        assert not offenders, (
            "positive UC-Iceberg-write claims found (UC OSS 0.4.x is Iceberg "
            "read-only); only negative statements are allowed:\n" + "\n".join(offenders)
        )

    def test_uc_compose_comment_states_no_iceberg_write(self):
        # The specific T-1.5.12 fix: the UC compose comment must no longer claim the
        # image "adds Iceberg write support".
        comment = (PROJECT_ROOT / "docker-compose-unity-catalog.yml").read_text()
        assert "adds Iceberg\n    # write support" not in comment
        assert re.search(
            r"no\s+iceberg\s+write", comment, re.I
        ), "UC compose comment must state it adds NO Iceberg write support"
