---
name: dashboard
description: Use when starting, configuring, or troubleshooting the open-lakehouse web dashboard — the read-only Next.js viewer over Unity Catalog, MLflow, SeaweedFS, and (optionally) Delta Sharing. Covers the code-execution feature flag, ports, env contract, and endpoints.
---

# Dashboard (read-only viewer)

The dashboard is a **read-only viewer**, not a control plane. It is a Next.js 15 /
React 19 app (ported from the containerized-lakehouse-platform frontend) that browses
Unity Catalog, MLflow, the SeaweedFS object store, service health, and — when the Delta
Sharing service is running — shares. It is an **opt-in optional service**: `./lakehouse
start all` deliberately does not start it (D8 neutrality).

Scope honesty (D8): the dashboard is a *viewer* of UC / MLflow / S3, not "the platform."
It reads only; it never writes to the warehouse in its default posture.

## Start / stop

```bash
./lakehouse start dashboard      # first run builds the Next.js image, then serves 127.0.0.1:3000
./lakehouse stop dashboard
./lakehouse logs dashboard
./lakehouse status --json        # services.dashboard: true|false
```

It binds to **127.0.0.1:3000 only** (least-privilege — never all interfaces).

### Building behind a proxy

Public npm is unreachable on some networks (TLS-intercepting proxy in docker builds).
The Dockerfile honors build args; supply the proxy only at invocation (committed defaults
stay public):

```bash
NPM_REGISTRY=<npm-proxy-url> NPM_STRICT_SSL=false ./lakehouse start dashboard
```

## Code-execution features — OFF by default (D6 / T-3.8)

The dashboard also *contains* a control-plane surface (running pipelines, executing
notebook cells) that runs arbitrary code / mutates state. These are **disabled by
default** and gated behind one flag:

```bash
DASHBOARD_ALLOW_CODE_EXECUTION=true ./lakehouse start dashboard   # trusted networks ONLY
```

When **off** (default):
- The Pipelines and Notebooks nav items are hidden; navigating to them shows a
  "disabled" notice.
- `POST /api/jupyter-exec`, `POST /api/pipelines/run`, `POST /api/pipelines`, and
  `DELETE /api/pipelines/history` return `403`.

When **on**:
- Those pages appear with a persistent red **"do not expose to an untrusted network"**
  banner, and the `./lakehouse start dashboard` arm prints a loud warning.

Enable it only on a trusted, non-exposed local machine. Even enabled, the dashboard has
no authentication of its own — combining code-execution + no auth + network exposure is
exactly the risk this flag exists to prevent. Re-enabling it as a first-class feature is
deferred to a future phase that adds dashboard authentication.

The path-traversal hardening on `POST /api/pipelines` (T-3.7: containment with a
trailing-separator boundary, so a sibling dir like `/app/pipelines-evil` is rejected) is
in force regardless of the flag.

## Endpoints it proxies (server-side, over the bridge)

| Route | Backend | Notes |
|---|---|---|
| `/api/uc/*` | `unity-catalog:8080` | UC REST proxy (read) |
| `/api/mlflow/*` | `mlflow-server:5000` | MLflow REST proxy (read) |
| `/api/storage/*` | `seaweedfs:8333` | object-store proxy (read; renamed from CP `/api/minio`) |
| `/api/delta-sharing/*` | `delta-sharing:8443` | optional; `503 unconfigured` when no token |
| `/api/jupyter/*` | `jupyter:8888` | notebook browsing |
| `/api/health/{storage,mlflow,delta-sharing}` | — | health probes; storage HEADs the bucket |
| `/api/health/{spark,airflow,ai-gateway}` | — | health probes for the rest of the stack (Spark master UI, Airflow API server, MLflow AI Gateway) |
| `/api/features` | — | read-only; reports whether code-execution is enabled |

The home page surfaces a health card for **every** OL service — SeaweedFS, Unity
Catalog, MLflow, Delta Sharing, Spark, Airflow, and the AI Gateway — plus an info
card for Kafka (TCP 9092, no web UI) and "open UI" links (Jupyter, Spark UI, MLflow,
UC, Airflow). Optional services that aren't started show as unhealthy/unknown; that
is expected. There are no dedicated nav pages for Kafka/Airflow/Spark — they have
their own UIs; the dashboard only shows health + a link (scope decision, see the PR).

Client "open UI" links point at host ports: UC `8081`, MLflow `5000`, Spark UI `8082`,
Jupyter `8889`, Delta Sharing `8443`.

## Env contract

Set in `docker-compose-dashboard.yml`: `UNITY_CATALOG_URL`, `MLFLOW_URL`, `S3_ENDPOINT`,
`S3_BUCKET`, `JUPYTER_URL`, `DELTA_SHARING_URL`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
(from `S3_ACCESS_KEY`/`S3_SECRET_KEY`), `AWS_REGION`, `JUPYTER_TOKEN` (optional),
`DELTA_SHARING_TOKEN` (optional), `PIPELINES_DIR`, `NODE_TLS_REJECT_UNAUTHORIZED=0`
(accepts the sharing server's self-signed cert), and `DASHBOARD_ALLOW_CODE_EXECUTION`
(default `false`). `tests/test_dashboard_config.py` (U-25) enforces that every env var read
in `dashboard/src` is declared here or is a Node/Dockerfile runtime var.

## Tests

- `dashboard/tests/**` — Vitest (run `npm test` inside `dashboard/`, or in CI). Includes
  F-08 (path-traversal → 400) and F-10 (feature-flag gating).
- `tests/test_dashboard_config.py` — static config contract (`pytest -m dashboard`), no
  Node/Docker required.

## Troubleshooting

- **Blank cards / all services "unknown":** the dashboard reaches services by bridge name;
  confirm the core stack is up (`./lakehouse status`) and on `lakehouse-network`.
- **Sharing page empty / "unconfigured":** the Delta Sharing service (its own optional PR)
  isn't running or no `DELTA_SHARING_TOKEN` is set — expected; the dashboard degrades
  gracefully.
- **First `start dashboard` is slow / fails offline:** it's building the Next.js image;
  pass `NPM_REGISTRY` if public npm is blocked.
