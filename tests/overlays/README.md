# Test-only compose overlays (PR #0 isolation harness)

These are **per-base** Docker Compose overlays (one per `docker-compose-<svc>.yml`)
used only by the automated test suite and the E-07 lifecycle fixture. They are the
`$LAKEHOUSE_OVERLAY_DIR` referenced by the overlay activation contract
(implementation plan §1.16.1–§1.16.2, §1.17.1).

**They are never part of the default path.** `./lakehouse` uses them only when the
overlay variables are set (`LAKEHOUSE_TEST_RUN_ID`, `LAKEHOUSE_OVERLAY_DIR`,
`LAKEHOUSE_RESOURCE_SUFFIX`; optional `LAKEHOUSE_PORT_OFFSET`, `LAKEHOUSE_ENV_FILE`).

What each overlay does, and why:

- **Run-scopes every resource.** `container_name` gets the `-${LAKEHOUSE_RESOURCE_SUFFIX}`
  suffix; PostgreSQL databases become `ol_test_<runid>_{mlflow,airflow}`; the S3 bucket
  becomes `ol-test-<runid>`. Named volumes and networks are auto-scoped by
  `COMPOSE_PROJECT_NAME=ol-test-<runid>` (set by the CLI on activation), so they render as
  `ol-test-<runid>_<name>` with no default-project volume reachable (§1.18.1).
- **Isolated bridge networking.** Each base service that ships with `network_mode: host`
  is switched to a project-scoped bridge network via `network_mode: !reset null` +
  `networks: [default]`. Production base files keep their current networking untouched —
  this overlay is opt-in and is not the default path (§1.17.1, §1.18.8). Unity Catalog is
  already bridged on `lakehouse-network`; its overlay moves it onto the shared `default`
  network so the whole test stack can talk.
- **No new services.** An overlay only *overrides* services its base already declares
  (§1.16.2) — proven by U-57.
- **Unity Catalog stays on embedded H2.** The UC overlay isolates by container name + network
  only and never points UC at a test PostgreSQL database, so the `docker cp` H2 backup path
  is genuinely exercised (§1.16.4) — proven by U-58.
- **No published host ports by default.** On a bridge network with its own project name,
  services reach each other by container name, so nothing needs to be published to the host
  (§1.17.1 — `LAKEHOUSE_PORT_OFFSET` is optional). The base files that publish ports (UC,
  MLflow) have those mappings reset. A checkpoint that needs host reachability publishes only
  what it needs, at an offset.

## Storage (PostgreSQL + SeaweedFS) is shared Compose, not host-installed

Since PR #13, PostgreSQL and SeaweedFS are **Compose services** (`docker-compose-storage.yml`)
with named volumes — they are no longer host-installed. Storage is deliberately **unscoped**:
one shared instance on the fixed published ports `localhost:5432` / `localhost:8333` that every
run reaches, isolating instead by run-scoped **database and bucket names** inside it
(`ol_test_<runid>_{mlflow,airflow,iceberg_catalog}`, bucket `ol-test-<runid>`).

Consequences for the overlays:

- There is **no `docker-compose-storage.test.yml`**, and `OVERLAY_BASE_SERVICES` omits `storage`.
  `overlay_set_compose_args storage` special-cases to the base file only, so `start storage` /
  `stop storage` (and the `start all` storage arm) work under an active overlay without a
  missing-overlay-file error.
- The run-scoped service overlays sit on a project-scoped bridge network with no published
  ports, so they reach the shared storage from inside a container via
  `host.docker.internal:5432` / `:8333` (the `host-gateway` mapping) — **on purpose**, because
  the shared storage publishes those ports on the host.
