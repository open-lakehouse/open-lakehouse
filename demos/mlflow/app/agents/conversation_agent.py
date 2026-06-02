"""Top-level conversational agent entrypoints."""

from __future__ import annotations

from typing import Any


def generate_sql_from_nl(prompt: str, tables: list[str] | None = None) -> dict[str, Any]:
    """Return placeholder NL -> Spark SQL output for UI integration."""
    normalized_prompt = prompt.strip().lower()
    available_tables = tables or ["sales.orders"]
    primary_table = available_tables[0]

    if "revenue" in normalized_prompt and "region" in normalized_prompt:
        sql = (
            "SELECT region, ROUND(SUM(revenue), 2) AS total_revenue "
            f"FROM {primary_table} GROUP BY region ORDER BY total_revenue DESC"
        )
        explanation = "Aggregate revenue by region in descending order."
        tables_used = [primary_table]
    elif "top" in normalized_prompt and "customer" in normalized_prompt:
        sql = (
            "SELECT customer_id, ROUND(SUM(revenue), 2) AS total_revenue "
            f"FROM {primary_table} GROUP BY customer_id "
            "ORDER BY total_revenue DESC LIMIT 10"
        )
        explanation = "Return top customers ranked by total revenue."
        tables_used = [primary_table]
    else:
        sql = f"SELECT * FROM {primary_table} LIMIT 100"
        explanation = "Fallback SQL used while advanced agent generation is pending."
        tables_used = [primary_table]

    return {
        "sql": sql,
        "explanation": explanation,
        "tables_used": tables_used,
    }
