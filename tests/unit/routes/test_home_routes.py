from fastapi import HTTPException

from app.utils import auth as auth_utils


def test_home_logged_out_contains_welcome_title(client, monkeypatch):
    def _raise(_request):
        raise HTTPException(status_code=401, detail="Not authenticated")

    monkeypatch.setattr(auth_utils, "require_auth", _raise)

    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome to ElbieFit" in response.text
    assert "Log in" in response.text
    assert "Recent workouts" not in response.text


def test_home_logged_in_shows_dashboard(client, fake_workout_repo, monkeypatch):
    monkeypatch.setattr(
        auth_utils, "require_auth", lambda _request: {"sub": "test-user-sub"}
    )

    response = client.get("/")
    assert response.status_code == 200
    assert "Recent workouts" in response.text


def test_health_returns_status(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta_endpoint_returns_basic_info(client):
    response = client.get("/meta")
    body = response.json()

    assert response.status_code == 200
    assert body["app_name"] == "ElbieFit"
    assert isinstance(body["version"], str)
    assert body["version"]
