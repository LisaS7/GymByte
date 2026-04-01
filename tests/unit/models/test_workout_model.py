from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.test_data import (
    TEST_CREATED_DATETIME,
    TEST_DATE_1,
    TEST_UPDATED_DATETIME,
    TEST_WORKOUT_SK_1,
    USER_PK,
)

from app.models.workout import WorkoutSetCreate

# ------------ Workout tests ------------


def test_workout_model_creates_instance_with_expected_fields(example_workout):
    assert example_workout.PK == USER_PK
    assert example_workout.SK == TEST_WORKOUT_SK_1
    assert example_workout.type == "workout"
    assert example_workout.date == TEST_DATE_1
    assert example_workout.tags == ["push", "upper"]
    assert example_workout.notes == "Felt strong"
    assert isinstance(example_workout.created_at, datetime)
    assert isinstance(example_workout.updated_at, datetime)


def test_workout_type_must_be_literal_workout(workout):
    with pytest.raises(ValidationError):
        workout(type="cardio")


def test_workout_notes_is_optional_and_can_be_none(workout):
    w = workout(notes=None)
    assert w.notes is None


def test_workout_to_ddb_item_uses_date_and_dt_helpers(monkeypatch, workout):
    # Track calls to fake converters
    date_calls = []
    dt_calls = []

    def fake_date_to_iso(d: date) -> str:
        date_calls.append(d)
        return f"DATE-{d:%Y%m%d}"

    def fake_dt_to_iso(dt: datetime) -> str:
        dt_calls.append(dt)
        return f"DT-{dt:%Y%m%d%H%M%S}"

    # Patch inside the workout module
    monkeypatch.setattr("app.models.workout.date_to_iso", fake_date_to_iso)
    monkeypatch.setattr("app.models.workout.dt_to_iso", fake_dt_to_iso)

    w = workout(
        date=TEST_DATE_1,
        created_at=TEST_CREATED_DATETIME,
        updated_at=TEST_UPDATED_DATETIME,
    )

    item = w.to_ddb_item()

    # The dict has the converted values, not raw datetimes
    assert item["date"] == "DATE-20251101"
    assert item["created_at"] == "DT-20250101120000"
    assert item["updated_at"] == "DT-20250102120000"

    # Sanity check: no datetime objects sneak through
    assert not isinstance(item["date"], date)
    assert not isinstance(item["created_at"], datetime)
    assert not isinstance(item["updated_at"], datetime)


# ------------ WorkoutSet tests ------------


def test_workout_set_model_creates_instance_with_expected_fields(example_set):

    assert example_set.PK == USER_PK
    assert example_set.type == "set"
    assert example_set.exercise_id == "EXERCISE#BENCH"
    assert example_set.set_number == 1
    assert example_set.reps == 8
    assert example_set.weight_kg == Decimal("60.5")
    assert example_set.rpe == 8
    assert isinstance(example_set.created_at, datetime)
    assert isinstance(example_set.updated_at, datetime)


def test_workoutset_workout_id_extracts_from_SK(workout_set):
    ws = workout_set(SK="WORKOUT#2025-11-04#W42#SET#001")
    assert ws.workout_id == "W42"


def test_workoutset_workout_id_raises_on_invalid_SK(workout_set):
    ws = workout_set(SK="WORKOUT#ONLYTWO")
    with pytest.raises(ValueError) as exc:
        _ = ws.workout_id

    assert "Invalid SK format" in str(exc.value)


def test_workout_set_type_must_be_literal_set(workout_set):
    with pytest.raises(ValidationError):
        workout_set(type="workout")  # not allowed per Literal


def test_workout_set_to_ddb_item_uses_dt_helper(monkeypatch, workout_set):
    dt_calls = []

    def fake_dt_to_iso(dt: datetime) -> str:
        dt_calls.append(dt)
        return f"DT-{dt:%Y%m%d%H%M%S}"

    monkeypatch.setattr("app.models.workout.dt_to_iso", fake_dt_to_iso)

    created_at = datetime(2025, 11, 4, 18, 5, 0)
    updated_at = datetime(2025, 11, 4, 18, 5, 30)

    ws = workout_set(
        created_at=created_at,
        updated_at=updated_at,
    )

    item = ws.to_ddb_item()

    # Helpers used for both timestamps
    assert item["created_at"] == "DT-20251104180500"
    assert item["updated_at"] == "DT-20251104180530"

    # Decimal should still be Decimal (model_dump keeps it)
    assert isinstance(item["weight_kg"], Decimal)

    # And no datetime objects in the final dict
    assert not isinstance(item["created_at"], datetime)
    assert not isinstance(item["updated_at"], datetime)


def test_workoutsetcreate_as_form_builds_expected_model():
    ws_create = WorkoutSetCreate.as_form(
        reps=8,
        weight_kg=Decimal("60.5"),
        rpe=9,
    )

    assert isinstance(ws_create, WorkoutSetCreate)
    assert ws_create.reps == 8
    assert ws_create.weight_kg == Decimal("60.5")
    assert ws_create.rpe == 9


def test_workoutsetcreate_as_form_allows_optional_fields_none():
    ws_create = WorkoutSetCreate.as_form(
        reps=5,
        weight_kg=None,
        rpe=None,
    )

    assert ws_create.reps == 5
    assert ws_create.weight_kg is None
    assert ws_create.rpe is None
