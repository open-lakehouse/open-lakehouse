"""Opt-in session handoff with real Jupyter and the production dashboard."""

import http.cookiejar
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(scope="session", autouse=True)
def composed_storage():
    """Use only isolated notebook/dashboard containers."""
    return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@pytest.mark.skipif(
    os.environ.get("LAKEHOUSE_TEST_JUPYTER_LAUNCH") != "1",
    reason="set LAKEHOUSE_TEST_JUPYTER_LAUNCH=1 for real browser-session checks",
)
def test_jupyter_browser_session(tmp_path):
    with socket.socket() as listener:
        assert (
            listener.connect_ex(("127.0.0.1", 8889)) != 0
        ), "Stop the notebook test on port 8889 before running this isolated check"
    name = "jupyter-session-" + secrets.token_hex(4)
    jupyter = name + "-notebook"
    dashboard = name + "-dashboard"
    image = name + ":test"
    token = secrets.token_urlsafe(32)

    def run(*args, check=True, timeout=120):
        return subprocess.run(
            args, cwd=ROOT, check=check, timeout=timeout, text=True, capture_output=True
        )

    # The pinned workshop image can be prepared once, without using local data.
    if run(
        "docker", "image", "inspect", "lakehouse-jupyter:spark-4.1.0", check=False
    ).returncode:
        run(
            "docker",
            "build",
            "-f",
            "docker/jupyter/Dockerfile",
            "-t",
            "lakehouse-jupyter:spark-4.1.0",
            ".",
            timeout=1800,
        )
    build_log = tmp_path / "dashboard-build.log"
    with build_log.open("w") as output:
        result = subprocess.run(
            ["docker", "build", "-t", image, "dashboard"],
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=1200,
        )
    assert result.returncode == 0, f"Dashboard build failed: {build_log}"
    try:
        run("docker", "network", "create", name)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            jupyter,
            "--network",
            name,
            "--network-alias",
            "jupyter",
            "-p",
            "127.0.0.1:8889:8889",
            "-e",
            f"JUPYTER_TOKEN={token}",
            "lakehouse-jupyter:spark-4.1.0",
        )
        run(
            "docker",
            "exec",
            jupyter,
            "python3",
            "-c",
            "import json; json.dump({'nbformat':4,'nbformat_minor':5,'metadata':{},'cells':[]},open('/home/jovyan/launch check.ipynb','w'))",
        )
        run(
            "docker",
            "run",
            "-d",
            "--name",
            dashboard,
            "--network",
            name,
            "-p",
            "127.0.0.1::3000",
            "-e",
            "JUPYTER_URL=http://jupyter:8889",
            "-e",
            f"JUPYTER_TOKEN={token}",
            "-e",
            "DASHBOARD_ALLOW_JUPYTER_LAUNCH=true",
            image,
        )
        info = json.loads(run("docker", "inspect", dashboard).stdout)[0]
        port = info["NetworkSettings"]["Ports"]["3000/tcp"][0]["HostPort"]
        base = f"http://localhost:{port}"
        deadline = time.monotonic() + 90
        while True:
            try:
                urllib.request.urlopen(base, timeout=2)
                urllib.request.urlopen("http://localhost:8889/api", timeout=2)
                break
            except (OSError, urllib.error.URLError):
                assert time.monotonic() < deadline, "Test services not ready"
                time.sleep(1)
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen("http://localhost:8889/api/contents")
        assert unauthorized.value.code == 403
        cookies = http.cookiejar.CookieJar()
        browser = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies), NoRedirect()
        )
        for path in ("", "launch check.ipynb"):
            request = urllib.request.Request(
                base + "/api/jupyter-launch",
                data=urllib.parse.urlencode({"path": path}).encode(),
                headers={"Origin": base, "Sec-Fetch-Site": "same-origin"},
            )
            with pytest.raises(urllib.error.HTTPError) as redirect:
                browser.open(request)
            response = redirect.value
            assert response.code == 303
            target = response.headers["Location"]
            assert target.startswith("http://localhost:8889/lab")
            assert token not in target
            assert response.headers["Cache-Control"] == "no-store"
            assert browser.open(target).status == 200
            assert browser.open("http://localhost:8889/api/contents").status == 200
        assert any(cookie.name == "username-localhost-8889" for cookie in cookies)
        request = urllib.request.Request(
            base + "/api/jupyter-launch",
            data=b"path=",
            headers={"Origin": "http://untrusted.example"},
        )
        with pytest.raises(urllib.error.HTTPError) as forbidden:
            browser.open(request)
        assert forbidden.value.code == 403
        run("docker", "stop", jupyter)
        request = urllib.request.Request(
            base + "/api/jupyter-launch", data=b"path=", headers={"Origin": base}
        )
        with pytest.raises(urllib.error.HTTPError) as unavailable:
            browser.open(request)
        assert "error=unavailable" in unavailable.value.headers["Location"]
    finally:
        for container in (dashboard, jupyter):
            run("docker", "rm", "-f", container, check=False)
        run("docker", "network", "rm", name, check=False)
        run("docker", "image", "rm", image, check=False)
