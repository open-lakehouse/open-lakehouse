# docs/merge/PROVENANCE.md — PR #13 base provenance

Records the exact base state PR #13 (network + storage foundation, plan Phases 1 + 2) is built on,
per Checkpoint 0 / absorbed Phase 0 (T-0.1, T-0.2). Created 2026-08-19.

## Base SHAs

| Ref | SHA | Notes |
|---|---|---|
| `main` | `4090bc3e10e8361352a33c0c0cd58f78b60e6e22` | tip is "Merge pull request #10"; does **not** yet contain #11 or #12 |
| PR #11 — `fix/mlflow-uv-lock-public-pypi` | `b85056277e84dd72a2941aeb6e17d276fcb97e71` | 1 commit ahead of `main`; touches only `demos/mlflow/uv.lock` |
| PR #12 — `feat/lifecycle-reset-safety` | `00d70c62e8258402f2c0fea88921beef2c527cb1` | 29 commits ahead of `main`, 0 behind; the lifecycle/data-safety work |
| **integration `feat/merge-cp-integration`** | `1105717cf3260651c23751f49468232410764c4a` | `main` → fast-forward to #12 → merge #11 (clean, `ort`, no conflicts) |
| **`feat/net-bridge-conversion`** | `1105717cf3260651c23751f49468232410764c4a` | branched off integration; Phase 1 work lands here |

## Branch topology (addendum §1)

```
origin/main (4090bc3, at PR #10)
  ├─ fix/mlflow-uv-lock-public-pypi (b850562)      → PR #11 (open)
  └─ feat/lifecycle-reset-safety (00d70c6)          → PR #12 (open)
        └─ feat/merge-cp-integration (1105717)  = main + #12 (ff) + merge(#11)
              └─ feat/net-bridge-conversion (1105717)  ← PR #13 Phase 1 lands here
                    (later: feat/merge-storage-seaweedfs for Phase 2)
```

**Base = `main` + PR #11 + PR #12** (addendum §1). Because #12 is 0 commits behind `main`, `main`
is an ancestor of #12, so `main + #12` fast-forwarded to #12's tip; #11's single `uv.lock` commit
then merged cleanly (different file, no conflict).

## Remote / PR state — verified via `gh` (read-only)

`gh pr list` confirms on `github.com/open-lakehouse/open-lakehouse`:
- **#12** (Phase 1.5 — Lifecycle & data safety) — **OPEN**
- **#11** (fix(mlflow): repoint demo uv.lock) — **OPEN**
- #10 and earlier — merged.
- No PR #13 exists yet (this work).

This is the addendum §1 "still open" case, so the integration branch was cut from a local merge of
`main` + #11 + #12. If #11/#12 gain review fixes after this tip, rebase/merge them into
`feat/merge-cp-integration` **before** the bridge conversion (Checkpoint 2) — do not build on a
stale lifecycle CLI.

## Attribution

CP-derived material ported in later checkpoints (the `terraform/spark-ecs` advertise-address
pattern for T-1.3, `make cache-deps` antecedents, the MinIO→SeaweedFS substitution) must carry
`Co-authored-by` trailers and be noted here as it lands.

## Phase 3 — Dashboard (`feat/merge-dashboard`, sibling PR)

Ported the containerized-lakehouse-platform **frontend** (Next.js 15 / React 19 / TS 5.7 /
Tailwind 3.4, `output: standalone`, Vitest 3.0) into `dashboard/`, with its Vitest suite from
CP `tests/frontend/` → `dashboard/tests/`. The verbatim import is one commit (CP-attributed
`Co-authored-by` trailers: Charlotte Blankenberg); the repoint, the T-3.7 fix, and the D6
feature flag are separate commits so the risky diff reads on its own.

Source → destination:

| CP source | open-lakehouse | Reworking |
|---|---|---|
| `frontend/` | `dashboard/` | verbatim import, then repoint |
| `frontend/src/app/api/minio/[...path]` | `dashboard/src/app/api/storage/[...path]` | renamed; `MINIO_URL`→`S3_ENDPOINT` (`seaweedfs:8333`) |
| (new) | `dashboard/src/app/api/health/storage` | HEAD-bucket probe (SeaweedFS has no `/minio/health/live`) |
| (new) | `dashboard/src/lib/features.ts`, `src/app/api/features`, `src/components/code-exec-guard.tsx` | D6 feature-flag plumbing |
| `tests/frontend/**` | `dashboard/tests/**` | verbatim; vitest `include` repointed to `./tests/**` |

Reworkings of note:
- **Repoint (T-3.2/3.3/3.4):** MinIO→SeaweedFS (`seaweedfs:8333`), `mlflow-server:5000`,
  `unity-catalog:8080`; bucket `lakehouse-data`→`${S3_BUCKET:-lakehouse}`; client "open UI"
  links → host ports (UC 8081, MLflow 5000, Spark UI 8082, Jupyter 8889, Sharing 8443);
  MinIO-console links dropped (SeaweedFS has no console).
- **T-3.7 (security):** `POST /api/pipelines` containment gained a trailing-separator
  boundary (`isInsidePipelinesDir`), closing the sibling-dir escape a bare
  `startsWith(base)` admitted. CP's own test that asserted `../../../etc/passwd` was allowed
  is inverted (F-08).
- **D6 / T-3.8:** the code-execution / write routes and the Pipelines + Notebooks pages ship
  **disabled** behind `DASHBOARD_ALLOW_CODE_EXECUTION` (default false), a documented demo
  toggle with loud warnings when enabled.
- **Neutrality (D8):** separate `docker-compose-dashboard.yml`, opt-in CLI arm, never started
  by `start all`. The sharing page's "external access" section was genericized (no
  cloudflared / tunnel specifics; `make share*` → `./lakehouse share *`).
