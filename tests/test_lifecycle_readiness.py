"""Real HTTP probes and profile writes, without Docker or installed services."""

import importlib.util
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "lakehouse").read_text()


def function(name):
    if name == "share_write_profile":
        # The previous implementation contained a JSON heredoc with a bare `}`.
        return SOURCE[
            SOURCE.index("share_write_profile() {") : SOURCE.index("\ncmd_share() {")
        ]
    return re.search(rf"^{name}\(\) \{{\n.*?^\}}", SOURCE, re.M | re.S).group()


@pytest.mark.parametrize("service", ["Unity Catalog", "MLflow", "Delta Sharing"])
@pytest.mark.parametrize("status", [200, 401, 403, 404, 503])
def test_http_readiness_rejects_error_responses(service, status):
    token = secrets.token_hex(24)
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("Authorization")))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        line = next(
            line
            for line in SOURCE.splitlines()
            if f'wait_for_service "{service}"' in line
        )
        command = shlex.split(line)[2]
        command = re.sub(
            r"https?://localhost:(?:\$\{[^}]+\}|\d+)",
            f"http://127.0.0.1:{server.server_port}",
            command,
        )
        result = subprocess.run(
            [
                "bash",
                "-c",
                function("wait_for_service")
                + '\nsleep() { :; }\nwait_for_service "$1" "$2" 1',
                "fixture",
                service,
                command,
            ],
            env={**os.environ, "DELTA_SHARING_TOKEN": token},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert (result.returncode == 0) == (status == 200)
        assert seen
        if service == "Delta Sharing":
            assert seen == [("/delta-sharing/shares", f"Bearer {token}")]
            assert token not in command
        assert token not in result.stdout + result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_profile_write_failure_is_propagated_even_in_conditional(tmp_path):
    target = tmp_path / "missing" / "profile.share"
    result = subprocess.run(
        [
            "bash",
            "-c",
            "set -e\n"
            + function("share_write_profile")
            + "\nshare_endpoint() { echo https://localhost:8443/delta-sharing; }"
            + '\nif share_write_profile "$DELTA_SHARING_TOKEN"; then exit 0; else exit 19; fi',
        ],
        env={
            **os.environ,
            "PROJECT_ROOT": str(ROOT),
            "SHARING_PROFILE": str(target),
            "DELTA_SHARING_TOKEN": secrets.token_hex(24),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 19
    assert not target.exists()
    assert "Wrote sharing profile" not in result.stdout
    assert "Cannot write private sharing profile" in result.stderr


def profile_writer():
    spec = importlib.util.spec_from_file_location(
        "write_sharing_profile", ROOT / "scripts/tools/write-sharing-profile.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_profile_is_private_and_json_encoded(tmp_path):
    target = tmp_path / "profile.share"
    token = 'synthetic"\\token\nwith special characters'
    profile_writer().write_profile(
        target, "https://localhost:8443/delta-sharing", token
    )
    assert json.loads(target.read_text())["bearerToken"] == token
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_failed_profile_replace_preserves_original_and_cleans_temporary_file(
    tmp_path, monkeypatch
):
    target = tmp_path / "profile.share"
    target.write_text("original-private-profile")
    writer = profile_writer()

    def fail_replace(*args):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(writer.os, "replace", fail_replace)
    with pytest.raises(OSError):
        writer.write_profile(
            target, "https://localhost:8443/delta-sharing", secrets.token_hex(24)
        )
    assert target.read_text() == "original-private-profile"
    assert sorted(tmp_path.iterdir()) == [target]


def test_profile_symlink_is_not_replaced(tmp_path):
    original = tmp_path / "original"
    original.write_text("preserve")
    target = tmp_path / "profile.share"
    target.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        profile_writer().write_profile(
            target, "https://localhost:8443/delta-sharing", secrets.token_hex(24)
        )
    assert original.read_text() == "preserve"
    assert target.is_symlink()
