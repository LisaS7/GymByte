from typing import Any

import pytest

from app.utils import auth as auth_utils
from app.utils import db
from tests.test_data import USER_SUB


@pytest.fixture
def stub_basic_auth_helpers(monkeypatch):
    def fake_get_id_token(request):
        return "fake-token"

    def fake_get_jwks_url(issuer):
        return "https://example.com/jwks.json"

    monkeypatch.setattr(auth_utils, "get_id_token", fake_get_id_token)
    monkeypatch.setattr(auth_utils, "get_jwks_url", fake_get_jwks_url)


@pytest.fixture
def auth_pipeline(monkeypatch):
    """
    Patch the auth pipeline helpers and capture calls.
    Returns a dict with 'calls' and allows overriding return values.
    """
    calls: dict[str, Any] = {}

    def fake_get_id_token(request):
        calls["get_id_token"] = True
        return "fake-token"

    def fake_get_jwks_url(issuer_url):
        calls["get_jwks_url"] = issuer_url
        return "https://example.com/jwks.json"

    def fake_decode_and_validate(id_token, jwks_url, issuer, audience):
        calls["decode_and_validate"] = (id_token, jwks_url, issuer, audience)
        return {"sub": USER_SUB, "exp": 1700000000, "token_use": "id"}

    def fake_log_sub_and_exp(decoded):
        calls["log_sub_and_exp"] = decoded

    monkeypatch.setattr(auth_utils, "get_id_token", fake_get_id_token)
    monkeypatch.setattr(auth_utils, "get_jwks_url", fake_get_jwks_url)
    monkeypatch.setattr(
        auth_utils, "decode_and_validate_id_token", fake_decode_and_validate
    )
    monkeypatch.setattr(auth_utils, "log_sub_and_exp", fake_log_sub_and_exp)

    return calls


@pytest.fixture
def frozen_time(monkeypatch):
    """
    Freeze db.time.time() to a known timestamp.
    now=125 -> window_id=2, retry_after=55
    """
    now = 125
    monkeypatch.setattr(db.time, "time", lambda: now)
    return now


class FakeRateLimitTable:
    def __init__(self, count: int):
        self.count = count
        self.last_kwargs = None

    def update_item(self, **kwargs):
        self.last_kwargs = kwargs
        return {"Attributes": {"count": self.count}}


@pytest.fixture
def fake_table_factory():
    def _make(count: int) -> FakeRateLimitTable:
        return FakeRateLimitTable(count=count)

    return _make


@pytest.fixture
def use_table(monkeypatch):
    """
    Helper to install a specific fake table as db.get_table().
    Returns the table so the test can inspect captured kwargs.
    """

    def _use(table):
        monkeypatch.setattr(db, "get_table", lambda: table)
        return table

    return _use
