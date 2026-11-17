"""Opt-in production dashboard build with network-isolated upstream fixtures."""

import os
import platform as platform_info
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(scope="session", autouse=True)
def composed_storage():
    """The dashboard wiring test uses only its own HTTP upstreams."""
    return False


@pytest.mark.skipif(
    os.environ.get("LAKEHOUSE_TEST_FRESH_INSTALL") != "1",
    reason="set LAKEHOUSE_TEST_FRESH_INSTALL=1 to build and boot isolated containers",
)
def test_dashboard_service_endpoints(tmp_path):
    native = "arm64" if platform_info.machine() in ("arm64", "aarch64") else "amd64"
    platform = os.environ.get("LAKEHOUSE_TEST_PLATFORM", "linux/" + native)
    name = "dashboard-install-" + uuid.uuid4().hex[:10]
    upstream = name + "-upstream"
    image = name + ":test"
    token = secrets.token_urlsafe(24)

    def run(*args, check=True, timeout=120):
        return subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, check=check, timeout=timeout
        )

    log = tmp_path / "build.log"
    with log.open("w") as out:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--platform",
                platform,
                "--pull",
                "--no-cache",
                "-t",
                image,
                "dashboard",
            ],
            cwd=ROOT,
            stdout=out,
            stderr=subprocess.STDOUT,
            timeout=1800,
        )
    assert result.returncode == 0, f"build failed: {log}\n{log.read_text()[-5000:]}"
    config = yaml.safe_load((ROOT / "docker-compose-dashboard.yml").read_text())
    endpoints = config["services"]["dashboard"]["environment"]
    stub = """
const http = require('http');
http.createServer((req,res) => {
  res.setHeader('Content-Type', 'application/json');
  if (req.url !== '/api/3.0/mlflow/gateway/endpoints/list') { res.writeHead(404); }
  res.end('{}');
}).listen(5000, '0.0.0.0');
http.createServer((req,res) => {
  res.setHeader('Content-Type', 'application/json');
  if (req.headers.authorization !== 'token ' + process.env.JUPYTER_TOKEN) { res.writeHead(403); res.end('{}'); return; }
  if (req.url !== '/api/contents') { res.writeHead(404); res.end('{}'); return; }
  res.end(JSON.stringify({type:'directory', content:[]}));
}).listen(8889, '0.0.0.0');
"""
    probe = """
(async () => {
  let res = await fetch('http://127.0.0.1:3000/api/health/ai-gateway');
  if (res.status !== 200 || (await res.json()).status !== 'healthy') throw new Error('gateway not healthy');
  res = await fetch('http://127.0.0.1:3000/api/jupyter/contents');
  if (res.status !== 200 || (await res.json()).type !== 'directory') throw new Error('Jupyter proxy failed');
  console.log('Gateway registry on 5000 and authenticated Jupyter proxy on 8889 verified');
})().catch(e => { console.error(e); process.exit(1); });
"""
    try:
        run("docker", "network", "create", name)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            upstream,
            "--network",
            name,
            "--network-alias",
            "jupyter",
            "--network-alias",
            "mlflow-server",
            "-e",
            f"JUPYTER_TOKEN={token}",
            "node:22-alpine",
            "node",
            "-e",
            stub,
        )
        run(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            name,
            "--platform",
            platform,
            "-e",
            f"JUPYTER_URL={endpoints['JUPYTER_URL']}",
            "-e",
            f"MLFLOW_URL={endpoints['MLFLOW_URL']}",
            "-e",
            f"JUPYTER_TOKEN={token}",
            "-e",
            "DASHBOARD_ALLOW_CODE_EXECUTION=true",
            image,
        )
        deadline = time.monotonic() + 120
        while True:
            result = run("docker", "exec", name, "node", "-e", probe, check=False)
            if result.returncode == 0:
                break
            assert time.monotonic() < deadline, result.stderr[-3000:]
            time.sleep(3)
        print(platform, result.stdout.strip())
        run("docker", "stop", upstream)
        failure = "fetch('http://127.0.0.1:3000/api/health/ai-gateway').then(r=>{if(r.status!==503)process.exit(1)}).catch(()=>process.exit(1))"
        run("docker", "exec", name, "node", "-e", failure)
    finally:
        for container in (name, upstream):
            run("docker", "rm", "-f", container, check=False)
        run("docker", "network", "rm", name, check=False)
        run("docker", "image", "rm", image, check=False)
