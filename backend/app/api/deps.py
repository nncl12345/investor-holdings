"""Shared FastAPI dependencies."""

from fastapi import Header, HTTPException, status

from app.core.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    Protect write endpoints behind a shared secret.

    - If `settings.api_key` is empty (local dev default), the dependency is a no-op.
    - If set, the caller must send `X-API-Key: <value>` matching the configured secret.

    Read endpoints deliberately stay unauthenticated — the demo is public by design.
    """
    expected = settings.api_key
    if not expected:
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key",
        )
