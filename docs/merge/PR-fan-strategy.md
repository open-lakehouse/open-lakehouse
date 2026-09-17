# CP-feature merge — PR fan strategy (Phases 3–7 on an unmerged #13)

**Purpose.** Plan the CP-feature merge (Phases 3–7 of the Option-A plan) as a set of small,
independently reviewable PRs **without waiting for #13 to land in `main`**. The Option-A §4
delivery section collapses Phases 3–7 into one "later CP-feature PR"; that PR would be
unreviewable (a Next.js app + a Delta Sharing server + 10 demos + offline tooling + a docs
overhaul in one diff). This note replaces that with a **fan**.

## Constraint we are designing around

- We **cannot merge** into `main` (owner-controlled). #11, #12, #13 stay open indefinitely.
- Everything in Phases 3–6 depends on #13 at both code and runtime level (bridge networking,
  Compose storage, UC 0.5.0, Connect-first). So **nothing can target `main` yet.**
- Therefore the work hangs off #13. The goal is to make that a **shallow fan**, never a deep
  chain, and to keep each PR reviewable in isolation.

## Topology — a fan, not a chain

```
origin/main ──(can't merge)──► untouched
   └─ feat/merge-cp-integration        (= main + #11 + #12)          ← base of #13
        └─ feat/net-bridge-conversion  (= + #13)  ◄── THE TRUNK for all feature work
              ├─ feat/merge-dashboard     → Dashboard PR   (Phase 3)   ┐
              ├─ feat/merge-sharing       → Sharing PR     (Phase 4)   │ parallel siblings,
              ├─ feat/merge-demos-docs    → Demos PR       (Phase 5)   │ NONE based on another
              ├─ feat/merge-offline       → Offline PR     (Phase 6)   ┘
              └─ feat/merge-docs-ci       → Docs/CI PR     (Phase 7 — depends on 3–6, lands last)
```

**The trunk is `feat/net-bridge-conversion` (the #13 head).** Every feature branch is cut from
the *same* trunk tip and each opens a PR whose **base is the trunk** — so the PR diff shows only
that phase's changes, not #13's ~45 commits. Feature branches are **siblings**: a change to one
never forces a rebase of another. Max base depth is 3 (`main` → integration → #13 → fan), which
is acceptable because the fan itself is flat.

When #13 eventually lands in `main`, **retarget every feature PR's base to `main`**, rebase each
onto `main`, and the fan flattens into ordinary trunk-based development. Nothing else changes.

## The PRs

Phases 3–6 touch almost entirely **disjoint, mostly-new file trees**, which is what makes the fan
safe. Task IDs (`T-3.x` …) reference the Option-A implementation plan.

| PR (branch) | Scope | File surface | Depends on | Exit criteria |
|---|---|---|---|---|
| **Dashboard** — `feat/merge-dashboard` (Phase 3) | Port CP `frontend/` → `dashboard/` (Next.js/React), re-point env to bridge names, `docker-compose-dashboard.yml`, add `dashboard` CLI service, **fix the `/api/pipelines` path-traversal hole (T-3.7)**, **feature-flag off the RCE pages (T-3.8, D6)**, `dashboard` skill | ~all **new** (`dashboard/`, new compose, new skill); **shared:** `lakehouse` (CLI service arm), `status --json` | **#13** | `./lakehouse start dashboard` serves read-only on `127.0.0.1:3000`; Vitest green; RCE pages disabled by default; no path-traversal |
| **Delta Sharing** — `feat/merge-sharing` (Phase 4) | Port `docker/delta-sharing/` + `url-rewriter-proxy.py`, repoint S3 → `seaweedfs:8333`, `docker-compose-sharing.yml`, `scripts/sharing/`, `./lakehouse share`, `delta-sharing` skill, **document the upstream signer bug (T-4.8)** | ~all **new**; **shared:** `lakehouse` (CLI + `share` command), `status --json` | **#13** | `./lakehouse share start` serves 8443; presigned URLs re-signed for SeaweedFS (modes B/C 200); profile generates |
| **Demos** — `feat/merge-demos-docs` (Phase 5) | Port 10 notebooks → `demos/` on **Spark Connect**, demo contract + `teardown.sh`, **build `unity-catalog-multi-engine` for real (T-5.6, D8 exit criterion)**, widen per-demo teardowns (T-5.9), keep `sync_to_uc.py`/`clean_tables.py` | mostly **new** under `demos/`; **shared:** per-demo `teardown.sh` only | **#13**; **soft** on Sharing (T-5.4 folds sharing notebooks — see note) | Each demo runs top-to-bottom via `sc://localhost:15002`; multi-engine demo: DuckDB **and** PyIceberg read one table via the Iceberg REST endpoint; teardowns leave zero S3 residue |
| **Offline** — `feat/merge-offline` (Phase 6) | `./lakehouse setup --offline` (pip wheels + Maven/coursier), **merge proxy build-args (`ARG PIP_INDEX_URL`, `NPM_REGISTRY`…) into Dockerfiles (T-6.2)** — this also closes the airflow-build gap, `docs/deployment/offline.md` | **shared:** Dockerfiles (`airflow`, `mlflow`, `jupyter`, `dashboard`), `lakehouse` (setup flag) | loosely **#13** | Cold build works behind a proxy via `--build-arg`; committed defaults stay public (`https://pypi.org/simple`), proxy supplied only at invocation |
| **Docs/CI** — `feat/merge-docs-ci` (Phase 7) | `CLAUDE.md` (stack/pins/ports/neutrality statement), `README`, resolve the `architecture.md`↔`CLAUDE.md` format contradiction (T-7.11), `NOTICE`, **CI: `docker compose config` for all compose files + dashboard Vitest (T-7.4)**, port hygiene tests | **heavy overlap** with #13 docs/skills | **#13 + Dashboard + Sharing + Demos + Offline** | Docs describe the merged world; CI green on every compose file; neutrality statement present |

**Note on the one soft cross-dependency:** Phase 5's `T-5.4` folds the sharing notebooks into
`demos/delta-sharing/`. Keep that *one task* out of the Demos PR and land it as a tiny follow-up
after Sharing merges — so Demos and Sharing stay fully independent siblings. Everything else in
Phases 3–6 is genuinely parallel.

## Reviewability rules (non-negotiable)

1. **One subsystem per PR**, bounded file scope. If a phase is large, split *mechanical* from
   *substantive*: e.g. Dashboard = "import CP `frontend/` verbatim (mechanical, `Co-authored-by`)"
   as one commit, then "re-point to bridge + fix path-traversal + feature-flag" as separate
   commits, so a reviewer reads the risky diff without wading through the bulk import.
2. **Base every feature PR on the trunk (`feat/net-bridge-conversion`)**, never on `main` — that
   keeps the PR diff to the phase only, not #13's commits.
3. **Additive only.** No behavior change to existing services (Option-A §4: "purely additive").
   Risky endpoints ship **disabled** (D6). This is what lets these merge in any order.
4. **Self-contained.** Each PR carries its own compose file, CLI service arm, skill doc, tests,
   and `docs/merge/PROVENANCE.md` attribution for ported CP code.
5. **Draft until reviewed.** The window is for building, not landing.
6. **Green bar per PR:** unit + security + that phase's own tests. Integration stays out of CI.
7. **Size cap:** if a single PR's substantive (non-mechanical, non-generated) diff exceeds
   ~600 lines, split it further.

## The two collision hotspots — and the protocol

Because these are otherwise disjoint, only **two files** cause cross-PR conflicts:

- **`lakehouse` CLI dispatch.** Dashboard, Sharing, and Offline each add a service/command across
  the ~7 CLI sites. These are **additive `case`-arms**, so conflicts are trivial. Protocol:
  land/rebase the CLI-touching PRs **one at a time**; whoever rebases second re-applies their arm.
- **`CLAUDE.md` / skills / `status --json`.** Feature PRs make only the **minimal** status/CLI
  additions they need. The **big doc rewrite is owned exclusively by the Docs/CI PR (Phase 7)**,
  which lands last — so feature PRs never fight over prose.

Everything else (new dirs, new compose files, new skills) has zero overlap.

## Rebase discipline while #13 is unmerged

1. `git config rerere.enabled true` — records conflict resolutions so each restack replays them.
2. Cut every feature branch from the **same** trunk SHA; record it in the PR body.
3. **When #13 (the trunk) gains review fixes**, advance `feat/net-bridge-conversion`, then for each
   feature branch:
   ```bash
   git rebase --onto feat/net-bridge-conversion <old-trunk-sha> feat/merge-<phase>
   ```
   These are independent and usually clean (features are disjoint from #13's files).
4. **Feature branches never rebase onto each other** — that's the whole point of the fan.
5. **When #13 lands in `main`:** retarget each feature PR base to `main`, run the same
   `git rebase --onto origin/main feat/net-bridge-conversion feat/merge-<phase>`, retire the trunk
   branch. The stack depth drops to 1.

## Recommended order to *start* (all parallel, but stagger the CLI-touching ones)

1. **Demos** first — highest user value, touches the CLI least (only per-demo files), and
   unblocks the D8 multi-engine exit criterion.
2. **Dashboard** and **Sharing** next, in parallel — biggest imports; land their CLI arms one at a
   time.
3. **Offline** any time — mostly Dockerfile/CLI plumbing; pull it forward if a proxy-only build is
   blocking another PR (it closes the airflow-build gap).
4. **Docs/CI** last — it documents and CI-checks all of the above.

## What this buys us

- Every PR is a focused, additive, reviewable diff against a stable trunk — no 45-commit mega-diffs.
- The owner can review and merge them **in any order** once #13 lands, because they don't depend
  on each other.
- Reconciliation cost stays bounded: a change anywhere (including in #13) triggers at most a flat
  set of independent `rebase --onto`s, aided by `rerere`, never a cascading chain.

---

This plan and its description were written by Isaac.
