from __future__ import annotations

import secrets
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from app.settings import settings
from app.utils.log import logger

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_COOKIE_NAME = "csrf_token"
_HEADER_NAME = "x-csrftoken"


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Double-submit cookie CSRF protection.

    On safe requests (GET/HEAD/OPTIONS): issue a csrf_token cookie if absent.
    On unsafe requests (POST/PUT/PATCH/DELETE): require an X-CSRFToken header
    whose value matches the csrf_token cookie; respond 403 otherwise.

    The cookie is non-HttpOnly so that HTMX (via htmx:configRequest) can read
    it and copy the value into the X-CSRFToken request header.  A cross-site
    attacker cannot read the cookie (same-origin policy) and therefore cannot
    supply the matching header.
    """

    def __init__(self, app, excluded_prefixes: tuple[str, ...] = ()):
        super().__init__(app)
        self.excluded_prefixes = excluded_prefixes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.CSRF_ENABLED:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in self.excluded_prefixes):
            return await call_next(request)

        if request.method.upper() not in _SAFE_METHODS:
            # Multipart requests (file uploads) are excluded here because reading
            # the body in middleware consumes the stream; CSRF is checked manually
            # in the route handler for those endpoints.
            if "multipart/form-data" in request.headers.get("content-type", ""):
                pass
            else:
                cookie_token = request.cookies.get(_COOKIE_NAME, "")
                header_token = request.headers.get(_HEADER_NAME, "")
                if not cookie_token or not secrets.compare_digest(cookie_token, header_token):
                    logger.warning(
                        f"CSRF validation failed method={request.method} path={path}"
                    )
                    return PlainTextResponse(
                        "CSRF token missing or invalid", status_code=403
                    )

        response = await call_next(request)

        # Mint a new token on safe requests when the cookie is absent.
        if (
            request.method.upper() in _SAFE_METHODS
            and _COOKIE_NAME not in request.cookies
        ):
            response.set_cookie(
                key=_COOKIE_NAME,
                value=secrets.token_hex(32),
                httponly=False,
                secure=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,
            )

        return response
