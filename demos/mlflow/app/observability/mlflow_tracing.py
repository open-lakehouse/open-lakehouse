"""MLflow tracing integration helpers."""

from __future__ import annotations

from typing import Any


def evaluate_query_outcome(
    prompt: str,
    sql: str,
    execution_result: dict[str, Any],
) -> dict[str, Any]:
    """Return placeholder evaluation metrics for a query execution outcome."""
    rows = int(execution_result.get("row_count", 0))
    has_error = execution_result.get("error") is not None
    safety_score = 0.0 if has_error else 1.0
    correctness_score = 0.8 if rows > 0 and not has_error else 0.5
    quality = "pass" if not has_error else "warn"

    return {
        "query_quality": quality,
        "correctness_score": correctness_score,
        "safety_score": safety_score,
        "notes": "Placeholder evaluator; replace with MLflow tracing/eval pipeline.",
        "prompt": prompt,
        "sql": sql,
        "rows": rows,
    }
