"""Validated Spark SQL execution service."""

from __future__ import annotations

from time import perf_counter
from typing import Any

import pandas as pd


def execute_sql(sql: str) -> dict[str, Any]:
    """Execute SQL hook placeholder.

    Contract for the real implementation:
    - execute against Spark
    - return a Spark DataFrame in `spark_dataframe`
    - return a UI-friendly pandas projection in `dataframe`

    Current placeholder keeps `spark_dataframe` as None until Spark wiring lands.
    """
    start = perf_counter()
    sample = pd.DataFrame(
        {
            "region": ["North America", "Europe", "APAC"],
            "total_revenue": [12450.75, 10980.10, 8750.30],
        }
    )
    elapsed_ms = int((perf_counter() - start) * 1000)

    return {
        "sql": sql,
        "spark_dataframe": None,
        "dataframe": sample,
        "runtime_ms": elapsed_ms,
        "row_count": len(sample),
        "tables_used": ["sales.orders"],
        "error": None,
    }
