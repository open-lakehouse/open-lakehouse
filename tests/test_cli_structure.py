"""CLI structure tests for the lifecycle commands (PR #0, Phase 1.5).

    U-28  reset/backup/doctor are TOP-LEVEL COMMANDS (4 sites), not services.

The 4 sites (plan 1.13.3): argument parsing (the connect-mode bypass), a
cmd_<name>() function, the top-level case dispatch, and cmd_help().
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LAKEHOUSE = REPO_ROOT / "lakehouse"
TEXT = LAKEHOUSE.read_text()


def _func_body(name: str) -> str:
    """Return the body of a `name() { ... }` bash function (brace at col 0 close)."""
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


class TestU28LifecycleCommandsAreTopLevel:
    COMMANDS = ("reset", "backup", "doctor")

    def test_cmd_functions_exist(self):
        for c in self.COMMANDS:
            assert f"cmd_{c}()" in TEXT, f"cmd_{c}() function missing"

    def test_top_level_case_dispatch(self):
        # Each command dispatches from the top-level case to its cmd_ function.
        for c in self.COMMANDS:
            assert re.search(
                rf"^\s*{c}\)\s+cmd_{c}", TEXT, re.M
            ), f"{c}) not dispatched to cmd_{c} in the top-level case"

    def test_arg_parsing_bypass_site(self):
        # The connect-mode bypass case (argument parsing) lists the commands.
        m = re.search(r"help\|status\|__resolve\|([a-z|]*)\|''", TEXT)
        assert m, "connect-mode bypass case not found"
        for c in self.COMMANDS:
            assert c in m.group(0), f"{c} missing from the arg-parsing bypass case"

    def test_listed_in_help(self):
        help_out = _run("help").stdout
        for c in self.COMMANDS:
            assert re.search(rf"^\s*{c}\b", help_out, re.M), f"{c} missing from help"

    def test_not_in_service_dispatch(self):
        # Must NOT appear in the start/stop/logs service `case $service in` blocks.
        for fn in ("cmd_start", "cmd_stop", "cmd_logs"):
            body = _func_body(fn)
            for c in self.COMMANDS:
                assert not re.search(
                    rf"^\s*{c}\)", body, re.M
                ), f"{c}) leaked into {fn} service dispatch"

    def test_rejects_all_without_yes_noninteractive(self):
        # Non-interactive destructive reset without --yes is rejected.
        r = _run("reset", "--all", stdin="")
        assert r.returncode != 0, "reset --all without --yes should be rejected"

    def test_dry_run_is_exempt_from_confirmation(self):
        r = _run("reset", "--all", "--dry-run", stdin="")
        assert r.returncode == 0, f"reset --all --dry-run should succeed: {r.stderr}"
        assert "DRY RUN" in r.stdout


class TestContainerRefsAreOverlayResolved:
    """Regression guard (plan 1.17.4): every docker exec/logs/ps container
    reference resolves through resolve_container_name so an active test overlay
    never probes or execs the wrong (production) stack. Base container literals
    may appear ONLY as an argument to resolve_container_name."""

    BASE_NAMES = (
        "spark-master-41",
        "spark-worker-41",
        "spark-connect-41",
        "kafka",
        "zookeeper",
        "unity-catalog",
        "airflow-webserver",
        "airflow-scheduler",
        "airflow-triggerer",
        "airflow-dag-processor",
        "jupyter",
    )

    def test_no_raw_literal_in_docker_exec_or_logs(self):
        alt = "|".join(re.escape(n) for n in self.BASE_NAMES)
        bad = re.findall(rf"docker (?:exec|logs)(?:\s+-\S+)*\s+({alt})\b", TEXT)
        assert not bad, f"raw literal container names in docker exec/logs: {bad}"

    def test_no_raw_literal_in_docker_ps_grep(self):
        alt = "|".join(re.escape(n) for n in self.BASE_NAMES)
        # `grep -q '^<base>$'` against `docker ps` must use the resolved name var.
        bad = re.findall(rf"grep -q ['\"]\^(?:{alt})\$['\"]", TEXT)
        assert not bad, f"raw literal container names in docker ps greps: {bad}"

    def test_port_preflight_skips_under_active_overlay(self):
        # The overlay stack uses a project-scoped bridge and publishes no host
        # ports, so the host-port pre-flight must short-circuit when the overlay
        # is active — else the production stack's ports spuriously block startup.
        body = _func_body("check_ports_for_service")
        m = re.search(r"OVERLAY_ACTIVE.*?\n(.*?\n)?\s*return 0", body, re.S)
        assert m, "check_ports_for_service must early-return under OVERLAY_ACTIVE"
        assert body.index("OVERLAY_ACTIVE") < body.index(
            "check_port_available"
        ), "the overlay skip must precede any host-port check"


# --- U-50 (Checkpoint 6): container-name probes match Compose --------------------


def _compose_container_names() -> set[str]:
    names = set()
    for f in sorted(REPO_ROOT.glob("docker-compose-*.yml")):
        if f.name.endswith(".test.yml"):
            continue
        for line in f.read_text().splitlines():
            m = re.match(r"\s*container_name:\s*(\S+)", line)
            if m:
                names.add(m.group(1))
    return names


def _resolve_default(base: str) -> str:
    """Mirror resolve_container_name on the DEFAULT path: the one allow-listed
    PR #0 fix (mlflow -> mlflow-server), else identity."""
    return "mlflow-server" if base == "mlflow" else base


class TestU50ContainerNamesMatchCompose:
    def test_every_probed_name_resolves_to_a_compose_container(self):
        # Every literal fed to resolve_container_name in the CLI must, once the
        # default-path resolution is applied, name a real Compose container_name.
        # This catches the `mlflow` vs `mlflow-server` bug class (§1.13.6, T-1.5.11).
        compose = _compose_container_names()
        assert compose, "expected container_name entries in the compose files"
        literals = set(re.findall(r"resolve_container_name\s+([a-z0-9-]+)", TEXT))
        assert literals, "expected resolve_container_name calls in the CLI"
        for base in literals:
            assert _resolve_default(base) in compose, (
                f"resolve_container_name {base} -> {_resolve_default(base)!r} "
                "does not match any Compose container_name"
            )

    def test_mlflow_probe_resolves_to_mlflow_server(self):
        # The specific bug: the CLI probes `mlflow` but Compose names it
        # `mlflow-server`; resolve_container_name must bridge that.
        assert "mlflow" in re.findall(r"resolve_container_name\s+([a-z0-9-]+)", TEXT)
        assert "mlflow-server" in _compose_container_names()
        # resolve_container_name lives in the sourced overlay lib.
        lib = (REPO_ROOT / "scripts" / "lib" / "overlay.sh").read_text()
        assert "mlflow-server" in lib, "resolve_container_name must map mlflow"

    def test_no_bare_is_container_running_mlflow_literal(self):
        # Nothing may probe the literal `mlflow` container directly (it does not
        # exist — Compose names it mlflow-server).
        assert not re.search(r'is_container_running\s+"mlflow"', TEXT)
