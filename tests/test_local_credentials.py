"""Local setup credentials are private, consistent and stable across reruns."""

import base64
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/tools/configure-local-credentials.py"
SPEC = importlib.util.spec_from_file_location("local_credentials", SCRIPT)
credentials = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(credentials)


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "installation"
    root.mkdir()
    for rel in (
        ".env.example",
        "config/spark/spark-defaults.conf.example",
        "config/unity-catalog/server.properties.example",
    ):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    for key in (
        *credentials.PLACEHOLDERS,
        "COMPOSE_PROJECT_NAME",
        "LAKEHOUSE_SHARING_PROFILE",
        "DASHBOARD_ALLOW_JUPYTER_LAUNCH",
    ):
        monkeypatch.delenv(key, raising=False)
    tools = tmp_path / "bin"
    tools.mkdir()
    docker = tools / "docker"
    docker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "if sys.argv[1] == 'info':\n"
        "    sys.exit(int(os.environ.get('TEST_DOCKER_DOWN', '0')))\n"
        "if sys.argv[1] == 'inspect':\n"
        "    sys.exit(1) if os.environ.get('TEST_INSPECT_FAIL') else None\n"
        "    print(os.environ.get('TEST_CONTAINERS', '[]'))\n"
        "elif sys.argv[1:3] == ['container', 'ls']:\n"
        "    sys.exit(1) if os.environ.get('TEST_LIST_FAIL') else None\n"
        "    for c in json.loads(os.environ.get('TEST_CONTAINERS', '[]')):\n"
        "        print(c['Name'].lstrip('/'))\n"
        "elif sys.argv[1:3] == ['volume', 'ls']:\n"
        "    print(os.environ.get('TEST_VOLUMES', ''))\n"
        "elif sys.argv[1] == 'exec':\n"
        "    print(os.environ.get('TEST_JUPYTER_RUNTIME', '{}'))\n"
        "else:\n"
        "    print('[]')\n"
    )
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    monkeypatch.delenv("TEST_CONTAINERS", raising=False)
    monkeypatch.delenv("TEST_DOCKER_DOWN", raising=False)
    for key in ("TEST_LIST_FAIL", "TEST_INSPECT_FAIL", "TEST_VOLUMES"):
        monkeypatch.delenv(key, raising=False)
    return root


def values(root):
    return credentials.read_env((root / ".env").read_text())


def private_files(root):
    return [
        root / rel
        for rel in (
            ".env",
            "config/spark/spark-defaults.conf",
            "config/unity-catalog/server.properties",
        )
    ]


def containers(root, data):
    return [
        {
            "Name": "/airflow-webserver",
            "Config": {
                "Labels": {"com.docker.compose.project.working_dir": str(root)},
                "Env": [f"{key}={value}" for key, value in data.items()],
            },
        }
    ]


def test_fresh_credentials_are_private_and_aligned(installation, capsys):
    credentials.configure(installation)
    data = values(installation)
    assert data["POSTGRES_USER"] == "lakehouse"
    assert data["AIRFLOW_ADMIN_USER"] == "admin"
    assert data["DASHBOARD_ALLOW_JUPYTER_LAUNCH"] == "true"
    assert len(base64.urlsafe_b64decode(data["AIRFLOW_FERNET_KEY"])) == 32
    assert len(data["S3_ACCESS_KEY"]) == 20
    assert len(data["POSTGRES_PASSWORD"]) == 64
    assert len(data["JUPYTER_TOKEN"]) == 64
    secret_keys = set(credentials.PLACEHOLDERS) - {
        "POSTGRES_USER",
        "AIRFLOW_ADMIN_USER",
    }
    assert len({data[k] for k in secret_keys}) == len(secret_keys)
    output = capsys.readouterr()
    for key in secret_keys:
        assert data[key] not in output.out + output.err
    for path in private_files(installation):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    spark = private_files(installation)[1].read_text()
    uc = private_files(installation)[2].read_text()
    assert (
        credentials.property_value(spark, "spark.hadoop.fs.s3a.access.key")
        == data["S3_ACCESS_KEY"]
    )
    assert (
        credentials.property_value(spark, "spark.hadoop.fs.s3a.secret.key")
        == data["S3_SECRET_KEY"]
    )
    assert credentials.property_value(uc, "s3.accessKey.0") == data["S3_ACCESS_KEY"]
    assert credentials.property_value(uc, "s3.secretKey.0") == data["S3_SECRET_KEY"]


def test_rerun_preserves_values_contents_and_mtimes(installation):
    credentials.configure(installation)
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in private_files(installation)
    }
    credentials.configure(installation)
    assert before == {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in private_files(installation)
    }


def test_existing_template_is_completed(installation):
    shutil.copyfile(installation / ".env.example", installation / ".env")
    credentials.configure(installation)
    data = values(installation)
    assert data["S3_ACCESS_KEY"] != "lakehouse_s3"
    assert data["S3_SECRET_KEY"] != "lakehouse_s3_secret"  # pragma: allowlist secret
    assert data["POSTGRES_USER"] != "your_username"
    assert data["MLFLOW_PG_PASS"] and data["DELTA_SHARING_TOKEN"]


def test_fresh_example_false_does_not_prevent_setup_handoff(installation):
    with (installation / ".env.example").open("a") as f:
        f.write("\nDASHBOARD_ALLOW_JUPYTER_LAUNCH=false\n")  # pragma: allowlist secret
    credentials.configure(installation)
    assert values(installation)["DASHBOARD_ALLOW_JUPYTER_LAUNCH"] == "true"


def test_existing_explicit_settings_and_quoted_password_are_preserved(installation):
    credentials.configure(installation)
    path = installation / ".env"
    text = re.sub(
        r"(?m)^POSTGRES_PASSWORD=.*$",
        "POSTGRES_PASSWORD='custom $value with spaces'",  # pragma: allowlist secret - test fixture
        path.read_text(),
    )
    text = text.replace(
        "DASHBOARD_ALLOW_JUPYTER_LAUNCH=true", "DASHBOARD_ALLOW_JUPYTER_LAUNCH=false"
    )
    path.write_text(text)
    path.chmod(0o644)
    credentials.configure(installation)
    assert path.read_text() == text
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "key", ["POSTGRES_PASSWORD", "MLFLOW_PG_PASS", "AIRFLOW_FERNET_KEY"]
)
def test_missing_persistent_secret_is_not_rotated(installation, key):
    credentials.configure(installation)
    path = installation / ".env"
    text = re.sub(rf"(?m)^{key}=.*\n", "", path.read_text())
    path.write_text(text)
    with pytest.raises(ValueError, match=f"restore {key}"):
        credentials.configure(installation)
    assert path.read_text() == text


def test_restore_missing_env_from_owned_container_configuration(
    installation, monkeypatch
):
    credentials.configure(installation)
    existing = values(installation)
    recovered = {k: existing[k] for k in credentials.PLACEHOLDERS}
    recovered["AIRFLOW__CORE__FERNET_KEY"] = recovered.pop("AIRFLOW_FERNET_KEY")
    monkeypatch.setenv(
        "TEST_CONTAINERS", json.dumps(containers(installation, recovered))
    )
    (installation / ".env").unlink()
    credentials.configure(installation)
    assert all(values(installation)[k] == existing[k] for k in credentials.PLACEHOLDERS)


def test_other_projects_container_secrets_are_not_adopted(installation, monkeypatch):
    foreign_password = secrets.token_hex(16)
    monkeypatch.setenv(
        "TEST_CONTAINERS",
        json.dumps(
            containers(
                installation.parent / "other",
                {"POSTGRES_PASSWORD": foreign_password},
            )
        ),
    )
    credentials.configure(installation)
    assert values(installation)["POSTGRES_PASSWORD"] != foreign_password


def test_existing_sharing_token_is_reused(installation):
    credentials.configure(installation)
    original = values(installation)["DELTA_SHARING_TOKEN"]
    (installation / "lakehouse.share").write_text(json.dumps({"bearerToken": original}))
    path = installation / ".env"
    path.write_text(re.sub(r"(?m)^DELTA_SHARING_TOKEN=.*\n", "", path.read_text()))
    credentials.configure(installation)
    assert values(installation)["DELTA_SHARING_TOKEN"] == original


def test_s3_credentials_can_be_recovered_from_existing_configs(installation):
    credentials.configure(installation)
    original = values(installation)
    path = installation / ".env"
    path.write_text(
        re.sub(r"(?m)^S3_(ACCESS_KEY|SECRET_KEY)=.*\n", "", path.read_text())
    )
    credentials.configure(installation)
    assert values(installation)["S3_ACCESS_KEY"] == original["S3_ACCESS_KEY"]
    assert values(installation)["S3_SECRET_KEY"] == original["S3_SECRET_KEY"]


def test_config_mismatch_stops_before_any_write(installation):
    credentials.configure(installation)
    spark = private_files(installation)[1]
    spark.write_text(
        spark.read_text().replace(
            values(installation)["S3_ACCESS_KEY"], "unrelated-key"
        )
    )
    before = {p: p.read_bytes() for p in private_files(installation)}
    with pytest.raises(ValueError, match="Credential mismatch"):
        credentials.configure(installation)
    assert before == {p: p.read_bytes() for p in private_files(installation)}


@pytest.mark.parametrize("key", sorted(credentials.PLACEHOLDERS))
@pytest.mark.parametrize("stopped", [False, True])
def test_container_mismatch_stops_before_any_write(
    installation, monkeypatch, capsys, key, stopped
):
    credentials.configure(installation)
    capsys.readouterr()
    current = values(installation)[key]
    recovered = secrets.token_hex(32)
    docker_key = "AIRFLOW__CORE__FERNET_KEY" if key == "AIRFLOW_FERNET_KEY" else key
    owned = containers(installation, {docker_key: recovered})
    owned[0]["Name"] = "/" + {
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
        "S3_ACCESS_KEY": "seaweedfs",
        "S3_SECRET_KEY": "seaweedfs",
        "MLFLOW_PG_PASS": "mlflow-server",
        "JUPYTER_TOKEN": "jupyter",
        "DELTA_SHARING_TOKEN": "delta-sharing",
    }.get(key, "airflow-webserver")
    owned[0]["State"] = {"Running": not stopped}
    monkeypatch.setenv("TEST_CONTAINERS", json.dumps(owned))
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
        for p in private_files(installation)
    }

    def unexpected_write(*args):
        pytest.fail("conflict reached private_write")

    monkeypatch.setattr(credentials, "private_write", unexpected_write)
    with pytest.raises(ValueError, match=f"Credential mismatch.*{key}") as error:
        credentials.configure(installation)
    assert before == {
        p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
        for p in private_files(installation)
    }
    output = capsys.readouterr()
    diagnostic = str(error.value) + output.out + output.err
    assert current not in diagnostic
    assert recovered not in diagnostic


def test_matching_container_credentials_preserve_files(installation, monkeypatch):
    credentials.configure(installation)
    recovered = values(installation)
    recovered["AIRFLOW__CORE__FERNET_KEY"] = recovered.pop("AIRFLOW_FERNET_KEY")
    monkeypatch.setenv(
        "TEST_CONTAINERS", json.dumps(containers(installation, recovered))
    )
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in private_files(installation)
    }
    credentials.configure(installation)
    assert before == {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in private_files(installation)
    }


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("source", ["container", "fernet_alias", "sharing_profile"])
def test_conflicting_recovery_sources_stop_before_any_write(
    installation, monkeypatch, capsys, reverse, source
):
    credentials.configure(installation)
    capsys.readouterr()
    key = {
        "container": "POSTGRES_PASSWORD",
        "fernet_alias": "AIRFLOW_FERNET_KEY",
        "sharing_profile": "DELTA_SHARING_TOKEN",
    }[source]
    original = values(installation)[key]
    different = secrets.token_hex(32)
    owned = containers(installation, {key: original})
    if source == "sharing_profile":
        (installation / "lakehouse.share").write_text(
            json.dumps({"bearerToken": different})
        )
    else:
        other_key = "AIRFLOW__CORE__FERNET_KEY" if source == "fernet_alias" else key
        other = containers(installation, {other_key: different})[0]
        other["Name"] = "/mlflow-server"
        owned.append(other)
    if reverse:
        owned.reverse()
    monkeypatch.setenv("TEST_CONTAINERS", json.dumps(owned))
    before = {p: p.read_bytes() for p in private_files(installation)}

    def unexpected_write(*args):
        pytest.fail("conflicting recovery sources reached private_write")

    monkeypatch.setattr(credentials, "private_write", unexpected_write)
    with pytest.raises(ValueError, match=f"Credential mismatch.*{key}") as error:
        credentials.configure(installation)
    assert before == {p: p.read_bytes() for p in private_files(installation)}
    output = capsys.readouterr()
    assert original not in str(error.value) + output.out + output.err
    assert different not in str(error.value) + output.out + output.err


def test_matching_recovery_alias_and_profile_are_preserved(installation, monkeypatch):
    credentials.configure(installation)
    data = values(installation)
    owned = containers(installation, data)
    other = containers(
        installation,
        {"AIRFLOW__CORE__FERNET_KEY": data["AIRFLOW_FERNET_KEY"]},
    )[0]
    other["Name"] = "/mlflow-server"
    owned.append(other)
    monkeypatch.setenv("TEST_CONTAINERS", json.dumps(owned))
    (installation / "lakehouse.share").write_text(
        json.dumps({"bearerToken": data["DELTA_SHARING_TOKEN"]})
    )
    before = {p: p.read_bytes() for p in private_files(installation)}
    credentials.configure(installation)
    assert before == {p: p.read_bytes() for p in private_files(installation)}


def test_single_quoted_secret_is_not_overridden_by_parent_environment(
    installation, monkeypatch
):
    credentials.configure(installation)
    path = installation / ".env"
    literal = "private $literal with spaces"  # pragma: allowlist secret - test fixture
    text = re.sub(
        r"(?m)^POSTGRES_PASSWORD=.*$",
        f"POSTGRES_PASSWORD='{literal}'",
        path.read_text(),
    )
    path.write_text(text)
    monkeypatch.setenv("POSTGRES_PASSWORD", secrets.token_hex(32))
    monkeypatch.setenv(
        "TEST_CONTAINERS",
        json.dumps(containers(installation, {"POSTGRES_PASSWORD": literal})),
    )
    credentials.configure(installation)
    assert path.read_text() == text
    assert values(installation)["POSTGRES_PASSWORD"] == literal


def test_no_changes_without_available_docker_state(installation, monkeypatch):
    monkeypatch.setenv("TEST_DOCKER_DOWN", "1")
    with pytest.raises(ValueError, match="Start Docker"):
        credentials.configure(installation)
    assert not (installation / ".env").exists()


@pytest.mark.parametrize("failure", ["TEST_LIST_FAIL", "TEST_INSPECT_FAIL"])
def test_incomplete_docker_inspection_stops_without_writes(
    installation, monkeypatch, failure
):
    monkeypatch.setenv("TEST_CONTAINERS", json.dumps(containers(installation, {})))
    monkeypatch.setenv(failure, "1")
    with pytest.raises(ValueError, match="Docker state"):
        credentials.configure(installation)
    assert not (installation / ".env").exists()


def test_stopped_installation_with_only_storage_volumes_is_protected(
    installation, monkeypatch
):
    monkeypatch.setenv("TEST_VOLUMES", "installation_postgres-data")
    with pytest.raises(ValueError, match="restore POSTGRES_USER"):
        credentials.configure(installation)
    assert not (installation / ".env").exists()


def test_running_airflow_password_is_not_silently_replaced(installation, monkeypatch):
    credentials.configure(installation)
    path = installation / ".env"
    text = re.sub(r"(?m)^AIRFLOW_ADMIN_PASSWORD=.*\n", "", path.read_text())
    path.write_text(text)
    monkeypatch.setenv("TEST_CONTAINERS", json.dumps(containers(installation, {})))
    with pytest.raises(ValueError, match="restore AIRFLOW_ADMIN_PASSWORD"):
        credentials.configure(installation)
    assert path.read_text() == text


def test_existing_jupyter_runtime_token_is_recovered(installation, monkeypatch):
    credentials.configure(installation)
    token = values(installation)["JUPYTER_TOKEN"]
    path = installation / ".env"
    path.write_text(re.sub(r"(?m)^JUPYTER_TOKEN=.*\n", "", path.read_text()))
    owned = containers(installation, {})
    owned[0]["Name"] = "/jupyter"
    monkeypatch.setenv("TEST_CONTAINERS", json.dumps(owned))
    monkeypatch.setenv("TEST_JUPYTER_RUNTIME", json.dumps({"token": token}))
    credentials.configure(installation)
    assert values(installation)["JUPYTER_TOKEN"] == token


def test_symlinked_env_is_not_replaced(installation):
    outside = installation.parent / "outside"
    outside.write_text("preserve")
    (installation / ".env").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        credentials.configure(installation)
    assert outside.read_text() == "preserve"


def test_invalid_existing_fernet_key_is_not_replaced(installation):
    credentials.configure(installation)
    path = installation / ".env"
    text = re.sub(
        r"(?m)^AIRFLOW_FERNET_KEY=.*$", "AIRFLOW_FERNET_KEY=invalid", path.read_text()
    )
    path.write_text(text)
    with pytest.raises(ValueError, match="Invalid AIRFLOW_FERNET_KEY"):
        credentials.configure(installation)
    assert path.read_text() == text


def function(name):
    source = (ROOT / "lakehouse").read_text()
    return re.search(rf"^{name}\(\) \{{\n.*?^\}}", source, re.M | re.S).group()


def test_overlay_skips_real_credential_files(installation):
    result = subprocess.run(
        [
            "bash",
            "-c",
            function("ensure_local_credentials")
            + "\nOVERLAY_ACTIVE=true\nensure_local_credentials\n",
        ],
        env={**os.environ, "PROJECT_ROOT": str(installation)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not (installation / ".env").exists()


def test_setup_initializes_without_manual_credential_edits(installation):
    tools = installation / "scripts/tools"
    tools.mkdir(parents=True)
    shutil.copyfile(SCRIPT, tools / SCRIPT.name)
    (tools / "download-jars.sh").write_text("#!/bin/sh\nexit 0\n")
    stubs = """
header() { :; }
check_gnutools_on_macos() { :; }
check_prerequisites() { :; }
check_credential_consistency() { :; }
check_cmd() { return 1; }
nc() { return 1; }
df() { echo 'fs 99G 1G 98G'; }
OVERLAY_ACTIVE=false
DF_TOOL=df
"""
    script = (
        stubs
        + function("ensure_local_credentials")
        + "\n"
        + function("cmd_setup")
        + "\ncmd_setup\n"
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env={**os.environ, "PROJECT_ROOT": str(installation)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Setup complete" in result.stdout
    assert values(installation)["JUPYTER_TOKEN"]


def test_credentials_only_dispatch_skips_downloads_and_services(installation):
    tools = installation / "scripts/tools"
    tools.mkdir(parents=True)
    shutil.copyfile(SCRIPT, tools / SCRIPT.name)
    script = (
        "OVERLAY_ACTIVE=false\n"
        + function("ensure_local_credentials")
        + "\n"
        + function("cmd_setup")
        + "\ncmd_setup --credentials-only\n"
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env={**os.environ, "PROJECT_ROOT": str(installation)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert values(installation)["MLFLOW_PG_PASS"]
    assert not (installation / "jars").exists()
    assert 'setup)        cmd_setup "${@:2}"' in (ROOT / "lakehouse").read_text()
