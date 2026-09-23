# Testing standard

open-lakehouse is a **reference architecture**. People adopt a reference
architecture precisely because they trust that the pieces have been proven to
work together — so the test suite is not an add-on, it is the product's core
claim. Companies will run this in production. The bar is therefore higher than a
"does it boot" hobby CI: **every version pin, every cross-layer contract, and
every golden rule is backed by a test that actually executes, and a skipped
test is a failure, not a pass.**

This document is the standard the CI implements against. If a change weakens a
guarantee here, the change is wrong, not the standard.

## Principles

1. **A pin is a tested claim, never a comment.** No jar/image/package version is
   "known good" until a test exercises the exact artifact on the exact runtime
   and asserts the behavior the pin exists to protect. The rationale for a pin
   (e.g. "Delta 4.3.0 NPEs through the UC connector") must exist as an
   *executable negative test*, so the reason survives after everyone who
   remembers it has moved on.
2. **A skip is a failure on the gated path.** `pytest.skip` when the stack is
   down is fine for a laptop; on the version-change and release paths a gate
   that did not run is red. Green must mean "ran and passed."
3. **Test the contract, not the smoke.** "Container started" proves nothing a
   customer cares about. We assert ACID semantics, exactly-once streaming with
   checkpoint recovery, governance enforcement (an unauthorized read is
   *denied*), time-travel, schema evolution, and multi-engine read parity.
4. **The golden rules are enforced by tests, not honor.** UC OSS is the only
   catalog; no JDBC-catalog path; Spark 4.1 only; Connect-first. Each has a
   test that fails if it regresses.
5. **Reproducible or it didn't happen.** Images are pinned by digest, jars by
   checksum, Python by lockfile. A green run today reproduces byte-for-byte.
6. **Deployment parity is in scope.** The `terraform/` (AWS) and
   `terraform-databricks/` paths are how this reaches production, so they are
   validated (plan/validate always; a smoke apply on the release path), not
   just the local Compose stack.

## Test tiers

| Tier | Runs | Docker? | Gate |
|------|------|---------|------|
| **T0 — Static invariants** | every PR | no | pin consistency (`verify-versions.sh`), golden-rule guards, config/doc drift, lint, secrets, compose `config` validate |
| **T1 — Unit** | every PR | no | pure Python logic, CLI arg handling, config generation |
| **T2 — Component** | every PR | ephemeral (testcontainers) | per-service behavior: SeaweedFS S3 conformance, Kafka produce/consume, UC REST, Postgres |
| **T3 — Integration / E2E** | version-change PRs, nightly, release | full stack via `./lakehouse` | the medallion end-to-end on the real pinned classpath: Kafka → Structured Streaming → Delta (bronze) → SDP (silver/gold), UC governance, MLflow, Delta Sharing |
| **T4 — Version-change gate** | any PR touching a pin | full stack, matrixed | candidate jar set proven; **negative** tests prove the known-bad versions fail; upgrade is evidenced |
| **T5 — Deployment parity** | release | Terraform validate + smoke apply | AWS + Databricks destinations reachable, UC-only, no JDBC |

T0–T2 run with no external infrastructure and gate **every** PR. T3+ need a
runner that can bring the stack up; they gate the paths where version/behavior
actually changes and run nightly so drift surfaces within a day.

## The version-change protocol

Changing any pin (jar, image, or package) is the highest-risk change in this
repo, so it has its own required procedure. "It looked like it worked once" is
not evidence.

1. **T0 stays green.** `scripts/tools/verify-versions.sh` proves the new version
   is named consistently across `download-jars.sh`, `spark-defaults.conf.example`,
   and `CLAUDE.md`, and that no forbidden version or JDBC-catalog path leaked in.
   Runs with no Docker; also catches a drifted *live* `spark-defaults.conf`.
2. **The positive gate runs and passes.** `tests/integration/test_delta_version.py`
   (and its siblings per layer) exercise write → append → read → time-travel on
   the candidate classpath and fail on `NoSuchMethodError`/`AbstractMethodError`.
   On this path the test **must not skip** — a skip fails the job.
3. **The negative gate holds.** The matrix runs the known-bad version and asserts
   it still fails the way the pin says it does (Delta 4.3.0 → UC-connector NPE;
   Delta 4.2.0 → no catalog-managed Delta). If a "bad" version starts passing,
   the pin's rationale is stale and must be re-documented — that is also a
   failure until a human reconciles it.
4. **The compatibility matrix is updated from the run**, not by hand
   (`docs/compatibility.md`), so the published support statement is generated
   evidence.
5. **The supply-chain locks are regenerated.** A jar bump reruns
   `./scripts/tools/download-jars.sh --lock`; an image bump reruns
   `./scripts/tools/pin-images.sh --lock`. The refreshed `jars.sha256` /
   `images.lock` are committed in the same PR, so the pinned version and the
   bytes that back it move together (see **Supply chain** below).

A pin bump merges only when 1–5 are green. This is what "beware of
compatibility; a lot of these are version pinned for a reason" looks like as an
enforced process rather than a hope.

## Current pins under test

Spark 4.1.0 (Scala 2.13 / Java 21) · Delta 4.3.1 · Iceberg 1.10.0 · UC OSS 0.5.0
(Spark connector 0.4.1 + client 0.5.1 + hadoop 0.5.1) · MLflow 3.14 · Kafka
(cp-kafka 7.5.0 = Apache 3.5) · AWS SDK v2 2.24.6 · PostgreSQL 16.

Known-bad, held by negative tests: Delta 4.3.0 (UC-connector NPE), Delta 4.2.0
(no catalog-managed Delta), UC connector 0.3.0 (pre-catalog-managed).

## Supply chain

A version pin names *what* to fetch; supply-chain hardening proves we got the
*bytes we expected* and records an inventory of everything we ship. Three
mechanisms, each with a committed lock that moves in lockstep with the pins:

- **Jar checksums — `scripts/tools/jars.sha256`.** `download-jars.sh` verifies
  every jar by **sha256 against the lock**, not just by size (a re-published or
  tampered artifact of similar size passes a size check but not a hash). A
  mismatch is always fatal — the file is deleted. Generate/refresh with
  `./scripts/tools/download-jars.sh --lock`; a cached-but-tampered jar is not
  trusted just because it is on disk. `verify-versions.sh` checks the lock
  *covers* every pinned jar (warn by default; `--require-checksums` makes a gap
  fatal). The E2E workflow runs `download-jars.sh --verify-only` as its own step.
- **Image digests — `scripts/tools/images.lock`.** A floating tag (`postgres:16`,
  `apache/spark:4.1.0-…`) can be re-pushed to different bytes; pinning
  `repo@sha256:…` makes the pull reproducible. `pin-images.sh` collects every
  external image from the compose `image:` lines and Dockerfile `FROM` lines
  (locally-built `lakehouse-*` images and build-stage aliases excluded),
  resolves each to a digest with `--lock` (docker/crane/skopeo), and `--check`
  reports coverage. Recording the digest is step one; enforcing it means
  rewriting the compose/Dockerfile reference to `repo@<digest>`.
- **SBOM.** CI generates an SPDX-JSON SBOM of the repo (`anchore/sbom-action`)
  and uploads it as a build artifact, then runs an informational vulnerability
  scan. The SBOM is the inventory we diff release-over-release and hand to
  downstream scanners.

**Current state / enforcement flip.** Both locks ship **unpopulated** — they are
generated on a networked machine (this repo's authoring environment had no
registry/Maven access) and committed. Until then, checksum and digest coverage
**warn** and only size/tag gate. Once populated, tighten CI to fail closed:
add `--require-checksums` to the jar gate and `--strict` to
`pin-images.sh --check`. Regenerating the locks on every pin bump is step 5 of
the version-change protocol above.

## Gate policy

- **Required on `main`:** T0, T1, T2. A PR cannot merge with any of these red.
- **Required when a pin file changes** (`download-jars.sh`,
  `spark-defaults.conf.example`, any `docker-compose-*.yml`, `CLAUDE.md`,
  `pyproject.toml`): T3 + T4, no skips.
- **Required when an IaC file changes** (`terraform/**`, `terraform-databricks/**`,
  `terraform-notebooks/**`): T5 static parity.
- **Nightly:** full T3 against `main` (slow tier included), so environmental drift
  (a moved image tag, a yanked jar) surfaces within a day rather than at the next
  release.
- **Release:** T0–T5, all green, before a tag is cut.

### Which workflow implements which tier

| Tier | Workflow | Trigger |
|------|----------|---------|
| T0, T1, security, SBOM | `.github/workflows/ci.yml` | every PR + push to `main` |
| T2 + T3 (full stack) | `.github/workflows/e2e.yml` | pin/stack-file PRs · nightly 07:00 UTC · dispatch |
| T4 (version-change negative gate) | `.github/workflows/version-matrix.yml` | pin-file PRs · dispatch |
| T5 (deployment parity, static) | `.github/workflows/deploy-parity.yml` | IaC PRs · dispatch |

T2 component tests (testcontainers: Postgres, Kafka) run inside the `e2e.yml`
full-stack job today — they need Docker but not the whole stack, so they could be
promoted to their own per-PR Docker job once the runner budget allows; the tier
boundary is defined so that split is a scheduling change, not a rewrite.

A T4 `fail` leg that unexpectedly passes fails the build: the pin's rationale in
`docs/compatibility.md` is then stale and a human reconciles it before the pin
can move.

## What we do not do

- We do not copy `lakehouse-at-home`'s CI. It is a learning fork: Iceberg+JDBC
  catalog, Spark 4.0/Java17, `spark://:7077`. Every one of those violates a
  golden rule here. We took the *shape* of its multi-stage E2E pipeline and
  rebuilt it against this stack's invariants.
- We do not let integration tests be `--ignore`d in CI and call the suite
  "passing." That is the exact gap this standard closes.
