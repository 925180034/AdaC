"""FastAPI middleware for API key auth and tenant context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from adacascade.config import settings

PUBLIC_PATHS = {"/healthz", "/metrics", "/docs", "/openapi.json", "/redoc"}


class AuthAndTenantMiddleware(BaseHTTPMiddleware):
    """Enforce bearer-token auth and attach tenant context to requests."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        tenant_id = request.headers.get("X-Tenant-Id") or settings.DEFAULT_TENANT_ID
        request.state.tenant_id = tenant_id

        path = request.url.path
        if settings.AUTH_ENABLED and not _is_public_path(path):
            expected = f"Bearer {settings.API_KEY}"
            if request.headers.get("Authorization") != expected:
                return JSONResponse(
                    {"detail": "Missing or invalid bearer token"}, status_code=401
                )
        return await call_next(request)


def _is_public_path(path: str) -> bool:
    return (
        path in PUBLIC_PATHS or path.startswith("/docs/") or path.startswith("/redoc/")
    )


def get_tenant_id(request: Request) -> str:
    """Return the tenant id attached by AuthAndTenantMiddleware."""
    return str(getattr(request.state, "tenant_id", settings.DEFAULT_TENANT_ID))
