# Proxy-friendly image builds (Phase 6 Part A)

Makes the two package-installing local images — **Airflow** and **Jupyter** —
buildable behind an internal package proxy, using overridable build args that
**default to public PyPI**. Purely additive: with no variables set, every build
resolves exactly as before. This closes the airflow-build gap that PR #13's own
"Known issues" flagged (its `docker/airflow/Dockerfile` had no `ARG PIP_INDEX_URL`,
so its build could not reach a mirror and hit blocked public PyPI).

Base: `feat/net-bridge-conversion` (PR #13 trunk). Sibling of the Dashboard (#16),
Sharing (#15), and Demos (#14) branches — cut from the same trunk tip, never based
on each other. See `docs/merge/PR-fan-strategy.md`.

## Scope (Phase 6 rescoped 2026-08-23 — Part A only)

This is the **proxy-build-args** slice. The full air-gapped `./lakehouse setup
--offline` (pip-wheel + Maven/coursier vendoring, T-6.1 / I-26) is **deferred**:
field engineers build behind a proxy (which Part A covers), reproducibility already
comes from committed lockfiles + pinned images, and there is no zero-egress
deployment target today. Revisit only if a real air-gapped POC appears.

## What's in it

- **`docker/airflow/Dockerfile`** — `ARG PIP_INDEX_URL=https://pypi.org/simple`,
  `ARG PIP_TRUSTED_HOST=` (empty ⇒ no `--trusted-host`), and
  `ARG SPARK_DIST_URL=<Apache archive spark-4.1.0 tarball>` (the build curls the
  Spark distribution, so that fetch also needs a knob). pip installs use
  `--index-url` + the optional `--trusted-host`. **Version pins unchanged**
  (`pyspark==4.1.0` + the five provider pins).
- **`docker/jupyter/Dockerfile`** — already had `PIP_INDEX_URL`; adds
  `PIP_TRUSTED_HOST` the same way. Pins unchanged.
- **`docker/jupyter-hosted/Dockerfile`** — adds both pip args (Dockerfile-only;
  the local Compose stack does not build it).
- **`docker-compose-airflow.yml` / `docker-compose-notebooks.yml`** — forward the
  args from the environment with **public defaults** (`${PIP_INDEX_URL:-https://pypi.org/simple}`,
  `${PIP_TRUSTED_HOST:-}`, and `${SPARK_DIST_URL:-<Apache archive>}` for Airflow).
  The non-empty default form is deliberate: an empty `${VAR:-}` would override the
  Dockerfile default and break the public path.
- **`.env.example`** — commented, public-example proxy hint with a
  "never commit an internal proxy URL" warning.
- **`docs/deployment/proxy-builds.md`** — the how-to, including the
  npm-is-dashboard / Maven-is-`download-jars.sh` / MLflow-is-apt-only boundaries.
- **`docs/merge/PR-fan-strategy.md`** — Offline row rescoped to match.

The proxy is supplied **only at invocation** (`--build-arg` / env). No internal
proxy host appears in any committed file or in the branch history.

## Blast radius

**Breaks / changes behavior:** none. The default online build path is byte-for-byte
unchanged; the new args are inert unless set. No CLI, runtime, or version-pin change.

**Explicitly out of scope (documented, not coded):**
- **MLflow** — its image only `apt`-installs `postgresql-client` (no pip), so a
  `PIP_INDEX_URL` arg would be dead. An apt mirror is environment-specific and left
  to the operator.
- **npm** is the Dashboard sibling's (#16) `NPM_REGISTRY` / `NPM_STRICT_SSL`; **Maven
  JARs** are host-side via `scripts/tools/download-jars.sh` (`MAVEN_BASE_URL`).

## Known issues / follow-ups

- **`./lakehouse start notebooks` builds via proxy only on first build.** It runs
  `docker compose up -d` (no `--build`), so once `lakehouse-jupyter:spark-4.1.0`
  exists the proxy args no-op on that command. `start airflow` uses `up --build`
  and does not have this asymmetry. `proxy-builds.md` documents the explicit
  `docker compose … build` step to re-point an existing image. (A CLI `--build`
  for `start notebooks` would fix the asymmetry but is a CLI change beyond this
  slice.)
- **`SPARK_DIST_URL` must serve the same tarball layout.** The Airflow build's
  `mv /opt/spark-4.1.0-bin-hadoop3 …` assumes that top-level directory name;
  re-hosting the identical file is fine, a repackaged archive is not. Documented in
  `proxy-builds.md`.
- **Pre-existing, not from this branch:** `./lakehouse test` /
  `wait_for_service` probe Airflow's old `/health` endpoint and grep `"healthy"`;
  Airflow 3 moved it to `/api/v2/monitor/health`, so `test` reports a false-negative
  even when Airflow is healthy. This branch touches no CLI code — flagged for a
  later trunk fix.

## Verification

- **Static:** the diff is exactly the 8 in-scope files; `git log -p` over the
  branch range carries no internal proxy host; pins unchanged. `docker compose
  config` on both Compose files renders the **public defaults** when the variables
  are unset and **interpolates a proxy** when they are set.
- **Live build through a proxy** (public PyPI is blocked in this sandbox, so the
  proxy path is what gets exercised — the committed public default is validated by
  `compose config`): a fresh **`--no-cache` Jupyter build** succeeded through the
  proxy — proving the new `PIP_TRUSTED_HOST` (the proxy is TLS-intercepting; pip
  only completes because `--trusted-host` is injected) — installing the pinned
  versions (`pyspark 4.1.0`, `jupyterlab 4.3.0`, …). The **Airflow build** fetched
  its Spark distribution via `SPARK_DIST_URL` and installed the providers through
  the proxy.
- **Live bring-up:** Airflow (webserver/scheduler/triggerer) and Jupyter both came
  up healthy against the running bridge stack; Airflow's `/api/v2/monitor/health`
  reports metadatabase + scheduler + triggerer healthy; **Jupyter reaches Spark
  Connect** (`sc://spark-connect-41:15002`, `range(3).count() = 3`). The rest of
  the connectivity suite (PostgreSQL, SeaweedFS + S3 conformance, Kafka, Spark, UC +
  Iceberg REST) is green.

---

This pull request and its description were written by Isaac.
