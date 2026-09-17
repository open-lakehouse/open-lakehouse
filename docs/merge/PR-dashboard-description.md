# Dashboard (Phase 3) — read-only web viewer

Ports the containerized-lakehouse-platform **frontend** into `dashboard/` as an
opt-in, read-only web viewer over Unity Catalog, MLflow, the SeaweedFS object
store, service health, and (when running) Delta Sharing.

**Base:** cut from the #13 trunk `feat/net-bridge-conversion` @ `952b5d6` (a fan
sibling — see `docs/merge/PR-fan-strategy.md`; not based on #14/#15).

## What this is

A Next.js 15 / React 19 app (TS 5.7, Tailwind 3.4, `output: standalone`,
Vitest 3.0). It is a **viewer**, not a control plane — it reads UC / MLflow / S3
and never writes to the warehouse in its default posture (D8 scope honesty). It
is **opt-in**: `./lakehouse start all` does not start it.

The home page surfaces a **health card for every OL service** (SeaweedFS, Unity
Catalog, MLflow, Delta Sharing, Spark, Airflow, AI Gateway), a Kafka info card
(TCP 9092, no web UI), and "open UI" links (Jupyter, Spark UI, MLflow, UC,
Airflow). Dedicated *nav pages* exist only for the data-plane services that CP
shipped (Catalog, Experiments, Storage, Sharing + gated Pipelines/Notebooks);
Kafka/Airflow/Spark keep their own UIs and are surfaced as health + link only —
see Decision points.

```bash
./lakehouse start dashboard      # first run builds the image; serves 127.0.0.1:3000
./lakehouse stop dashboard
```

## Commit shape (mechanical → substantive)

1. **Import CP frontend verbatim** (`Co-authored-by` Charlotte Blankenberg) — bulk, no behavior change.
2. **Repoint to SeaweedFS + bridge service names** — endpoints, bucket, env, client links, vitest paths.
3. **Compose + opt-in CLI arm + status/ports/help + overlay** — how it plugs into the platform.
4. **Close the `/api/pipelines` path-traversal (T-3.7)** + invert CP's F-08 test.
5. **Feature-flag off the code-execution / write routes + pages (D6 / T-3.8)** — the demo toggle.
6. **Skill, PROVENANCE, PR description, Python config tests.**

Read the risky diffs (4, 5) without wading through the ~11k-line bulk import.

## Security posture

- **Read-only by default.** The Pipelines + Notebooks pages and the four
  code-execution / write routes (`POST /api/jupyter-exec`, `POST /api/pipelines/run`,
  `POST /api/pipelines`, `DELETE /api/pipelines/history`) are **disabled** behind
  `DASHBOARD_ALLOW_CODE_EXECUTION` (default `false`). Disabled routes return `403`;
  the nav hides the pages. Enable only on a trusted, non-exposed network — it is a
  deliberate, warning-laden demo toggle (loud CLI warning + persistent in-UI banner).
- **Path traversal (T-3.7):** `POST /api/pipelines` containment now uses a
  trailing-separator boundary, rejecting sibling-dir escapes like
  `/app/pipelines-evil`. Enforced whether or not the flag is on. F-08 inverts CP's
  original "traversal allowed" assertion.
- **Least-privilege exposure:** binds `127.0.0.1:3000` only.
- **No internal specifics:** the sharing page's external-access section is
  tool-agnostic (no cloudflared / tunnel names; `./lakehouse share *`).

## Decision points (please weigh in)

1. **Code-execution posture — one env var; routes present-but-inert, NOT stripped.**
   With `DASHBOARD_ALLOW_CODE_EXECUTION` off (the default), the whole pipelines /
   notebooks / jupyter-exec surface still *exists and responds*, but returns `403`
   as the **first line** of each handler — before any code execution, outbound
   Jupyter call, shell, or filesystem write. The capability is therefore inert, but
   the endpoints are **not physically absent**: a direct request gets
   `403 {"error":"disabled"}`, not a `404` or connection-refused. (This is inherent
   to Next.js file-based routing — a `route.ts` is always mounted while the server
   runs; there is no separate per-feature port, and the container publishes only
   `127.0.0.1:3000`.)
   - *Why this way:* re-enabling for a demo is a single
     `DASHBOARD_ALLOW_CODE_EXECUTION=true` flip, not a re-port, and the gate is
     enforced **server-side** (proven by direct-HTTP integration tests) — it is not
     UI hiding. Only the exact string `"true"` enables it.
   - *Alternative not taken:* physically **stripping** the routes (genuine `404`,
     no handler at all) — smallest surface, but removes the toggle and means
     re-porting to bring the feature back.
   - *Revisit when:* the dashboard gains its own authentication, or a build with no
     code-execution code at all is wanted → switch to stripping.
2. **Read-only by default, opt-in service** — a UC/MLflow/S3 viewer, not started by
   `./lakehouse start all` (D8 neutrality). OK to keep opt-in?
3. **`package-lock.json` pinned to the public registry** — CP's lock resolved
   through an internal build-proxy; rewritten to `registry.npmjs.org` (integrity
   hashes unchanged) and scrubbed from history. The proxy is supplied only at build
   time via `--build-arg NPM_REGISTRY`.
4. **The Unity Catalog OSS web UI is enabled in the core UC service** (see Blast
   radius). It publishes no versioned release, so it's pinned to a rolling main
   build (`unitycatalog-ui:main-aadc6fc`) on host `3001`, reached via a `server`
   network alias the UI's proxy hardcodes. *Alternative:* keep it out of the core
   UC service and link the dashboard's UC card to the in-app `/catalog` page
   instead. *Revisit if:* a `main`-tagged image or an extra container in the
   default `start unity-catalog` is unwanted.

## Blast radius

Almost entirely new files (`dashboard/`, `docker-compose-dashboard.yml`,
`.claude/skills/dashboard/`, `tests/test_dashboard_config.py`, `tests/integration/test_dashboard.py`, the test overlay).
Shared touch-points are additive only: the `lakehouse` CLI (opt-in `dashboard`
arms + `status --json`), `scripts/lib/overlay.sh` (`OVERLAY_BASE_SERVICES`), and a
Phase-3 section appended to `docs/merge/PROVENANCE.md`.

**One deliberate exception to "purely additive":** this PR also **enables the
Unity Catalog OSS web UI** (`docker-compose-unity-catalog.yml` — previously a
commented-out stub), so `./lakehouse start unity-catalog` now also starts a
`unity-catalog-ui` container (host `3001`; UC exposed under a `server` network
alias the UI's proxy requires; run-scoped in the UC test overlay). This is what
makes the dashboard's "Unity Catalog" card open a real UC UI rather than the
API root's "Hello, Unity Catalog!" greeting. If a reviewer prefers to keep the
UI out of the core UC service, the fallback is to link the card to the in-app
`/catalog` page instead — see Decision points.

## Verification

- `tests/test_dashboard_config.py` (5 tests, `pytest -m dashboard`): port
  contract, env-var contract (U-25), code-execution-off-by-default (U-26 / D6),
  neutrality (U-38 / D8), core-compose isolation.
- Vitest `dashboard/tests/**` — 69 tests, incl. F-08 (traversal → 400) and F-10
  (19 flag-gating cases: every gated route 403 when off; flag strictness — only
  exact `"true"` enables).
- `tests/integration/test_dashboard.py` (`integration`+`dashboard` markers; skips
  when the container is down): every gated route hit **directly over HTTP** → 403
  when off (API-layer enforcement, not UI hiding); read-only reachability
  (I-16…I-19); asserts the container publishes **only `127.0.0.1:3000`**.
- `bash -n` + `shellcheck` clean on the CLI; base and run-scoped overlay both
  render via `docker compose config`.
- Verified live **both ways**: flag OFF → 8/8 integration pass (all gated routes
  403); flag ON → the gate un-gates. Full docker build (npm proxy) +
  `./lakehouse start dashboard` on the live stack + browser walk-through; `tsc` clean.

This pull request and its description were written by Isaac.
