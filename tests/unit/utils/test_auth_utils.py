import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from app.utils import auth as auth_utils
from tests.test_data import USER_SUB

fake_jwks_url = "https://example.com/.well-known/jwks.json"
fake_token = "header.payload.sig"


class FakeKey:
    key = "fake-public-key"


class FakeJwksClient:
    def __init__(self, url):
        self.url = url

    def get_signing_key_from_jwt(self, token):
        assert token == fake_token
        return FakeKey()


@pytest.fixture(autouse=True)
def _disable_auth_bypass(monkeypatch):
    monkeypatch.setattr(auth_utils.settings, "DISABLE_AUTH_FOR_LOCAL_DEV", False)


# ------------ Get jwks url ------------


def test_get_jwks_url_success():
    issuer_url = "https://cognito-idp.eu-west-2.amazonaws.com/eu-west-2_fakepool"

    result = auth_utils.get_jwks_url(issuer_url)

    assert (
        result == "https://cognito-idp.eu-west-2.amazonaws.com/"
        "eu-west-2_fakepool/.well-known/jwks.json"
    )


def test_get_jwks_url_missing_params():
    with pytest.raises(HTTPException) as err2:
        auth_utils.get_jwks_url("")

    assert err2.value.status_code == 500


# ------------ Get ID Token ------------


def test_get_id_token_success(make_request_with_cookies):
    req = make_request_with_cookies({"id_token": "test-token"})
    result = auth_utils.get_id_token(req)
    assert result == "test-token"


def test_get_id_token_missing(make_request_with_cookies):
    req = make_request_with_cookies({})

    with pytest.raises(HTTPException) as err:
        auth_utils.get_id_token(req)

    assert err.value.status_code == 401
    assert "ID token is missing" in err.value.detail


# ------------ Decode and validate token ------------


def test_decode_and_validate_token_success(monkeypatch):

    def fake_decode(token, signing_key, algorithms, issuer, audience):
        assert token == fake_token
        assert signing_key == "fake-public-key"
        assert algorithms == ["RS256"]
        return {
            "sub": USER_SUB,
            "exp": 1700000000,
            "token_use": "id",
        }

    # patch PyJWKClient used in auth module
    monkeypatch.setattr(auth_utils, "PyJWKClient", FakeJwksClient)
    # patch jwt.decode in auth module
    monkeypatch.setattr(auth_utils.jwt, "decode", fake_decode)

    decoded = auth_utils.decode_and_validate_id_token(
        id_token=fake_token,
        jwks_url=fake_jwks_url,
        issuer=auth_utils.ISSUER_URL,
        audience=auth_utils.AUDIENCE,
    )

    assert decoded["sub"] == USER_SUB
    assert decoded["token_use"] == "id"
    assert "exp" in decoded


def test_decode_and_validate_id_token_wrong_token_use(monkeypatch):

    def fake_decode(token, signing_key, algorithms, issuer, audience):
        return {
            "sub": USER_SUB,
            "exp": 1700000000,
            "token_use": "access",
        }

    monkeypatch.setattr(auth_utils, "PyJWKClient", FakeJwksClient)
    monkeypatch.setattr(auth_utils.jwt, "decode", fake_decode)

    with pytest.raises(HTTPException) as err:
        auth_utils.decode_and_validate_id_token(
            id_token=fake_token,
            jwks_url=fake_jwks_url,
            issuer=auth_utils.ISSUER_URL,
            audience=auth_utils.AUDIENCE,
        )

    assert err.value.status_code == 401
    assert "Wrong token type" in err.value.detail


# ------------ Require auth ------------


@pytest.mark.asyncio
async def test_require_auth_success(auth_pipeline, make_request_with_cookies):
    req = make_request_with_cookies({"id_token": "fake-token"})

    decoded = auth_utils.require_auth(req, Response())

    assert decoded["sub"] == USER_SUB
    assert auth_pipeline["get_id_token"] is True
    assert "get_jwks_url" in auth_pipeline
    assert "decode_and_validate" in auth_pipeline
    assert auth_pipeline["log_sub_and_exp"]["sub"] == USER_SUB


@pytest.mark.asyncio
async def test_require_auth_failure_cases(
    monkeypatch, make_request_with_cookies, stub_basic_auth_helpers
):
    req = make_request_with_cookies({"id_token": "fake-token"})

    cases = [
        (auth_utils.InvalidTokenError("bad token"), "Invalid token"),
        (RuntimeError("something unexpected"), "Invalid token"),
    ]

    for exc, expected in cases:

        def fake_decode_and_validate(_exc=exc, *args, **kwargs):
            raise _exc

        monkeypatch.setattr(
            auth_utils, "decode_and_validate_id_token", fake_decode_and_validate
        )

        with pytest.raises(HTTPException) as err:
            auth_utils.require_auth(req, Response())

        assert err.value.status_code == 401
        assert expected in err.value.detail


# ------------ attempt_token_refresh ------------


def test_attempt_token_refresh_success(monkeypatch):
    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "id_token": "new-id-token",
                "access_token": "new-access-token",
                "expires_in": 3600,
            }

    monkeypatch.setattr(auth_utils.requests, "post", lambda *a, **kw: FakeResp())

    result = auth_utils.attempt_token_refresh("valid-refresh-token")

    assert result["id_token"] == "new-id-token"
    assert result["access_token"] == "new-access-token"
    assert result["expires_in"] == 3600


def test_attempt_token_refresh_failure(monkeypatch):
    class FakeResp:
        status_code = 400
        text = "invalid_grant"

        def json(self):
            return {}

    monkeypatch.setattr(auth_utils.requests, "post", lambda *a, **kw: FakeResp())

    with pytest.raises(HTTPException) as err:
        auth_utils.attempt_token_refresh("expired-refresh-token")

    assert err.value.status_code == 401
    assert "Session expired" in err.value.detail


# ------------ require_auth refresh paths ------------


def test_require_auth_expired_with_valid_refresh(monkeypatch, make_request_with_cookies, stub_basic_auth_helpers):
    """Expired ID token + valid refresh token -> success, new cookies set."""
    req = make_request_with_cookies({"id_token": "expired-token", "refresh_token": "valid-rt"})
    resp = Response()

    call_count = {"n": 0}

    def fake_decode_and_validate(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise auth_utils.jwt.ExpiredSignatureError("expired")
        return {"sub": USER_SUB, "exp": 9999999999, "token_use": "id"}

    monkeypatch.setattr(auth_utils, "decode_and_validate_id_token", fake_decode_and_validate)
    monkeypatch.setattr(
        auth_utils,
        "attempt_token_refresh",
        lambda rt: {"id_token": "new-id", "access_token": "new-at", "expires_in": 3600},
    )

    decoded = auth_utils.require_auth(req, resp)

    assert decoded["sub"] == USER_SUB
    # Both new cookies should be queued on the response
    set_cookie_headers = [v for k, v in resp.raw_headers if k == b"set-cookie"]
    assert any(b"id_token=new-id" in h for h in set_cookie_headers)
    assert any(b"access_token=new-at" in h for h in set_cookie_headers)


def test_require_auth_expired_no_refresh_token(monkeypatch, make_request_with_cookies, stub_basic_auth_helpers):
    """Expired ID token + no refresh token -> 401."""
    req = make_request_with_cookies({"id_token": "expired-token"})

    def fake_decode_and_validate(*args, **kwargs):
        raise auth_utils.jwt.ExpiredSignatureError("expired")

    monkeypatch.setattr(auth_utils, "decode_and_validate_id_token", fake_decode_and_validate)

    with pytest.raises(HTTPException) as err:
        auth_utils.require_auth(req, Response())

    assert err.value.status_code == 401
    assert "Session expired" in err.value.detail


def test_require_auth_expired_bad_refresh_token(monkeypatch, make_request_with_cookies, stub_basic_auth_helpers):
    """Expired ID token + bad refresh token -> 401 from attempt_token_refresh."""
    req = make_request_with_cookies({"id_token": "expired-token", "refresh_token": "bad-rt"})

    def fake_decode_and_validate(*args, **kwargs):
        raise auth_utils.jwt.ExpiredSignatureError("expired")

    def fake_attempt_token_refresh(rt):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    monkeypatch.setattr(auth_utils, "decode_and_validate_id_token", fake_decode_and_validate)
    monkeypatch.setattr(auth_utils, "attempt_token_refresh", fake_attempt_token_refresh)

    with pytest.raises(HTTPException) as err:
        auth_utils.require_auth(req, Response())

    assert err.value.status_code == 401
    assert "Session expired" in err.value.detail
