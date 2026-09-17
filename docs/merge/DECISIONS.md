# docs/merge/DECISIONS.md — architecture decisions pointer (T-0.4)

The D1–D8 decisions are already made and are **not** re-litigated in PR #13. This file is a pointer,
per Checkpoint 0 / absorbed Phase 0 (addendum §6). Authoritative text:

- **`option_a_implementation_plan.md` §3** (D1–D8) — the decisions with rationale.
- **`option_a_pr1_binding.md`** — the binding addendum for PR #13 (branch base, order, lifecycle
  re-ground, blast-radius, doc ownership, Phase 0 absorption). **Binding where anything disagrees.**

## The decisions that shape PR #13

| # | Decision | Bearing on PR #13 |
|---|---|---|
| **D1** | **Bridge networking** (§3.1) | Convert all services off `network_mode: host` to the shared `lakehouse-network`; address peers by container name; publish host ports. Client invariant `sc://localhost:15002` preserved (I-03). |
| **D2** | **UC → official `unitycatalog/unitycatalog:v0.5.0`** (§3.2, §1.12) | Replace the `newfrontdocker/…:v0.4.1` staging image (supply-chain hygiene + catalog-managed Delta). Gated by I-44/I-45; I-47 pins that Iceberg writes stay upstream-blocked. `v0.5.1` **not** adopted (no container). |
| **D3** | Delta Sharing proxy kept; MinIO-isms renamed | Later PR (not #13). |
| **D4** | Run-history stays S3 JSON initially | Later PR. |
| **D5** | **Jupyter token auth** (§3.5) | Enabled in PR #13 (T-1.14). |
| **D6** | Dashboard pipeline-run page cut from v1 | Later PR. |
| **D7** | `reset` orphan classification (four classes) | Shipped in PR #12. |
| **D8** | **Engine neutrality** (§3.8, §1.11) | PR #13 lands the config-level guards (U-35/U-36/U-40, I-42); the multi-engine demo itself is a later-PR exit criterion. |

Full context lives in the two source documents above; do not duplicate their rationale here.
