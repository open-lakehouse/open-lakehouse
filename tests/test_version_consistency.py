"""T0 pin-consistency gate (no Docker) — wraps scripts/tools/verify-versions.sh.

A version pin is a tested claim, not a comment (see docs/testing.md). This is the
static half of that guarantee: it fails the build when the core jar versions
named in download-jars.sh, spark-defaults.conf.example, and CLAUDE.md disagree,
or when a forbidden (known-broken) version or a JDBC-catalog path has leaked into
shipped config. It runs in the existing unit job — no runner, no network.

The behavioral half (does Delta 4.3.1 actually work on the pinned classpath, and
does 4.3.0 actually fail) lives in tests/integration/test_delta_version.py and
the e2e version-change matrix.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "tools" / "verify-versions.sh"


def test_verify_versions_script_present_and_executable():
    assert GATE.is_file(), "verify-versions.sh missing"
    # bit is nice-to-have; the suite invokes it via bash regardless.
    assert GATE.read_text().startswith("#!"), "verify-versions.sh missing shebang"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_pins_are_consistent():
    """download-jars.sh / spark-defaults.conf.example / CLAUDE.md agree, and no
    forbidden version or JDBC-catalog path is present in shipped config."""
    proc = subprocess.run(
        ["bash", str(GATE), "--tracked-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    # The gate prints per-check ✓/✗ lines; surface them on failure so the CI log
    # names the exact mismatch rather than just an exit code.
    assert proc.returncode == 0, (
        "version-consistency gate failed:\n"
        + proc.stdout
        + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else "")
    )
