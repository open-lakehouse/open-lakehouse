# PR #13 — Checkpoint 0 diagnosis (findings only, no implementation)

Verification of the plan's measured assumptions before any Phase 1/2 code, per the PR #13 kickoff
Checkpoint 0. Captured 2026-08-19 on `feat/net-bridge-conversion` (base `1105717`, = `main` + #12 +
#11). **Nothing here is implementation.** Where a plan claim is confirmed it says so; where it is
wrong it is flagged **[CORRECTION]**.

## 1. Networking status quo (§1.2)

**Host-mode inventory — derived from `docker-compose-*.yml`, not hardcoded:**

| File | `network_mode: host` lines | Services |
|---|---|---|
| `docker-compose-spark41.yml` | 3 (L5, L33, L62) | spark-master-41, spark-worker-41, spark-connect-41 |
| `docker-compose-kafka.yml` | 2 (L5, L16) | zookeeper, kafka |
| `docker-compose-mlflow.yml` | 2 (L42, L55) | mlflow-server, mlflow-agent (AI Gateway) |
| `docker-compose-airflow.yml` | 1 (L34) | airflow (single service block) |
| `docker-compose-notebooks.yml` | 1 (L24) | jupyter |
| **Total** | **9** | across **5** files |

> **[CORRECTION]** §1.2 prose says *"eight container definitions"* but its own breakdown
> (Spark ×3, Kafka ×2, Airflow ×1, MLflow ×2, Jupyter ×1) sums to **9**, which matches the grep.
> The count is **9**, not 8. U-02 must assert zero host-mode across all of these. (Kafka's two are
> `zookeeper` + `kafka`; MLflow's two are the tracking server + the AI Gateway agent — both real
> service defs, so 9 is correct.)

**Confirmed as stated by §1.2:**
- **UC is the only bridged service** — `lakehouse-network` appears only in
  `docker-compose-unity-catalog.yml`; `unity-catalog` publishes `8081:8080` (comment already notes
  the "8081 host, SeaweedFS uses 8080" port-collision strain — the §3.1 D1 argument).
- **SeaweedFS and PostgreSQL are in NO compose file** — no `image:` line references either; they are
  host-installed and reached via `host.docker.internal`. This is what T-1.2 changes.
- **`host.docker.internal`** appears in `docker-compose-spark41.yml` and `.env.example`
  (`POSTGRES_HOST=host.docker.internal`, `S3_ENDPOINT=http://host.docker.internal:8333`). T-1.6
  removes these; U-04 asserts zero outside docs.

## 2. Spark-on-bridge pattern is portable (§1.8) — CONFIRMED

`terraform/spark-ecs/docker/entrypoint.sh` is exactly the pattern T-1.3 must port:
- `resolve_task_ip()` reads the ECS metadata endpoint, **falling back to
  `hostname -i | grep -vE '^127\.'`** — which on a Docker bridge yields the container IP.
- Exports `SPARK_LOCAL_IP` **and** `SPARK_PUBLIC_DNS` to that IP.
- Master dispatch: `spark-class …master.Master --host "$BIND_IP"` where `BIND_IP=$SPARK_LOCAL_IP` —
  it **binds and advertises `--host`, and that value is the task IP, never `0.0.0.0`** (the exact
  §1.8 correction). Worker/Connect address the master by name (`spark://${MASTER_HOST}:${PORT}`).

Consequence: R-1 stays Low-Medium; T-1.3 ports a proven helper rather than inventing one. Ideal:
factor a shared helper so local Compose and ECS don't drift.

## 3. UC image & 0.5.0 upgrade (§1.12, §3.2)

- **Current image confirmed:** `docker-compose-unity-catalog.yml` L36 = `newfrontdocker/unitycatalog:v0.4.1`.
- **Iceberg-read-only claim confirmed in-repo:** `config/spark/spark-defaults.conf` and the UC
  compose comments already state UC OSS 0.4.x exposes no Iceberg write endpoints — matching §1.12.
- **[NOT VERIFIED THIS SESSION]** Whether official `unitycatalog/unitycatalog:v0.5.0` is currently
  pullable, whether `v0.5.1` still lacks a container, and the live catalog-managed-Delta behavior
  **could not be checked** — `gh` and Docker pulls were out of scope for this read-only checkpoint.
  These must be confirmed at the start of Checkpoint 3 (T-1.17/I-44) before the upgrade; if the
  container is missing or the upgrade is not non-breaking, **stop** (constraint 6).

## 4. SeaweedFS / UC operational specifics (§2.5) — CONFIRMED in `config/`

`config/unity-catalog/server.properties`:
- `s3.bucketPath.0=s3://lakehouse` — bucket **root**, not a sub-prefix (comment L21 documents it).
- `s3.sessionToken.0=not_used` — non-empty placeholder (comment L23–27: UC breaks on null).
- `s3.endpoint.0=http://localhost:8333` — a **host-mode endpoint** T-1.6 must rewrite to
  `http://seaweedfs:8333` on the bridge.

`config/spark/spark-defaults.conf`:
- **Both extensions present** (D8 / U-35): `IcebergSparkSessionExtensions,DeltaSparkSessionExtension`.
- **All three catalogs present** (D8 / U-36): `unity` (UCSingleCatalog), `iceberg`
  (SparkCatalog + RESTCatalog, read-only), `spark_catalog` (DeltaCatalog).
- `fs.s3a.multiobjectdelete.enable false` present (L51) — the T-2.6 re-test/remove candidate.
- UC + S3 endpoints hardcoded to `localhost:8081` / `localhost:8333` — host-mode assumptions the
  bridge conversion must revisit.

## 5. Lifecycle re-ground inventory (T-1.20, addendum §3) — findings for CP1+

PR #12 isolates by run-scoped **names** on **host-installed** Postgres/SeaweedFS. Moving both into
Compose with **named volumes** changes the target surface. Inventory to re-ground:

- **PostgreSQL databases** (unchanged set, but soon inside a `postgres` **service**):
  `mlflow`, `airflow`, `iceberg_catalog`, plus UC's backend (see below). `.env.example` confirms
  `ICEBERG_CATALOG_URI=…/iceberg_catalog`.
- **UC state — currently ephemeral H2 in-container.** `docker-compose-unity-catalog.yml` L47 has the
  `uc-data` mount **commented out** (`#- uc-data:/home/unitycatalog/etc/db`); only `uc-logs` is
  mounted. The `uc-data` **volume is declared** (L77). §1.15.1 / T-1.20(b): **mount `uc-data` in
  PR #13** and move backup/restore off the `docker cp`-of-H2 path.
- **Named volumes across base compose files:** `uc-data`, `uc-logs`, `mlflow-data`, `spark-data`,
  `spark-logs` (+ Airflow volumes) — plus the SeaweedFS + Postgres volumes T-1.2 introduces. Each
  must be re-derived and assigned in `reset`/`backup`/`restore` dry-run output (T-1.20(a)); `uc-logs`
  stays on the never-destroy list.
- **Overlay (T-1.5.0a–c):** run-scoped volumes via `COMPOSE_PROJECT_NAME` stay necessary; host
  DB-name guards alone no longer suffice once storage is Composed; runtime semantic validation
  (§1.18.2) must still fail closed. Re-prove I-28/I-29/I-30 shape + E-07 on the new topology
  (T-1.20(d)); skips do not count as passes.

## 6. Overlay carry-forward — proven on PR #12 vs must prove on PR #13 (addendum §8)

| Already proven on the overlay (#12) | Still must prove on the production path (#13) |
|---|---|
| Bridge DNS / published ports for **test** services | Full stack on the shared `lakehouse-network` bridge |
| Run-scoped volumes via `COMPOSE_PROJECT_NAME` | Default-project volumes for the new SeaweedFS + Postgres services |
| Runtime semantic gate on overlay `reset` | `reset`/`backup`/`restore` against **Composed** storage targets + mounted `uc-data` |
| — | Spark **with executors** on the bridge (I-01, the R-1 gate) |
| — | Kafka dual listeners, both directions (I-05 / I-06) |
| — | Host client `sc://localhost:15002` unchanged (I-03) |

The overlay is a **rehearsal**, not a free pass — the production conversion still has to clear the
right column.

## 7. Absorbed Phase 0 status

- **T-0.1 / T-0.2** — base SHAs + branch topology in `PROVENANCE.md`; golden `status --json` +
  unit baseline (**151 passed**, stack-down snapshot) in `baseline.json`. Done.
- **T-0.4** — `DECISIONS.md` written as a pointer to §3 + the addendum. Done.
- **T-0.5** — pytest markers `merge`, `storage`, `network`, `dashboard`, `sharing` are **already
  registered** in `pyproject.toml` (added by #12). Nothing to add.
- **T-0.3** — CP `make test` baseline **skipped** (best-effort per addendum §6); not a #13 blocker.

## 8. Net: diagnosis holds, with one correction

The plan's measured assumptions hold, with a single correction (**9** host-mode defs, not 8) and
two items deferred to a Docker-capable session (UC `v0.5.0` pullability + non-breaking check —
gated by I-44 at Checkpoint 3; the full network integration gates I-01…I-15 need a running stack).
No finding contradicts the plan enough to change Phase 1/2 scope. Ready to proceed to Checkpoint 1
(storage in Compose + begin lifecycle re-ground) on approval.

## Open items for the human (per kickoff constraint 5)

1. **Push/draft policy** — the "~2-week owner-away" window is stale (addendum §9). Branches are
   **local only**; nothing pushed. Confirm whether PR #13 should eventually open as a draft or stay
   local.
2. **`gh` access** — read-only `gh` is now configured in `.claude/settings.local.json`; remote state
   confirmed: **#11 and #12 open, #13 not yet created**. Mutating `gh` subcommands remain denied.
