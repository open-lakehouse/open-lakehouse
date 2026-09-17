# SPDX-License-Identifier: Apache-2.0
"""Static configuration tests for the dashboard (Phase 3).

These run without Docker or Node — they read the ported dashboard source, the
compose file, and the CLI, and assert the port contract, the env-var contract
(U-25), the code-execution-off-by-default posture (U-26 / D6), and the
neutrality invariants (U-38 / D8): the dashboard is a separate optional compose
and is never started by `./lakehouse start all`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard"
COMPOSE = REPO / "docker-compose-dashboard.yml"
CLI = REPO / "lakehouse"

pytestmark = pytest.mark.dashboard

# Env vars supplied by the Node/Next runtime or the Dockerfile, not the compose
# environment block — allowed to be read in code without a compose entry.
_RUNTIME_ENV = {"NODE_ENV", "PORT", "HOSTNAME"}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _compose_env_keys() -> set[str]:
    """Keys under the dashboard service `environment:` block."""
    text = _read(COMPOSE)
    keys: set[str] = set()
    in_env = False
    env_indent = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "environment:":
            in_env = True
            env_indent = len(line) - len(line.lstrip())
            continue
        if in_env:
            indent = len(line) - len(line.lstrip())
            if stripped and indent <= env_indent:
                break  # left the environment block
            m = re.match(r"([A-Z0-9_]+):", stripped)
            if m:
                keys.add(m.group(1))
    return keys


def test_compose_exists_and_binds_loopback_3000():
    assert (
        COMPOSE.is_file()
    ), "docker-compose-dashboard.yml must exist (separate optional service)"
    text = _read(COMPOSE)
    assert (
        '"127.0.0.1:3000:3000"' in text
    ), "dashboard must publish only on loopback:3000"


def test_code_execution_off_by_default():
    """U-26 / D6: the flag defaults to false in compose, and every exec/write
    route is gated behind codeExecutionEnabled()."""
    assert (
        "DASHBOARD_ALLOW_CODE_EXECUTION: ${DASHBOARD_ALLOW_CODE_EXECUTION:-false}"
        in _read(COMPOSE)
    )

    gated = [
        "src/app/api/jupyter-exec/route.ts",
        "src/app/api/jupyter/[...path]/route.ts",
        "src/app/api/pipelines/run/route.ts",
        "src/app/api/pipelines/route.ts",
        "src/app/api/pipelines/history/route.ts",
    ]
    for rel in gated:
        src = _read(DASHBOARD / rel)
        assert (
            "codeExecutionEnabled()" in src
        ), f"{rel} must gate on codeExecutionEnabled()"
        assert (
            "codeExecutionDisabledResponse()" in src
        ), f"{rel} must return the disabled response"


def test_env_var_contract():
    """U-25: every env var the dashboard source reads is either declared in the
    compose environment block or is a known runtime/Dockerfile var."""
    compose_keys = _compose_env_keys()
    allowed = compose_keys | _RUNTIME_ENV

    read_vars: set[str] = set()
    for ts in (DASHBOARD / "src").rglob("*.ts*"):
        text = _read(ts)
        read_vars.update(re.findall(r"process\.env\.([A-Z0-9_]+)", text))
        read_vars.update(re.findall(r'requireEnv\(["\']([A-Z0-9_]+)["\']\)', text))

    # NEXT_PUBLIC_* are inlined at build time by Next and need no compose entry.
    missing = {
        v for v in read_vars if v not in allowed and not v.startswith("NEXT_PUBLIC_")
    }
    assert (
        not missing
    ), f"env vars read in code but not in compose/runtime: {sorted(missing)}"


def test_not_started_by_start_all():
    """U-38 / D8 neutrality: the dashboard is opt-in. Every CLI arm that acts on
    the dashboard compose must sit under a standalone `dashboard)` case label,
    never a `...|all)` behavior arm — so `start all` / `stop all` never touch it.
    (The valid-arg allowlist and usage strings may still name it alongside all.)"""
    lines = _read(CLI).splitlines()
    actions = [
        i for i, ln in enumerate(lines) if "overlay_set_compose_args dashboard" in ln
    ]
    assert actions, "expected at least one dashboard compose action in the CLI"
    for i in actions:
        label = None
        for j in range(i, -1, -1):
            m = re.match(r"\s*([a-z0-9|_-]+)\)\s*$", lines[j])
            if m:
                label = m.group(1)
                break
        assert label == "dashboard", (
            f"dashboard compose action at line {i + 1} is under case '{label}', "
            "expected a standalone 'dashboard)' arm (not co-listed with 'all')"
        )


def test_dashboard_is_separate_compose_not_folded_into_core():
    """The core compose files must not define the dashboard service."""
    for core in ("docker-compose-storage.yml", "docker-compose-spark41.yml"):
        assert "open-lakehouse-dashboard" not in _read(REPO / core)
