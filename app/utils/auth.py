from datetime import datetime, timezone
from typing import Any, Dict

import jwt
import requests
from fastapi import HTTPException, Request, Response
from jwt import InvalidTokenError, PyJWKClient

from app.settings import settings
from app.utils.log import logger

ISSUER_URL = settings.COGNITO_ISSUER_URL
AUDIENCE = settings.COGNITO_AUDIENCE


def get_jwks_url(issuer_url: str) -> str:
    """
    Return the JWKS endpoint URL for a Cognito user pool.

    Pattern:
        <issuer_url>/.well-known/jwks.json

    Example issuer_url:
        https://cognito-idp.eu-west-2.amazonaws.com/eu-west-2_XXXX
    """

    if not issuer_url:
        logger.error(
            f"Missing COGNITO_ISSUER_URL env var. Value={settings.COGNITO_ISSUER_URL}"
        )
        raise HTTPException(
            status_code=500,
            detail="Missing COGNITO_ISSUER_URL in environment variables.",
        )

    # Construct JWKS URL
    base = issuer_url.rstrip("/")
    return f"{base}/.well-known/jwks.json"


def get_id_token(request: Request) -> str:
    """Extract ID token from cookies or raise 401"""
    id_token = request.cookies.get("id_token")
    if not id_token:
        logger.warning("ID token missing from cookies")
        raise HTTPException(status_code=401, detail="ID token is missing. Login again.")

    return id_token


def decode_and_validate_id_token(
    id_token: str, jwks_url, issuer: str, audience: str
) -> Dict[str, Any]:
    """
    Decode the ID token, verify signature and claims, return decoded
    """
    jwks_client = PyJWKClient(jwks_url)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token).key

    decoded_token = jwt.decode(
        id_token,
        signing_key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=audience,
    )

    logger.debug("JWT successfully decoded and verified")

    token_use = decoded_token.get("token_use")
    if token_use != "id":
        logger.error(
            f"Token 'token_use' mismatch: expected 'id', got {decoded_token.get('token_use')}"
        )
        raise HTTPException(status_code=401, detail="Wrong token type")

    return decoded_token


def log_sub_and_exp(decoded_token: Dict[str, Any]):  # pragma: no cover
    """Logging the user sub and token expiry to help with debugging"""
    exp = decoded_token.get("exp")
    exp_time = (
        datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if exp
        else None
    )
    sub = decoded_token.get("sub")
    logger.info(f"Authenticated user sub={sub}, token exp={exp_time}")


def set_state(sub, request):

    request.state.user_sub = sub


def attempt_token_refresh(refresh_token: str) -> dict:
    """Call Cognito's token endpoint with grant_type=refresh_token. Returns response JSON."""
    data = {
        "grant_type": "refresh_token",
        "client_id": AUDIENCE,
        "refresh_token": refresh_token,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(settings.token_url(), data=data, headers=headers, timeout=5)
    logger.debug(f"Token refresh status_code={resp.status_code}")

    if resp.status_code != 200:
        logger.warning(f"Token refresh failed: {resp.text}")
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    return resp.json()


def require_auth(request: Request, response: Response):
    """
    Validate ID token from cookies and return decoded claims.
    """

    if settings.DISABLE_AUTH_FOR_LOCAL_DEV:  # pragma: no cover
        logger.warning("Auth bypass enabled: returning fake LOCAL-DEV-USER claims")
        fake_claims = {
            "sub": settings.DEV_USER_SUB or "LOCAL-DEV-USER",
            "cognito:username": "localdevuser",
            "email": "local-dev@example.com",
        }
        return fake_claims

    id_token = get_id_token(request)

    issuer_url = (ISSUER_URL or "").rstrip("/")
    jwks_url = get_jwks_url(issuer_url)

    try:
        decoded_token = decode_and_validate_id_token(
            id_token=id_token, jwks_url=jwks_url, issuer=issuer_url, audience=AUDIENCE
        )

        log_sub_and_exp(decoded_token)
        sub = decoded_token.get("sub")
        set_state(sub, request)
        return decoded_token

    except jwt.ExpiredSignatureError:
        logger.warning("ID token expired; attempting refresh")

        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

        token_data = attempt_token_refresh(refresh_token)

        cookie_opts = {"httponly": True, "secure": True, "samesite": "lax"}
        response.set_cookie(key="id_token", value=token_data["id_token"], max_age=token_data["expires_in"], **cookie_opts)
        response.set_cookie(key="access_token", value=token_data["access_token"], max_age=token_data["expires_in"], **cookie_opts)

        new_id_token = token_data["id_token"]
        decoded_token = decode_and_validate_id_token(
            id_token=new_id_token, jwks_url=jwks_url, issuer=issuer_url, audience=AUDIENCE
        )
        sub = decoded_token.get("sub")
        set_state(sub, request)
        return decoded_token

    except InvalidTokenError as e:
        logger.error(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    except Exception as e:
        # safety net for debugging — but NOT leaking token
        logger.exception(f"Unexpected error during token validation: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
