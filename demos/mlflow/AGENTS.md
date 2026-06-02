# AGENTS.md — demos/mlflow

Guidance for AI coding agents working in this demo directory.

## Scope

This directory implements a conversational Delta analytics assistant defined in `plans.md`.

Use the Fast Path assumptions by default:

* Delta tables are already available.
* Access may be through local paths, local catalog, remote catalog, or Unity Catalog OSS.
* Broad automatic discovery is deferred to hardening.
* Do not add synthetic/fake table generation unless the user explicitly asks for it.
* Keep MVP scope simple: NL -> Spark SQL -> execute -> render -> MLflow evaluation.

## Catalog Rules

* Unity Catalog means **Unity Catalog OSS only**.
* Do not assume or implement managed Databricks Unity Catalog behavior in this demo.

## MVP Implementation Order

Follow this sequence unless the user asks otherwise:

1. Streamlit UI shell
2. NL -> Spark SQL agent code
3. SQL validation + Spark execution
4. Result rendering + transparency
5. MLflow evaluation of query outcomes

## Safety Defaults

* Never execute unsafe SQL.
* Allow read-only query shapes (`SELECT`, `WITH`) and block mutating/DDL operations.
* Enforce row limits and timeouts before execution.
* Keep generated SQL visible to the user and editable before execution.

## Code Organization

Use the module boundaries in `plans.md`:

* `app/metadata`: ingestion, catalog adapters, schema registry
* `app/safety`: SQL validation and runtime guardrails
* `app/spark`: session and execution services
* `app/agents`: intent parsing and SQL generation
* `app/orchestration`: LangGraph workflow/state
* `app/ui`: Streamlit entrypoint
* `app/visualization`: Plotly chart helpers
* `app/observability`: MLflow tracing + telemetry
* `app/hardening`: deferred post-MVP expansion

## Development Conventions

* Keep code modular and independently testable.
* Prefer explicit interfaces between layers over tight coupling.
* Add or update tests in `tests/` for each meaningful behavior change.
* Keep prompts centralized under `app/prompts/`.
