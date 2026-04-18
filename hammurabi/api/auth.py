"""X-API-Key authentication dependency. Open mode when API_KEY env is unset."""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from hammurabi.config import settings

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_header_scheme)) -> None:
    if not settings.api_key:
        return
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
