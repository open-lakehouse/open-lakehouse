# Automatic local credentials

Start Docker, then bootstrap a fresh Compose installation:

```bash
./lakehouse setup --credentials-only
./lakehouse start storage
./lakehouse setup
```

The first command needs Python 3.10+ and a reachable Docker daemon. It prepares
credentials and configuration without downloading JARs or starting services.
Storage starts next because the full setup command provisions its database.
Ordinary `./lakehouse setup` also prepares credentials; `start storage` and
`start all` check them before creating persistent storage.

Setup generates missing PostgreSQL, S3, Airflow administrator, Airflow Fernet,
Jupyter, MLflow database and Delta Sharing credentials. Generated passwords and
tokens use cryptographic randomness. The default local administrator names are
`lakehouse` (PostgreSQL) and `admin` (Airflow).

Secrets stay in the ignored `.env`, `config/spark/spark-defaults.conf` and
`config/unity-catalog/server.properties`, with owner-only permissions (0600).
S3 credentials match across all three files. Setup prints key names, never values.
Read these private files locally when you need a login; do not paste them into
issues or commit them. Back them up privately along with your stored data.

## Existing installations

Configured values are preserved, including an explicit
`DASHBOARD_ALLOW_JUPYTER_LAUNCH=false`. Repeating setup leaves unchanged files and
credentials intact. The old public S3/MLflow demo defaults are replaced only on a
fresh installation; setup does not rotate credentials for existing storage.

When a value is missing, setup can recover it from this checkout's Compose
containers, existing Spark/Unity Catalog configuration, the Jupyter runtime or
`lakehouse.share`. It does not adopt another checkout's container credentials.
An existing volume, container, sharing profile or private service configuration
marks an installation as existing. If a required persistent credential cannot
be recovered, setup stops and identifies the key to restore. Restore its original
value from your private backup before retrying. A configured value that disagrees
with recovered existing state also stops setup before any private file is written,
including when the container is stopped. The error identifies only the key, never
either value. Missing/template values still use the existing recovery path.
Recovery also rejects disagreements between owned containers, between Airflow's
Fernet environment aliases, or between a container and the sharing profile; it
never chooses a value based on inspection order. Single-quoted `.env` values
containing `$` remain literal even if the parent environment contains the same key.
Conflicting S3 configuration also stops setup rather than choosing a new password.
Container environment is evidence of its creation-time configuration, not proof of
current database authentication after a manual password change. Resolve conflicts
privately against the actual service and backups; setup does not reset passwords.

Setup requires Docker inspection to succeed, including when the containers are
stopped. Do not remove volumes or invent replacement database passwords to bypass
a recovery error. For host-installed or remote storage, supply its actual
credentials in `.env` before running setup; this helper configures local Compose
services, not an external database password reset.

Explicit `LAKEHOUSE_ENV_FILE` and test overlays own their configuration and bypass
this local bootstrap.

## Dashboard and Jupyter

Setup supplies one shared `JUPYTER_TOKEN` to the notebook server and dashboard,
and enables `DASHBOARD_ALLOW_JUPYTER_LAUNCH` when the setting is absent. Existing
explicit choices are preserved. Automatic browser sign-in also requires the
separate dashboard Jupyter-launch feature; credential setup alone does not add
that route. Recreate the dashboard and Jupyter containers after changing their
environment. Setup does not enable dashboard code execution or add authentication
to otherwise unauthenticated service APIs. Use this convenience with a trusted
local dashboard; it does not add a public deployment authentication layer.

## Regression checks

```bash
poetry run pytest tests/test_local_credentials.py -q
LAKEHOUSE_TEST_FRESH_INSTALL=1 poetry run pytest tests/integration/test_secure_local_setup.py -q -s
# Optional Intel emulation on an ARM Docker host:
LAKEHOUSE_TEST_FRESH_INSTALL=1 LAKEHOUSE_TEST_PLATFORM=linux/amd64 poetry run pytest tests/integration/test_secure_local_setup.py -q -s
```

The opt-in check starts only isolated PostgreSQL and SeaweedFS containers on
random loopback ports with empty temporary storage. It checks successful generated
credentials, rejection of incorrect credentials and stability across a rerun.
It removes only its own containers and network. This is a credential/bootstrap
check, not a fresh installation of every lakehouse service.

### Docker-free unit checks

```bash
python -m pytest tests/test_local_credentials.py --noconftest -q -p no:cacheprovider
```

This module supplies its own fake Docker CLI and fixtures. `--noconftest` avoids
loading the unrelated shared Spark fixtures. It checks mismatched credentials for
all supported keys, running/stopped container inspection, Fernet alias recovery,
no writes (including permissions/mtime), redacted errors and unchanged matching
credentials. It does not authenticate against live services.

### macOS / OrbStack checks (real containers, not run by the unit checks)

Start OrbStack and confirm `docker info` succeeds in the intended Docker context.
The opt-in fresh-storage integration commands above also work with OrbStack; use
native ARM first on Apple Silicon, then optionally `linux/amd64`. They validate
real PostgreSQL/S3 authentication but do not reproduce the fixed-name container
recovery path, because they deliberately use isolated container names.

To check that path, use a disposable checkout and an otherwise empty Docker
context/VM where `postgres`, `seaweedfs` and the other fixed service names are
unused. Do not run this experiment against your existing installation:

1. Run `./lakehouse setup --credentials-only`, then `./lakehouse start storage`.
   Create a small database table and an S3 object as data-preservation sentinels.
2. Privately back up the three generated configuration files. Change only
   `POSTGRES_PASSWORD` in the disposable `.env` to a synthetic different value.
   Record hashes, modes and mtimes of all three files without displaying contents.
3. Run `./lakehouse setup --credentials-only`. Expect a nonzero exit and an error
   naming `POSTGRES_PASSWORD`, with no values. Verify all three files are unchanged
   from step 2 and the sentinels remain accessible with the original credentials.
4. Stop only the disposable PostgreSQL container (do not remove it) and repeat the
   conflict check. Expect the same rejection and unchanged files.
5. Restore the backed-up `.env`, restart the disposable container, and repeat
   credentials-only setup. Expect success and unchanged credentials/files.
6. Repeat with `S3_SECRET_KEY` changed only in `.env`; expect rejection before
   either Spark or Unity Catalog configuration is changed. Restore the backup.

On an existing installation, limit verification to a privately backed-up,
unchanged credentials-only rerun and normal service authentication. A reported
conflict is a reason to investigate, not to recreate containers, remove volumes
or rotate passwords automatically. No volume deletion is needed for these checks.
