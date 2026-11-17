"""Exercise the server arguments emitted by the local MLflow entrypoint."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("override", [None, "tracking.example.test:5000"])
def test_allowed_hosts_preserves_local_access_and_explicit_overrides(
    tmp_path, override
):
    psql = tmp_path / "psql"
    psql.write_text("#!/bin/sh\nexit 0\n")
    psql.chmod(0o755)
    mlflow = tmp_path / "mlflow"
    mlflow.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['ARGS'], 'w') as f:\n"
        "    json.dump(sys.argv[1:], f)\n"
    )
    mlflow.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "MLFLOW_ALLOWED_HOSTS"}
    env.update(
        PATH=f"{tmp_path}:{Path(sys.executable).parent}:{os.environ['PATH']}",
        ARGS=str(tmp_path / "args.json"),
    )
    if override:
        env["MLFLOW_ALLOWED_HOSTS"] = override
    subprocess.run(
        ["bash", str(ROOT / "docker/mlflow/entrypoint.sh")],
        env=env,
        check=True,
        capture_output=True,
        timeout=10,
    )
    args = json.loads((tmp_path / "args.json").read_text())
    allowed = args[args.index("--allowed-hosts") + 1]
    if override:
        assert allowed == override
    else:
        hosts = set(allowed.split(","))
        assert {
            "localhost",
            "localhost:5000",
            "127.0.0.1",
            "127.0.0.1:5000",
            "mlflow-server",
            "mlflow-server:5000",
        } <= hosts
        assert not any("*" in host for host in hosts)
