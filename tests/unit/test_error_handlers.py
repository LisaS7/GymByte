from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.error_handlers import register_error_handlers

# Build a self-contained app so we never mutate the shared session-scoped app.
# Mount static so that url_for('static', ...) in base.html resolves correctly.
_test_app = FastAPI()
_test_app.mount("/static", StaticFiles(directory="static"), name="static")
register_error_handlers(_test_app)


@_test_app.get("/raise-401")
def raise_401():
    raise HTTPException(status_code=401, detail="Nope")


@_test_app.get("/raise-418")
def raise_418():
    raise HTTPException(status_code=418, detail="I am a teapot")


@_test_app.get("/raise-exception")
def raise_exception():
    raise ValueError("Kaboom")


_client = TestClient(_test_app, raise_server_exceptions=False)


def test_401_redirects_to_login():
    response = _client.get("/raise-401", follow_redirects=False)
    assert response.status_code == 307 or response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_http_exception_renders_error_template():
    response = _client.get("/raise-418")
    assert response.status_code == 418
    assert "I am a teapot" in response.text


def test_unhandled_exception_renders_gremlins():
    response = _client.get("/raise-exception")
    assert response.status_code == 500
    assert "Gremlins." in response.text
