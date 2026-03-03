"""FastAPI dependencies for API key authentication.

Two variants:
- require_api_key  — validates key AND increments calls_used (billable endpoints)
- read_api_key     — validates key without incrementing (e.g. GET /usage)

In LEADSCLEAN_DEMO=1 mode both dependencies return a dummy key info dict so the
server works without any database.
"""

import asyncio
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from db import AuthError, check_and_increment, get_key_info

_DEMO_KEY_INFO: dict = {
    "key": "demo",
    "email": "demo",
    "plan": "demo",
    "calls_used": 0,
    "monthly_limit": 999_999,
    "reset_at": "2099-01-01",
}

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _is_demo() -> bool:
    return bool(os.getenv("LEADSCLEAN_DEMO"))


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> dict:
    """Validate key and increment calls_used. Attach to billable endpoints."""
    if _is_demo():
        return _DEMO_KEY_INFO
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header.")
    try:
        return await asyncio.to_thread(check_and_increment, api_key)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


async def read_api_key(api_key: str | None = Security(_api_key_header)) -> dict:
    """Validate key without incrementing. Use for non-billable endpoints."""
    if _is_demo():
        return _DEMO_KEY_INFO
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header.")
    try:
        return await asyncio.to_thread(get_key_info, api_key)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
