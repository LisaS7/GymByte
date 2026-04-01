from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Literal

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.main import app
from app.models.profile import Preferences, UserProfile
from app.models.workout import Workout, WorkoutSet
from app.routes import workout as workout_routes
from app.settings import settings
from app.utils import auth as auth_utils
from app.utils import dates, db
from tests.test_data import TEST_DATE_2, TEST_WORKOUT_ID_2, USER_SUB


@pytest.fixture(autouse=True)
def disable_rate_limiting_for_tests():
    settings.RATE_LIMIT_ENABLED = False
    yield
    settings.RATE_LIMIT_ENABLED = True


@pytest.fixture(autouse=True)
def disable_csrf_for_tests():
    settings.CSRF_ENABLED = False
    yield
    settings.CSRF_ENABLED = True


@pytest.fixture
def fixed_now(monkeypatch) -> datetime:
    now = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(dates, "now", lambda: now)
    return now


class FakeProfileRepo:
    def __init__(self, unit: Literal["metric", "imperial"] = "metric"):
        self.unit = unit

    def get_for_user(self, user_sub: str):
        # Return a valid profile model with units set
        return UserProfile(
            PK=f"USER#{user_sub}",
            SK="PROFILE",
            display_name="Test User",
            email="test@example.com",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            timezone="Europe/London",
            preferences=Preferences(units=self.unit),
        )


# --------------- Request ---------------


@pytest.fixture
def make_request_with_cookies():
    """
    Fixture returning a function that builds a FastAPI Request with given cookies.
    Example:
        request = make_request_with_cookies({"id_token": "abc"})
    """

    def _build(cookies: dict) -> Request:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()
        scope = {
            "type": "http",
            "headers": [(b"cookie", cookie_header)],
        }
        return Request(scope)

    return _build


# --------------- Response ---------------


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


@pytest.fixture
def fake_response():
    """
    Factory fixture that returns a function to build FakeResponse objects.
    Example:
        resp = fake_response(status_code=400, text="boom")
    """

    def _make(status_code=200, json_data=None, text=""):
        return FakeResponse(status_code=status_code, json_data=json_data, text=text)

    return _make


# --------------- Test Clients ---------------


@pytest.fixture(scope="session")
def app_instance():
    return app


@pytest.fixture
def client(app_instance):
    """Plain client, real dependencies."""
    return TestClient(app_instance, raise_server_exceptions=False)


@pytest.fixture
def authenticated_client(app_instance):
    """
    Client with auth.require_auth overridden to always
    return a fake, valid claims dict.
    """

    def fake_require_auth(request: Request):
        return {"sub": "test-user-sub"}

    app_instance.dependency_overrides[auth_utils.require_auth] = fake_require_auth
    app_instance.dependency_overrides[workout_routes.get_profile_repo] = (
        lambda: FakeProfileRepo(unit="metric")
    )
    client = TestClient(app_instance, raise_server_exceptions=False)

    try:
        yield client
    finally:
        # Clean up so other tests see the real dependency
        app_instance.dependency_overrides.pop(auth_utils.require_auth, None)
        app_instance.dependency_overrides.pop(workout_routes.get_profile_repo, None)


# --------------- Item Factories ---------------


@pytest.fixture
def workout_factory(fixed_now) -> Callable[..., Workout]:
    def _make(**overrides: Any) -> Workout:
        base = Workout(
            PK=db.build_user_pk(USER_SUB),
            SK=db.build_workout_sk(TEST_DATE_2, TEST_WORKOUT_ID_2),
            type="workout",
            date=TEST_DATE_2,
            name="Move Me Dino Day",
            tags=["upper"],
            notes="Roar",
            created_at=fixed_now,
            updated_at=fixed_now,
        )
        return base.model_copy(update=overrides)

    return _make


@pytest.fixture
def set_factory(fixed_now) -> Callable[..., WorkoutSet]:
    def _make(**overrides: Any) -> WorkoutSet:
        base = WorkoutSet(
            PK=db.build_user_pk(USER_SUB),
            SK=db.build_set_sk(TEST_DATE_2, TEST_WORKOUT_ID_2, 1),
            type="set",
            exercise_id="squat",
            set_number=1,
            reps=8,
            weight_kg=Decimal("60"),
            rpe=7,
            created_at=fixed_now,
            updated_at=fixed_now,
        )
        return base.model_copy(update=overrides)

    return _make
