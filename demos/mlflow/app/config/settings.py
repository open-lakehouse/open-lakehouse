"""Application settings and environment configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppSettings:
    """Runtime settings sourced from environment variables."""

    openai_api_key: str
    openai_model: str
    spark_master: str
    catalog_access_mode: str
    catalog_name: str
    remote_catalog_uri: str
    query_row_limit: int
    query_timeout_seconds: int

    @property
    def has_openai_key(self) -> bool:
        """Return whether an OpenAI API key is present."""
        return bool(self.openai_api_key)


def _env_file_path() -> Path:
    """Return the demo-local .env file path."""
    return Path(__file__).resolve().parents[2] / ".env"


def _parse_positive_int(name: str, raw_value: str, default: int) -> int:
    """Parse an integer environment value and enforce positive semantics."""
    candidate = (raw_value or str(default)).strip()
    try:
        value = int(candidate)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer. Received: {candidate!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be > 0. Received: {value}")
    return value


def _parse_catalog_access_mode(raw_value: str) -> str:
    """Validate and normalize catalog mode."""
    normalized = (raw_value or "local").strip().lower()
    if normalized not in {"local", "remote"}:
        raise ValueError(
            "CATALOG_ACCESS_MODE must be 'local' or 'remote'. "
            f"Received: {normalized!r}"
        )
    return normalized


def load_settings(
    env_file: Path | None = None,
    *,
    require_openai_api_key: bool = False,
    dotenv_override: bool = False,
) -> AppSettings:
    """Load environment-backed settings for the MLflow demo app."""
    resolved_env_file = env_file or _env_file_path()
    load_dotenv(resolved_env_file, override=dotenv_override)

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    spark_master = os.getenv("SPARK_MASTER", "").strip()
    catalog_access_mode = _parse_catalog_access_mode(os.getenv("CATALOG_ACCESS_MODE", "local"))
    catalog_name = os.getenv("CATALOG_NAME", "").strip()
    remote_catalog_uri = os.getenv("REMOTE_CATALOG_URI", "").strip()
    query_row_limit = _parse_positive_int(
        "QUERY_ROW_LIMIT",
        os.getenv("QUERY_ROW_LIMIT", "1000"),
        default=1000,
    )
    query_timeout_seconds = _parse_positive_int(
        "QUERY_TIMEOUT_SECONDS",
        os.getenv("QUERY_TIMEOUT_SECONDS", "60"),
        default=60,
    )

    if not openai_model:
        raise ValueError("OPENAI_MODEL cannot be empty.")
    if require_openai_api_key and not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required but missing.")
    if catalog_access_mode == "remote" and not remote_catalog_uri:
        raise ValueError(
            "REMOTE_CATALOG_URI is required when CATALOG_ACCESS_MODE=remote."
        )

    return AppSettings(
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        spark_master=spark_master,
        catalog_access_mode=catalog_access_mode,
        catalog_name=catalog_name,
        remote_catalog_uri=remote_catalog_uri,
        query_row_limit=query_row_limit,
        query_timeout_seconds=query_timeout_seconds,
    )


def startup_health_payload(settings: AppSettings) -> dict[str, Any]:
    """Build startup health data for UI diagnostics."""
    spark_target_mode = "configured" if settings.spark_master else "default"
    return {
        "config_loaded": True,
        "spark_target_mode": spark_target_mode,
        "catalog_access_mode": settings.catalog_access_mode,
        "openai_key_present": settings.has_openai_key,
        "query_row_limit": settings.query_row_limit,
        "query_timeout_seconds": settings.query_timeout_seconds,
    }
