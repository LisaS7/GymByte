"""
Tests for GET /progress and GET /progress/exercise.

Pattern mirrors the other route test files:
  - FakeWorkoutRepo / FakeExerciseRepo are defined in conftest.py
  - We override progress_routes.get_workout_repo, get_exercise_repo, get_profile_repo
  - FakeProfileRepo from conftest is reused for progress route tests
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.profile import Preferences, UserProfile
from app.models.workout import Workout, WorkoutSet
from app.routes import progress as progress_routes
from app.utils import auth as auth_utils, db
from tests.unit.routes.conftest import FakeExerciseRepo, FakeProfileRepo

USER_SUB = "test-user-sub"


# ──────────────────────────────────────────────────────────────────────────────
# Extended FakeWorkoutRepo with get_all_workout_data_for_user
# ──────────────────────────────────────────────────────────────────────────────


class FakeProgressWorkoutRepo:
    def __init__(self):
        self.workouts_to_return: list[Workout] = []
        self.sets_to_return: list[WorkoutSet] = []

    def get_all_for_user(self, user_sub: str) -> list[Workout]:
        return self.workouts_to_return

    def get_all_workout_data_for_user(
        self, user_sub: str
    ) -> tuple[list[Workout], list[WorkoutSet]]:
        return self.workouts_to_return, self.sets_to_return

    def get_sets_for_exercise(self, exercise_id: str) -> list[WorkoutSet]:
        return [s for s in self.sets_to_return if s.exercise_id == exercise_id]


# ──────────────────────────────────────────────────────────────────────────────
# Factories
# ──────────────────────────────────────────────────────────────────────────────


def _make_workout(d: date, workout_id: str = "wid1") -> Workout:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return Workout(
        PK=db.build_user_pk(USER_SUB),
        SK=db.build_workout_sk(d, workout_id),
        type="workout",
        date=d,
        name="Test Workout",
        created_at=now,
        updated_at=now,
    )


def _make_set(
    workout_date: date,
    workout_id: str,
    exercise_id: str,
    weight_kg: Decimal = Decimal("80"),
    set_number: int = 1,
) -> WorkoutSet:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return WorkoutSet(
        PK=db.build_user_pk(USER_SUB),
        SK=db.build_set_sk(workout_date, workout_id, set_number),
        type="set",
        exercise_id=exercise_id,
        set_number=set_number,
        reps=5,
        weight_kg=weight_kg,
        created_at=now,
        updated_at=now,
    )


def _make_profile(units: str = "metric") -> UserProfile:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return UserProfile(
        PK=db.build_user_pk(USER_SUB),
        SK="PROFILE",
        display_name="Test User",
        email="test@example.com",
        timezone="Europe/London",
        created_at=now,
        updated_at=now,
        preferences=Preferences(units=units),
    )


def _make_exercise(exercise_id: str = "squat-id", name: str = "Squat"):
    from app.models.exercise import Exercise

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return Exercise(
        PK=db.build_user_pk(USER_SUB),
        SK=db.build_exercise_sk(exercise_id),
        type="exercise",
        name=name,
        equipment="barbell",
        category="legs",
        muscles=["quads"],
        created_at=now,
        updated_at=now,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def progress_client(app_instance):
    """
    TestClient with auth stubbed out and progress-specific repo overrides.
    Yields (client, workout_repo, exercise_repo, profile_repo).
    """
    from fastapi import Request
    from fastapi.testclient import TestClient

    workout_repo = FakeProgressWorkoutRepo()
    exercise_repo = FakeExerciseRepo()
    profile_repo_instance = FakeProfileRepo()

    def fake_auth(request: Request):
        return {"sub": USER_SUB}

    app_instance.dependency_overrides[auth_utils.require_auth] = fake_auth
    app_instance.dependency_overrides[progress_routes.get_workout_repo] = (
        lambda: workout_repo
    )
    app_instance.dependency_overrides[progress_routes.get_exercise_repo] = (
        lambda: exercise_repo
    )
    app_instance.dependency_overrides[progress_routes.get_profile_repo] = (
        lambda: profile_repo_instance
    )

    client = TestClient(app_instance, raise_server_exceptions=False)

    try:
        yield client, workout_repo, exercise_repo, profile_repo_instance
    finally:
        app_instance.dependency_overrides.pop(auth_utils.require_auth, None)
        app_instance.dependency_overrides.pop(progress_routes.get_workout_repo, None)
        app_instance.dependency_overrides.pop(progress_routes.get_exercise_repo, None)
        app_instance.dependency_overrides.pop(progress_routes.get_profile_repo, None)


# ──────────────────────────────────────────────────────────────────────────────
# GET /progress
# ──────────────────────────────────────────────────────────────────────────────


def test_progress_page_returns_200(progress_client):
    client, workout_repo, exercise_repo, _ = progress_client
    resp = client.get("/progress")
    assert resp.status_code == 200


def test_progress_page_contains_freq_chart_canvas(progress_client):
    client, _, _, _ = progress_client
    resp = client.get("/progress")
    assert 'id="freq-chart"' in resp.text


def test_progress_page_lists_exercises_in_select(progress_client):
    client, _, exercise_repo, _ = progress_client
    exercise_repo.seed(_make_exercise("squat-id", "Barbell Squat"))
    exercise_repo.seed(_make_exercise("bench-id", "Bench Press"))

    resp = client.get("/progress")

    assert "Barbell Squat" in resp.text
    assert "Bench Press" in resp.text
    assert 'id="exercise-select"' in resp.text


def test_progress_page_shows_empty_state_when_no_exercises(progress_client):
    client, _, _, _ = progress_client
    resp = client.get("/progress")
    assert "No exercises yet" in resp.text


def test_progress_page_freq_data_is_json_in_data_attribute(progress_client):
    client, workout_repo, _, _ = progress_client
    d = date(2025, 3, 3)
    workout_repo.workouts_to_return = [_make_workout(d, "wid1")]

    resp = client.get("/progress")

    assert resp.status_code == 200
    # freq_data is a JSON string embedded in data-chart="..."
    assert "data-chart=" in resp.text


# ──────────────────────────────────────────────────────────────────────────────
# GET /progress/exercise
# ──────────────────────────────────────────────────────────────────────────────


def test_exercise_chart_returns_200(progress_client):
    client, workout_repo, exercise_repo, _ = progress_client
    ex = _make_exercise("squat-id")
    exercise_repo.seed(ex)

    d = date(2025, 3, 1)
    workout_repo.workouts_to_return = [_make_workout(d, "wid1")]
    workout_repo.sets_to_return = [_make_set(d, "wid1", "squat-id", Decimal("100"))]

    resp = client.get("/progress/exercise?exercise_id=squat-id")
    assert resp.status_code == 200


def test_exercise_chart_contains_canvas_when_data_exists(progress_client):
    client, workout_repo, exercise_repo, _ = progress_client
    ex = _make_exercise("squat-id")
    exercise_repo.seed(ex)

    d = date(2025, 3, 1)
    workout_repo.workouts_to_return = [_make_workout(d, "wid1")]
    workout_repo.sets_to_return = [_make_set(d, "wid1", "squat-id", Decimal("100"))]

    resp = client.get("/progress/exercise?exercise_id=squat-id")

    assert 'id="exercise-chart"' in resp.text


def test_exercise_chart_shows_empty_state_when_no_sets(progress_client):
    client, workout_repo, exercise_repo, _ = progress_client
    ex = _make_exercise("squat-id")
    exercise_repo.seed(ex)

    resp = client.get("/progress/exercise?exercise_id=squat-id")

    assert resp.status_code == 200
    assert "No sets logged yet" in resp.text


def test_exercise_chart_returns_404_for_unknown_exercise(progress_client):
    client, _, _, _ = progress_client
    resp = client.get("/progress/exercise?exercise_id=does-not-exist")
    assert resp.status_code == 404


def test_exercise_chart_imperial_user_gets_lb_unit(progress_client):
    client, workout_repo, exercise_repo, profile_repo = progress_client
    # Switch to imperial
    profile_repo._profile = _make_profile("imperial")

    ex = _make_exercise("squat-id")
    exercise_repo.seed(ex)

    d = date(2025, 3, 1)
    workout_repo.workouts_to_return = [_make_workout(d, "wid1")]
    workout_repo.sets_to_return = [_make_set(d, "wid1", "squat-id", Decimal("100"))]

    resp = client.get("/progress/exercise?exercise_id=squat-id")

    assert resp.status_code == 200
    assert '"lb"' in resp.text or "lb" in resp.text
