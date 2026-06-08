"""Integration tests for fast-path end-to-end flow."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_env(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _bootstrap_imports() -> tuple[object, object, object, object]:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    settings_module = importlib.import_module("app.config.settings")
    streamlit_module = importlib.import_module("app.ui.streamlit_app")
    helpers_module = importlib.import_module("app.utils.helpers")
    logging_module = importlib.import_module("app.utils.logging")
    return settings_module, streamlit_module, helpers_module, logging_module


def test_phase0_modules_importable() -> None:
    """Basic smoke check to ensure phase-0 modules load."""
    _, streamlit_module, helpers_module, logging_module = _bootstrap_imports()
    assert callable(streamlit_module.main)
    assert callable(helpers_module.generate_request_id)
    assert logging_module.get_logger("phase0-test")


def test_load_settings_from_env_file(tmp_path: Path) -> None:
    settings_module, _, _, _ = _bootstrap_imports()
    env_file = tmp_path / ".env"
    _write_env(
        env_file,
        "\n".join(
            [
                "OPENAI_API_KEY=sk-example",
                "OPENAI_MODEL=gpt-4.1-mini",
                "CATALOG_ACCESS_MODE=local",
                "QUERY_ROW_LIMIT=500",
                "QUERY_TIMEOUT_SECONDS=15",
            ]
        ),
    )

    settings = settings_module.load_settings(env_file=env_file, dotenv_override=True)
    health = settings_module.startup_health_payload(settings)

    assert settings.has_openai_key is True
    assert settings.query_row_limit == 500
    assert settings.query_timeout_seconds == 15
    assert health["config_loaded"] is True
    assert health["openai_key_present"] is True


def test_load_settings_rejects_invalid_limits(tmp_path: Path) -> None:
    settings_module, _, _, _ = _bootstrap_imports()
    env_file = tmp_path / ".env"
    _write_env(
        env_file,
        "\n".join(
            [
                "OPENAI_API_KEY=sk-example",
                "OPENAI_MODEL=gpt-4.1-mini",
                "CATALOG_ACCESS_MODE=local",
                "QUERY_ROW_LIMIT=0",
                "QUERY_TIMEOUT_SECONDS=30",
            ]
        ),
    )

    with pytest.raises(ValueError, match="QUERY_ROW_LIMIT"):
        settings_module.load_settings(env_file=env_file, dotenv_override=True)


def test_load_settings_requires_remote_catalog_uri(tmp_path: Path) -> None:
    settings_module, _, _, _ = _bootstrap_imports()
    env_file = tmp_path / ".env"
    _write_env(
        env_file,
        "\n".join(
            [
                "OPENAI_API_KEY=sk-example",
                "OPENAI_MODEL=gpt-4.1-mini",
                "CATALOG_ACCESS_MODE=remote",
                "QUERY_ROW_LIMIT=100",
                "QUERY_TIMEOUT_SECONDS=30",
            ]
        ),
    )

    with pytest.raises(ValueError, match="REMOTE_CATALOG_URI"):
        settings_module.load_settings(env_file=env_file, dotenv_override=True)
