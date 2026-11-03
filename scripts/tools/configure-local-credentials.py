#!/usr/bin/env python3
"""Prepare private local credentials without rotating an existing installation."""

import argparse
import base64
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess  # nosec B404 - Docker state is read using fixed argument arrays.
import sys
import tempfile
from pathlib import Path

PLACEHOLDERS = {
    "POSTGRES_USER": {"your_username"},
    "POSTGRES_PASSWORD": {"your_password"},
    "S3_ACCESS_KEY": {
        "your_access_key",
        "your_access_key_here",
        "your_seaweedfs_access_key",
    },
    "S3_SECRET_KEY": {
        "your_secret_key",
        "your_secret_key_here",
        "your_seaweedfs_secret_key",
    },
    "AIRFLOW_ADMIN_USER": {"your_airflow_user"},
    "AIRFLOW_ADMIN_PASSWORD": {"your_secure_password_here"},
    "AIRFLOW_FERNET_KEY": set(),
    "JUPYTER_TOKEN": {"change_me_generate_a_real_token"},
    "MLFLOW_PG_PASS": set(),
    "DELTA_SHARING_TOKEN": set(),
}
LEGACY = {
    "S3_ACCESS_KEY": "lakehouse_s3",
    "S3_SECRET_KEY": "lakehouse_s3_secret",  # pragma: allowlist secret - public legacy default
    "MLFLOW_PG_PASS": "mlflow_password",  # pragma: allowlist secret - public legacy default
}
PERSISTENT = {
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "MLFLOW_PG_PASS",
    "AIRFLOW_FERNET_KEY",
}
CONTAINERS = (
    "postgres",
    "seaweedfs",
    "mlflow-server",
    "airflow-webserver",
    "jupyter",
    "delta-sharing",
)


def read_env(text):
    values = {}
    for line in text.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$", line)
        if not match:
            continue
        key, raw = match.groups()
        try:
            parts = shlex.split(raw, comments=True)
        except ValueError:
            raise ValueError(f"Cannot parse {key}; use a single-line value") from None
        value = " ".join(parts)
        # Single-quoted values are literal in both shell and Compose syntax.
        literal = re.fullmatch(r"\s*'[^']*'\s*(?:#.*)?", raw) is not None
        values[key] = (
            os.environ.get(key, value) if "$" in raw and not literal else value
        )
    return values


def docker_run(*args, timeout=5, check=False):
    binary = shutil.which("docker")
    if not binary:
        raise OSError("Docker CLI is unavailable")
    # Callers supply Docker arguments directly; no shell or user-provided command.
    return subprocess.run(  # nosec B603
        [binary, *args], capture_output=True, text=True, timeout=timeout, check=check
    )


def docker_json(*args):
    try:
        result = docker_run(*args)
        if result.returncode:
            raise ValueError()
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise ValueError(
            "Cannot inspect Docker state; credentials were not changed"
        ) from None


def docker_names(*args):
    try:
        result = docker_run(
            *args,
            "--format",
            "{{.Names}}" if args[0] == "container" else "{{.Name}}",
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError(
            "Cannot list Docker state; credentials were not changed"
        ) from None
    return set(result.stdout.splitlines())


def existing_state(root):
    try:
        ready = docker_run("info", "--format", "{{.ServerVersion}}")
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError(
            "Start Docker before configuring credentials; existing storage must be checked"
        ) from None
    if ready.returncode:
        raise ValueError(
            "Start Docker before configuring credentials; existing storage must be checked"
        )
    recovered = {}

    def recover(key, value):
        # Never choose a secret based on container inspection order.
        if key == "AIRFLOW__CORE__FERNET_KEY":
            key = "AIRFLOW_FERNET_KEY"
        if key not in PLACEHOLDERS or not value:
            return
        if key in recovered and recovered[key] != value:
            raise ValueError(
                f"Credential mismatch for {key} between existing sources; "
                "restore consistent original values before setup; credentials were not changed"
            )
        recovered[key] = value

    owned = []
    names = docker_names("container", "ls", "--all")
    selected = sorted(set(CONTAINERS) & names)
    for container in docker_json("inspect", *selected) if selected else []:
        config = container.get("Config", {})
        directory = (config.get("Labels") or {}).get(
            "com.docker.compose.project.working_dir"
        )
        if not directory or Path(directory).resolve() != root:
            continue
        owned.append(container)
        for entry in config.get("Env", []):
            key, _, value = entry.partition("=")
            recover(key, value)
    # A random Jupyter token may exist only in its private runtime file.
    if not recovered.get("JUPYTER_TOKEN") and any(
        c.get("Name") == "/jupyter" for c in owned
    ):
        try:
            result = docker_run(
                "exec",
                "jupyter",
                "jupyter",
                "server",
                "list",
                "--json",
                timeout=10,
            )
            for line in result.stdout.splitlines():
                try:
                    info = json.loads(line)
                except ValueError:
                    continue
                if info.get("token"):
                    recovered["JUPYTER_TOKEN"] = info["token"]
                    break
        except (OSError, subprocess.TimeoutExpired):
            pass
    profile = Path(
        os.environ.get("LAKEHOUSE_SHARING_PROFILE", root / "lakehouse.share")
    )
    if profile.exists():
        try:
            token = json.loads(profile.read_text())["bearerToken"]
        except (ValueError, KeyError):
            raise ValueError(
                "Cannot read the existing sharing profile; restore it before setup"
            ) from None
        recover("DELTA_SHARING_TOKEN", token)
    project = os.environ.get("COMPOSE_PROJECT_NAME") or re.sub(
        r"[^a-z0-9_-]", "", root.name.lower()
    )
    volumes = docker_names("volume", "ls") & {
        f"{project}_postgres-data",
        f"{project}_seaweedfs-data",
    }
    configured = any(
        (root / p).exists()
        for p in (
            "config/spark/spark-defaults.conf",
            "config/unity-catalog/server.properties",
        )
    )
    protected = (
        set(PERSISTENT) if owned or volumes or profile.exists() or configured else set()
    )
    for container in owned:
        protected.update(
            {
                "/airflow-webserver": {"AIRFLOW_ADMIN_USER", "AIRFLOW_ADMIN_PASSWORD"},
                "/jupyter": {"JUPYTER_TOKEN"},
                "/delta-sharing": {"DELTA_SHARING_TOKEN"},
            }.get(container.get("Name"), set())
        )
    return recovered, protected


def property_value(text, key):
    match = re.search(rf"^\s*{re.escape(key)}(?:\s*=\s*|\s+)(.*)$", text, re.M)
    return match.group(1).strip() if match else ""


def private_write(path, text):
    if path.is_symlink():
        raise ValueError(f"Refusing to replace symlink: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == text:
        path.chmod(0o600)
        return
    fd, name = tempfile.mkstemp(prefix=".credentials-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def configure(root):
    env_file = root / ".env"
    if env_file.is_symlink():
        raise ValueError("Refusing to replace a symlinked .env")
    created = not env_file.exists()
    text = (root / ".env.example").read_text() if created else env_file.read_text()
    values = read_env(text)
    recovered, protected = existing_state(root)
    configs = {
        "config/spark/spark-defaults.conf": {
            "spark.hadoop.fs.s3a.access.key": "S3_ACCESS_KEY",
            "spark.hadoop.fs.s3a.secret.key": "S3_SECRET_KEY",
        },
        "config/unity-catalog/server.properties": {
            "s3.accessKey.0": "S3_ACCESS_KEY",
            "s3.secretKey.0": "S3_SECRET_KEY",
        },
    }
    config_text = {}
    for rel, mapping in configs.items():
        path = root / rel
        if path.is_symlink():
            raise ValueError(f"Refusing a symlinked configuration: {rel}")
        config_text[rel] = (
            path.read_text()
            if path.exists()
            else Path(str(path) + ".example").read_text()
        )
        if path.exists():
            for prop, key in mapping.items():
                value = property_value(config_text[rel], prop)
                if value and value not in PLACEHOLDERS[key]:
                    recovered.setdefault(key, value)
    generated = []
    for key, placeholders in PLACEHOLDERS.items():
        current = values.get(key, os.environ.get(key, ""))
        invalid = (
            not current
            or current in placeholders
            or ((not protected or created) and current == LEGACY.get(key))
        )
        if not invalid:
            if recovered.get(key) and current != recovered[key]:
                raise ValueError(
                    f"Credential mismatch for {key} between local configuration and existing state; "
                    "restore the original value before setup; credentials were not changed"
                )
            values[key] = current
            continue
        value = recovered.get(key)
        if not value and key in protected:
            raise ValueError(
                f"Existing installation: restore {key} before setup; credentials were not rotated"
            )
        if not value:
            value = {"POSTGRES_USER": "lakehouse", "AIRFLOW_ADMIN_USER": "admin"}.get(
                key
            )
            if not value:
                value = (
                    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                    if key == "AIRFLOW_FERNET_KEY"
                    else secrets.token_hex(10 if key == "S3_ACCESS_KEY" else 32)
                )
            generated.append(key)
        if not re.fullmatch(r"[A-Za-z0-9_./:=+@,-]+", value):
            raise ValueError(
                f"Configure {key} explicitly in .env; recovered values must be shell/Compose-safe"
            )
        values[key] = value
        line = f"{key}={value}"
        pattern = rf"(?m)^\s*(?:export\s+)?{key}=.*$"
        text = (
            re.sub(pattern, lambda _: line, text)
            if re.search(pattern, text)
            else text.rstrip("\n") + "\n" + line + "\n"
        )
    # Store explicitly supplied environment credentials that were absent in .env.
    for key in PLACEHOLDERS:
        if not re.search(rf"(?m)^\s*(?:export\s+)?{key}=", text):
            value = values[key]
            if not re.fullmatch(r"[A-Za-z0-9_./:=+@,-]+", value):
                raise ValueError(f"Set {key} explicitly in .env")
            text = text.rstrip("\n") + f"\n{key}={value}\n"
    if created or "DASHBOARD_ALLOW_JUPYTER_LAUNCH" not in values:
        setting = "DASHBOARD_ALLOW_JUPYTER_LAUNCH=true"
        pattern = r"(?m)^DASHBOARD_ALLOW_JUPYTER_LAUNCH=.*$"
        text = (
            re.sub(pattern, setting, text)
            if re.search(pattern, text)
            else text.rstrip("\n") + "\n" + setting + "\n"
        )
    updates = []
    for rel, mapping in configs.items():
        contents = config_text[rel]
        for prop, key in mapping.items():
            value = property_value(contents, prop)
            desired = values[key]
            if value and value not in PLACEHOLDERS[key] and value != desired:
                raise ValueError(
                    f"Credential mismatch in {rel} ({prop}); existing configuration was not overwritten"
                )
            if not re.fullmatch(r"[A-Za-z0-9_./:=+@,-]+", desired):
                raise ValueError(
                    f"Keep {key} consistent in .env and service configuration"
                )
            line = f"{prop}={desired}"
            pattern = rf"(?m)^\s*{re.escape(prop)}(?:\s*=\s*|\s+).*$"
            contents = (
                re.sub(pattern, lambda _: line, contents)
                if re.search(pattern, contents)
                else contents.rstrip("\n") + "\n" + line + "\n"
            )
        updates.append((root / rel, contents))
    try:
        if (
            len(
                base64.b64decode(
                    values["AIRFLOW_FERNET_KEY"], altchars=b"-_", validate=True
                )
            )
            != 32
        ):
            raise ValueError()
    except ValueError:
        raise ValueError(
            "Invalid AIRFLOW_FERNET_KEY; restore the original key instead of rotating it"
        ) from None
    # Validate all planned changes before replacing any private file.
    private_write(env_file, text)
    for path, contents in updates:
        private_write(path, contents)
    print(
        "Local credentials ready in private .env; Spark and Unity Catalog credentials aligned."
    )
    if generated:
        print("Generated values for: " + ", ".join(generated))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        configure(args.root.resolve())
    except (OSError, ValueError) as error:
        print(f"Credential setup stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
