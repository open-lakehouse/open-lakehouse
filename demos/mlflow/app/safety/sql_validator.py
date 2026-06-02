"""Spark SQL validation rules and allow/block checks."""

from __future__ import annotations

from typing import Any

BLOCKED_TOKENS = ("drop ", "delete ", "update ", "insert ", "alter ", "truncate ")
ALLOWED_PREFIXES = ("select", "with")


def validate_sql(sql: str, row_limit: int = 1000) -> dict[str, Any]:
    """Validate SQL for MVP safety and enforce a default row limit."""
    normalized_sql = " ".join(sql.strip().split())
    lowered = normalized_sql.lower()

    if not normalized_sql:
        return {"is_valid": False, "reason": "SQL is empty.", "normalized_sql": normalized_sql}

    if any(token in lowered for token in BLOCKED_TOKENS):
        return {
            "is_valid": False,
            "reason": "Blocked mutating or DDL SQL operation detected.",
            "normalized_sql": normalized_sql,
        }

    if not lowered.startswith(ALLOWED_PREFIXES):
        return {
            "is_valid": False,
            "reason": "Only SELECT/WITH statements are allowed.",
            "normalized_sql": normalized_sql,
        }

    if " limit " not in f" {lowered} ":
        normalized_sql = f"{normalized_sql} LIMIT {row_limit}"
        return {
            "is_valid": True,
            "reason": f"Valid SQL. Added default LIMIT {row_limit}.",
            "normalized_sql": normalized_sql,
        }

    return {
        "is_valid": True,
        "reason": "Valid SQL.",
        "normalized_sql": normalized_sql,
    }
