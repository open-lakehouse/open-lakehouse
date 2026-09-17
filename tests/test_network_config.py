"""Network-config assertions for the bridge conversion (PR #13 / Phase 1, T-1.1..T-1.8).

  U-02  no service uses network_mode: host
  U-03  every service is on the shared lakehouse-network
  U-04  no host.docker.internal for a lakehouse peer (the mlflow-agent -> host
        Ollama sidecar is the one allowed external-host exception)
  U-05  host-visible services publish their ports
  U-06  no duplicate published host port across the base compose files
  U-07  Spark worker/connect address the master by its bridge DNS name
  U-08  the Spark master advertises its own IP (SPARK_LOCAL_IP), never 0.0.0.0

Services are read from `docker compose config` so the airflow x-anchor merge is
resolved. Skips cleanly if the docker CLI is absent (config needs the CLI, not the
daemon).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_COMPOSE = sorted(
    f.name
    for f in REPO_ROOT.glob("docker-compose-*.yml")
    if not f.name.endswith(".test.yml")
)

pytestmark = pytest.mark.network

_docker = shutil.which("docker")
requires_docker_cli = pytest.mark.skipif(
    _docker is None, reason="docker CLI not available (compose config needs it)"
)


def _rendered(fname: str) -> dict:
    out = subprocess.run(
        ["docker", "compose", "-f", fname, "config", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, f"{fname} failed to render:\n{out.stderr}"
    return json.loads(out.stdout)


def _all_services():
    for fname in BASE_COMPOSE:
        doc = _rendered(fname)
        for svc_name, svc in (doc.get("services") or {}).items():
            yield fname, svc_name, svc


@requires_docker_cli
class TestBridgeNetworking:
    def test_u02_no_network_mode_host(self):
        offenders = [
            f"{f}:{s}" for f, s, cfg in _all_services() if cfg.get("network_mode")
        ]
        assert not offenders, f"services still using network_mode: {offenders}"

    def test_u03_every_service_on_lakehouse_network(self):
        offenders = []
        for f, s, cfg in _all_services():
            nets = cfg.get("networks") or {}
            names = set(nets.keys()) if isinstance(nets, dict) else set(nets)
            if "lakehouse-network" not in names:
                offenders.append(f"{f}:{s} -> {sorted(names)}")
        assert not offenders, f"services not on lakehouse-network: {offenders}"

    def test_u05_host_visible_services_publish_ports(self):
        # Collect every published host port across the base files.
        published = set()
        for f, s, cfg in _all_services():
            for p in cfg.get("ports") or []:
                pub = p.get("published") if isinstance(p, dict) else None
                if pub is not None:
                    published.add(int(pub))
        expected = {
            5432,  # postgres
            8333,  # seaweedfs S3
            8081,  # unity catalog
            7078,
            8082,
            8083,
            15002,  # spark master/UI/worker-UI/connect
            9092,
            2181,  # kafka/zookeeper
            5000,
            5001,  # mlflow tracking + gateway
            8085,  # airflow
            8889,  # jupyter
        }
        missing = expected - published
        assert not missing, f"expected published ports missing: {sorted(missing)}"

    def test_u06_no_duplicate_published_host_port(self):
        seen: dict[int, str] = {}
        dupes = []
        for f, s, cfg in _all_services():
            for p in cfg.get("ports") or []:
                pub = p.get("published") if isinstance(p, dict) else None
                if pub is None:
                    continue
                pub = int(pub)
                if pub in seen and seen[pub] != f"{f}:{s}":
                    dupes.append(f"port {pub}: {seen[pub]} vs {f}:{s}")
                seen[pub] = f"{f}:{s}"
        assert not dupes, f"duplicate published host ports: {dupes}"

    def test_u07_spark_addresses_master_by_dns_name(self):
        doc = _rendered("docker-compose-spark41.yml")
        for svc in ("spark-worker-41", "spark-connect-41"):
            cmd = json.dumps(doc["services"][svc].get("command"))
            assert (
                "spark://spark-master-41:7078" in cmd
            ), f"{svc} not pointed at the master DNS name"

    def test_u08_master_advertises_own_ip_not_zero(self):
        cmd = json.dumps(
            _rendered("docker-compose-spark41.yml")["services"]["spark-master-41"][
                "command"
            ]
        )
        assert "SPARK_LOCAL_IP" in cmd, "master must export SPARK_LOCAL_IP"
        assert "--host 0.0.0.0" not in cmd, "master must NOT advertise 0.0.0.0 (§1.8)"
        # --host is followed by the SPARK_LOCAL_IP var ($ at runtime, $$ in the
        # compose-config rendering).
        assert re.search(
            r"--host \$+\{?SPARK_LOCAL_IP\}?", cmd
        ), "master --host must be SPARK_LOCAL_IP (the container's own bridge IP)"


class TestNoHostDockerInternal:
    """U-04 — text scan (no Docker needed). host.docker.internal must not address a
    lakehouse peer; the only allowed occurrence is the mlflow-agent -> host Ollama
    sidecar (an external, non-lakehouse service reached via the host-gateway)."""

    def test_u04_no_host_docker_internal_for_peers(self):
        targets = (
            [REPO_ROOT / f for f in BASE_COMPOSE]
            + [REPO_ROOT / ".env.example"]
            + list((REPO_ROOT / "config").rglob("*.example"))
        )
        offenders = []
        for path in targets:
            for i, line in enumerate(path.read_text().splitlines(), 1):
                if "host.docker.internal" not in line:
                    continue
                # Allowed: the mlflow-agent Ollama external-host reference.
                if "ollama" in line.lower() or "host-gateway" in line.lower():
                    continue
                offenders.append(f"{path.name}:{i}: {line.strip()}")
        assert not offenders, f"host.docker.internal for lakehouse peers: {offenders}"
