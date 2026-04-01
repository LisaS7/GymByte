from decimal import Decimal

import pytest
from tests.test_data import (
    TEST_CREATED_DATETIME,
    TEST_DATE_1,
    TEST_SET_SK_1,
    TEST_UPDATED_DATETIME,
    TEST_WORKOUT_SK_1,
    USER_EMAIL,
    USER_PK,
)

from app.models.exercise import Exercise
from app.models.profile import UserProfile
from app.models.workout import Workout, WorkoutSet

# ───────────── Exercise  ─────────────


@pytest.fixture
def exercise():
    """Factory fixture for Exercise instances."""

    def _make(**overrides):
        defaults = {
            "PK": "EXERCISE#PUSHUP",
            "SK": "EXERCISE#PUSHUP",
            "type": "exercise",
            "name": "Push-up",
            "muscles": ["chest", "triceps"],
            "equipment": "bodyweight",
            "category": "push",
            "created_at": TEST_CREATED_DATETIME,
            "updated_at": TEST_UPDATED_DATETIME,
        }
        return Exercise(**{**defaults, **overrides})

    return _make


@pytest.fixture
def example_exercise(exercise):
    return exercise()


# ───────────── Profile  ─────────────
@pytest.fixture
def profile():
    """Factory fixture for UserProfile instances."""

    def _make(**overrides):
        defaults = {
            "PK": USER_PK,
            "SK": "PROFILE",
            "display_name": "Lisa Test",
            "email": USER_EMAIL,
            "created_at": TEST_CREATED_DATETIME,
            "updated_at": TEST_UPDATED_DATETIME,
            "timezone": "Europe/London",
        }
        return UserProfile(**{**defaults, **overrides})

    return _make


@pytest.fixture
def example_profile(profile):
    return profile()


# ───────────── Workout  ─────────────


@pytest.fixture
def workout():
    """Factory fixture for Workout instances."""

    def _make(**overrides):
        defaults = {
            "PK": USER_PK,
            "SK": TEST_WORKOUT_SK_1,
            "type": "workout",
            "date": TEST_DATE_1,
            "name": "Workout A",
            "tags": ["push", "upper"],
            "notes": "Felt strong",
            "created_at": TEST_CREATED_DATETIME,
            "updated_at": TEST_UPDATED_DATETIME,
        }
        return Workout(**{**defaults, **overrides})

    return _make


@pytest.fixture
def example_workout(workout):
    """Default Workout instance for tests that don't need customization."""
    return workout()


# ───────────── WorkoutSet  ─────────────


@pytest.fixture
def workout_set():
    """Factory fixture for WorkoutSet instances."""

    def _make(**overrides):
        defaults = {
            "PK": USER_PK,
            "SK": TEST_SET_SK_1,
            "type": "set",
            "exercise_id": "EXERCISE#BENCH",
            "set_number": 1,
            "reps": 8,
            "weight_kg": Decimal("60.5"),
            "rpe": 8,
            "created_at": TEST_CREATED_DATETIME,
            "updated_at": TEST_UPDATED_DATETIME,
        }
        return WorkoutSet(**{**defaults, **overrides})

    return _make


@pytest.fixture
def example_set(workout_set):
    """Default WorkoutSet instance for tests that don't need customization."""
    return workout_set()
