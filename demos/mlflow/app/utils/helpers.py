"""General helper functions shared across modules."""

from __future__ import annotations

import uuid


def generate_request_id() -> str:
    """Create a request correlation identifier."""
    return uuid.uuid4().hex[:12]


def bool_from_env(value: str | None, default: bool = False) -> bool:
    """Interpret common env-style truthy values."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def mask_secret(
    secret: str, *, visible_prefix: int = 4, visible_suffix: int = 2
) -> str:
    """Return a minimally exposed secret string for diagnostics."""
    if not secret:
        return ""
    if len(secret) <= visible_prefix + visible_suffix:
        return "*" * len(secret)
    return f"{secret[:visible_prefix]}{'*' * (len(secret) - visible_prefix - visible_suffix)}{secret[-visible_suffix:]}"
