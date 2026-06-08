"""Variant A Streamlit scaffold for NL -> Spark SQL demo.

This UI is intentionally simple and includes placeholder hook boundaries for:
- app.agents.conversation_agent
- app.safety.sql_validator
- app.spark.query_executor
- app.observability.mlflow_tracing
"""

from __future__ import annotations

import base64
import importlib
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if TYPE_CHECKING:
    from app.config.settings import AppSettings

APP_TITLE = "Open Lakehouse Analytics Assistant"
APP_SUBTITLE = "Natural language -> Spark SQL -> Execute -> Render -> Evaluate"
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
MLFLOW_LOGO_PATH = Path(
    "/Users/jules/.cursor/projects/Users-jules-git-repos-open-lakehouse/assets/"
    "image-943e358b-ae73-4707-a101-8eb0f1dd5ce1.png"
)
MLFLOW_LOGO_FALLBACK_PATH = ASSETS_DIR / "mlflow-logo-badge.svg"
CODEX_LOGO_URL = (
    "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/"
    "packages/static-avatar/avatars/codex.webp"
)
CODEX_LOGO_FALLBACK_PATH = ASSETS_DIR / "codex-agent-logo-badge.svg"
LOGO_BOX_WIDTH_PX = 220
LOGO_BOX_HEIGHT_PX = 88

SAMPLE_QUESTIONS = [
    "Show total revenue by region",
    "Top 10 customers by revenue this quarter",
    "Monthly order trend for the last 90 days",
]

DEFAULT_TABLES = [
    "sales.orders",
    "sales.customers",
    "finance.invoices",
]


def _call_hook(module_name: str, function_name: str, **kwargs: Any) -> Any:
    """Call a project hook if it exists; otherwise return None."""
    try:
        module = importlib.import_module(module_name)
        hook = getattr(module, function_name, None)
        if callable(hook):
            return hook(**kwargs)
    except Exception:
        # Keep UI resilient while backend hooks are still being implemented.
        return None
    return None


def _placeholder_generate_sql(prompt: str) -> dict[str, Any]:
    prompt_lower = prompt.lower()
    if "region" in prompt_lower and "revenue" in prompt_lower:
        sql = (
            "SELECT region, ROUND(SUM(revenue), 2) AS total_revenue "
            "FROM sales.orders GROUP BY region ORDER BY total_revenue DESC"
        )
        explanation = "Aggregates total revenue by region."
        tables_used = ["sales.orders"]
    else:
        sql = "SELECT * FROM sales.orders LIMIT 100"
        explanation = "Fallback query while SQL generation hook is not implemented."
        tables_used = ["sales.orders"]
    return {"sql": sql, "explanation": explanation, "tables_used": tables_used}


def _placeholder_validate_sql(sql: str) -> dict[str, Any]:
    blocked = ("drop ", "delete ", "update ", "insert ", "alter ", "truncate ")
    sql_lower = sql.lower().strip()
    if any(token in sql_lower for token in blocked):
        return {"is_valid": False, "reason": "Blocked SQL operation detected."}
    if not (sql_lower.startswith("select") or sql_lower.startswith("with")):
        return {
            "is_valid": False,
            "reason": "Only SELECT/WITH statements are allowed in MVP.",
        }
    return {"is_valid": True, "reason": "SQL passed placeholder validation."}


def _placeholder_execute_sql(sql: str) -> dict[str, Any]:
    start = time.perf_counter()
    data = {
        "region": ["North America", "Europe", "APAC"],
        "total_revenue": [12450.75, 10980.10, 8750.30],
    }
    df = pd.DataFrame(data)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return {
        "dataframe": df,
        "runtime_ms": elapsed_ms,
        "row_count": len(df),
        "tables_used": ["sales.orders"],
        "error": None,
        "sql": sql,
    }


def _placeholder_mlflow_eval(
    prompt: str,
    sql: str,
    execution_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "query_quality": "pass",
        "correctness_score": 0.82,
        "safety_score": 1.0,
        "notes": "Placeholder MLflow evaluation until tracing/eval hooks are wired.",
        "prompt": prompt,
        "sql": sql,
        "rows": execution_result.get("row_count", 0),
    }


def _initialize_session_state() -> None:
    from app.utils.helpers import generate_request_id

    st.session_state.setdefault("request_id", generate_request_id())
    st.session_state.setdefault("current_prompt", "")
    st.session_state.setdefault("generated_sql", "")
    st.session_state.setdefault("generated_explanation", "")
    st.session_state.setdefault("generated_tables", [])
    st.session_state.setdefault("execution_result", None)
    st.session_state.setdefault("evaluation_result", None)
    st.session_state.setdefault("query_history", [])
    st.session_state.setdefault("codex_logs", [])
    st.session_state.setdefault("mlflow_logs", [])


def _append_log(log_key: str, message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    st.session_state[log_key].insert(0, f"[{timestamp}] {message}")
    st.session_state[log_key] = st.session_state[log_key][:50]


def _path_to_data_uri(path: Path) -> str | None:
    """Return a data URI for a local image path, if it exists."""
    if not path.exists():
        return None
    image_bytes = path.read_bytes()
    suffix = path.suffix.lower()
    mime_type = "image/svg+xml" if suffix == ".svg" else "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _render_logo_row() -> None:
    """Render MLflow and Codex logos in equal-sized containers."""
    mlflow_src = _path_to_data_uri(MLFLOW_LOGO_PATH) or _path_to_data_uri(
        MLFLOW_LOGO_FALLBACK_PATH
    )
    codex_src = CODEX_LOGO_URL
    if not codex_src and CODEX_LOGO_FALLBACK_PATH.exists():
        codex_src = _path_to_data_uri(CODEX_LOGO_FALLBACK_PATH) or ""

    logo_html = f"""
    <div style="display:flex; gap:10px; align-items:center; margin: 0.25rem 0 0.75rem 0;">
      <div style="width:{LOGO_BOX_WIDTH_PX}px; height:{LOGO_BOX_HEIGHT_PX}px; display:flex; align-items:center; justify-content:center;">
        <img src="{mlflow_src or ''}" style="max-width:{LOGO_BOX_WIDTH_PX}px; max-height:{LOGO_BOX_HEIGHT_PX}px; width:{LOGO_BOX_WIDTH_PX}px; height:{LOGO_BOX_HEIGHT_PX}px; object-fit:contain;" />
      </div>
      <div style="width:{LOGO_BOX_WIDTH_PX}px; height:{LOGO_BOX_HEIGHT_PX}px; display:flex; align-items:center; justify-content:center;">
        <img src="{codex_src}" style="max-width:{LOGO_BOX_WIDTH_PX}px; max-height:{LOGO_BOX_HEIGHT_PX}px; width:{LOGO_BOX_WIDTH_PX}px; height:{LOGO_BOX_HEIGHT_PX}px; object-fit:contain;" />
      </div>
    </div>
    """
    st.markdown(logo_html, unsafe_allow_html=True)


def _render_sidebar(settings: "AppSettings") -> None:
    from app.config.settings import startup_health_payload

    st.sidebar.header("Data Context")
    st.sidebar.caption("Existing Delta tables only (no synthetic seed data).")
    st.sidebar.caption("Powered by MLflow and Codex Agent")
    st.sidebar.markdown(f"**Catalog Mode**: {settings.catalog_access_mode}")
    st.sidebar.markdown(f"**Row Limit**: {settings.query_row_limit}")
    st.sidebar.markdown(f"**Timeout**: {settings.query_timeout_seconds}s")
    st.sidebar.divider()

    st.sidebar.markdown("### Available Tables")
    for table in DEFAULT_TABLES:
        st.sidebar.write(f"- `{table}`")

    st.sidebar.divider()
    st.sidebar.markdown("### Sample Questions")
    for idx, question in enumerate(SAMPLE_QUESTIONS):
        if st.sidebar.button(question, key=f"sample_{idx}", use_container_width=True):
            st.session_state.current_prompt = question

    health = startup_health_payload(settings)
    with st.sidebar.expander("Startup Health", expanded=False):
        st.json(health)


def _generate_sql(prompt: str) -> dict[str, Any]:
    result = _call_hook(
        "app.agents.conversation_agent",
        "generate_sql_from_nl",
        prompt=prompt,
        tables=DEFAULT_TABLES,
    )
    if isinstance(result, dict) and result.get("sql"):
        return result
    return _placeholder_generate_sql(prompt)


def _validate_sql(sql: str) -> dict[str, Any]:
    result = _call_hook(
        "app.safety.sql_validator",
        "validate_sql",
        sql=sql,
    )
    if isinstance(result, dict) and "is_valid" in result:
        return result
    return _placeholder_validate_sql(sql)


def _execute_sql(sql: str) -> dict[str, Any]:
    result = _call_hook(
        "app.spark.query_executor",
        "execute_sql",
        sql=sql,
    )
    if isinstance(result, dict) and (
        "dataframe" in result or "spark_dataframe" in result
    ):
        return result
    return _placeholder_execute_sql(sql)


def _evaluate_with_mlflow(
    prompt: str,
    sql: str,
    execution_result: dict[str, Any],
) -> dict[str, Any]:
    result = _call_hook(
        "app.observability.mlflow_tracing",
        "evaluate_query_outcome",
        prompt=prompt,
        sql=sql,
        execution_result=execution_result,
    )
    if isinstance(result, dict):
        return result
    return _placeholder_mlflow_eval(prompt, sql, execution_result)


def main() -> None:
    from app.config.settings import load_settings
    from app.utils.logging import get_logger, log_event

    st.set_page_config(page_title=APP_TITLE, page_icon=":bar_chart:", layout="wide")
    _initialize_session_state()
    try:
        settings = load_settings()
    except ValueError as err:
        st.error(f"Configuration error: {err}")
        st.stop()

    logger = get_logger(
        __name__,
        request_id=st.session_state.request_id,
        phase="phase-0",
        component="streamlit-ui",
    )
    log_event(
        logger,
        "app_startup",
        catalog_access_mode=settings.catalog_access_mode,
        openai_key_present=settings.has_openai_key,
    )
    _render_sidebar(settings)

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)
    st.caption("Powered by MLflow and Codex Agent")
    _render_logo_row()

    st.markdown("### 1) Ask a question")
    prompt = st.text_input(
        "Natural language query",
        value=st.session_state.current_prompt,
        placeholder="Example: Show revenue by region for the last quarter",
    )

    if st.button("Generate Spark SQL", type="primary"):
        if not prompt.strip():
            st.warning("Enter a question first.")
            _append_log("codex_logs", "Prompt rejected: empty natural language input.")
        else:
            generated = _generate_sql(prompt)
            st.session_state.current_prompt = prompt
            st.session_state.generated_sql = generated.get("sql", "")
            st.session_state.generated_explanation = generated.get("explanation", "")
            st.session_state.generated_tables = generated.get("tables_used", [])
            st.session_state.execution_result = None
            st.session_state.evaluation_result = None
            _append_log(
                "codex_logs",
                "Generated Spark SQL from natural language prompt.",
            )
            _append_log(
                "codex_logs",
                f"Tables referenced: {', '.join(st.session_state.generated_tables) or 'n/a'}",
            )

    st.markdown("### 2) Review or edit SQL")
    sql_text = st.text_area(
        "Generated Spark SQL",
        value=st.session_state.generated_sql,
        height=140,
        placeholder="SQL will appear here after generation.",
    )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        run_clicked = st.button("Execute SQL", use_container_width=True)
    with col_b:
        if st.session_state.generated_explanation:
            st.info(st.session_state.generated_explanation)

    if run_clicked:
        if not sql_text.strip():
            st.warning("Generate or provide SQL before executing.")
            _append_log("codex_logs", "Execution skipped: SQL text is empty.")
        else:
            validation = _validate_sql(sql_text)
            if not validation.get("is_valid", False):
                st.error(
                    f"SQL blocked: {validation.get('reason', 'Unknown validation failure')}"
                )
                _append_log(
                    "codex_logs",
                    f"SQL validation blocked execution: {validation.get('reason', 'unknown reason')}",
                )
            else:
                runnable_sql = validation.get("normalized_sql", sql_text)
                _append_log("codex_logs", "SQL validation passed. Executing query.")
                execution = _execute_sql(runnable_sql)
                st.session_state.execution_result = execution
                st.session_state.evaluation_result = _evaluate_with_mlflow(
                    prompt=st.session_state.current_prompt,
                    sql=runnable_sql,
                    execution_result=execution,
                )
                _append_log(
                    "codex_logs",
                    f"Execution completed in {execution.get('runtime_ms', 'n/a')} ms with "
                    f"{execution.get('row_count', 'n/a')} rows.",
                )
                _append_log(
                    "mlflow_logs",
                    "Recorded evaluation for latest query outcome.",
                )
                st.session_state.query_history.insert(
                    0,
                    {
                        "prompt": st.session_state.current_prompt,
                        "sql": runnable_sql,
                        "rows": execution.get("row_count", 0),
                        "runtime_ms": execution.get("runtime_ms", 0),
                    },
                )

    st.markdown("### 3) Results")
    execution_result = st.session_state.execution_result
    if execution_result:
        if execution_result.get("error"):
            st.error(str(execution_result["error"]))
        else:
            meta_cols = st.columns(3)
            meta_cols[0].metric("Rows", execution_result.get("row_count", 0))
            meta_cols[1].metric("Runtime (ms)", execution_result.get("runtime_ms", 0))
            meta_cols[2].metric(
                "Tables Used", len(execution_result.get("tables_used", []))
            )

            dataframe = execution_result.get("dataframe")
            if isinstance(dataframe, pd.DataFrame):
                st.dataframe(dataframe, use_container_width=True)
            else:
                st.warning("Execution hook did not return a pandas DataFrame.")

    st.markdown("### 4) MLflow Evaluation")
    eval_result = st.session_state.evaluation_result
    if eval_result:
        left, right = st.columns(2)
        left.write(f"**Query Quality:** {eval_result.get('query_quality', 'n/a')}")
        left.write(
            f"**Correctness Score:** {eval_result.get('correctness_score', 'n/a')}"
        )
        right.write(f"**Safety Score:** {eval_result.get('safety_score', 'n/a')}")
        right.write(f"**Notes:** {eval_result.get('notes', 'n/a')}")

    with st.expander("Query History", expanded=False):
        for item in st.session_state.query_history[:10]:
            st.write(
                f"- Prompt: `{item['prompt']}` | Rows: {item['rows']} | "
                f"Runtime: {item['runtime_ms']} ms"
            )
            st.code(item["sql"], language="sql")

    st.markdown("### 5) Logs")
    log_col_a, log_col_b = st.columns(2)
    with log_col_a:
        with st.expander("Codex Agent Log", expanded=False):
            if st.session_state.codex_logs:
                st.code("\n".join(st.session_state.codex_logs), language="text")
            else:
                st.caption("No Codex events yet.")
    with log_col_b:
        with st.expander("MLflow Log", expanded=False):
            if st.session_state.mlflow_logs:
                st.code("\n".join(st.session_state.mlflow_logs), language="text")
            else:
                st.caption("No MLflow events yet.")


if __name__ == "__main__":
    main()
