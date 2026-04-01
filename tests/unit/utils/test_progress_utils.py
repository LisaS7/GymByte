from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.utils.progress import (
    build_1rm_chart_data,
    build_distribution_chart_data,
    build_exercise_progress_data,
    build_frequency_chart_data,
    build_volume_chart_data,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

USER_SUB = "test-user"


def _make_workout(d: date, workout_id: str = "wid1"):
    from datetime import datetime, timezone

    from app.models.workout import Workout
    from app.utils.db import build_user_pk, build_workout_sk

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return Workout(
        PK=build_user_pk(USER_SUB),
        SK=build_workout_sk(d, workout_id),
        type="workout",
        date=d,
        name="Test Workout",
        created_at=now,
        updated_at=now,
    )


def _make_set(workout_date: date, workout_id: str, exercise_id: str, weight_kg: Decimal, set_number: int = 1):
    from datetime import datetime, timezone

    from app.models.workout import WorkoutSet
    from app.utils.db import build_set_sk, build_user_pk

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return WorkoutSet(
        PK=build_user_pk(USER_SUB),
        SK=build_set_sk(workout_date, workout_id, set_number),
        type="set",
        exercise_id=exercise_id,
        set_number=set_number,
        reps=5,
        weight_kg=weight_kg,
        created_at=now,
        updated_at=now,
    )


# ──────────────────────────────────────────────────────────────────────────────
# build_frequency_chart_data
# ──────────────────────────────────────────────────────────────────────────────


def test_frequency_chart_returns_exactly_n_entries():
    result = build_frequency_chart_data([], weeks=12)
    assert len(result["labels"]) == 12
    assert len(result["values"]) == 12


def test_frequency_chart_all_zeros_when_no_workouts():
    result = build_frequency_chart_data([], weeks=6)
    assert result["values"] == [0, 0, 0, 0, 0, 0]


def test_frequency_chart_counts_workouts_in_current_week(monkeypatch):
    today = date.today()
    # Use two workouts in the current ISO week
    mondays_offset = today.weekday()
    this_monday = today - timedelta(days=mondays_offset)
    wednesday = this_monday + timedelta(days=2)
    friday = this_monday + timedelta(days=4)

    workouts = [_make_workout(wednesday, "w1"), _make_workout(friday, "w2")]
    result = build_frequency_chart_data(workouts, weeks=4)

    # Current week is the last entry
    assert result["values"][-1] == 2


def test_frequency_chart_workouts_in_older_weeks_are_bucketed():
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    two_weeks_ago_monday = this_monday - timedelta(weeks=2)
    two_weeks_ago_thursday = two_weeks_ago_monday + timedelta(days=3)

    workouts = [_make_workout(two_weeks_ago_thursday, "w1")]
    result = build_frequency_chart_data(workouts, weeks=4)

    # Index -3 is 2 weeks ago (index -1=current, -2=last week, -3=2 weeks ago)
    assert result["values"][-3] == 1
    # Others should be zero
    assert result["values"][-1] == 0
    assert result["values"][-2] == 0


def test_frequency_chart_workouts_outside_window_are_ignored():
    today = date.today()
    very_old = today - timedelta(weeks=52)
    workouts = [_make_workout(very_old, "w1")]
    result = build_frequency_chart_data(workouts, weeks=12)
    assert sum(result["values"]) == 0


def test_frequency_chart_label_format():
    result = build_frequency_chart_data([], weeks=1)
    # Label should be like "Mar 3" — month abbreviation + space + day without leading zero
    label = result["labels"][0]
    # Check it has a space and looks like "Mon D" or "Mon DD"
    parts = label.split(" ")
    assert len(parts) == 2
    assert parts[0].isalpha()  # month abbreviation
    assert parts[1].isdigit()  # day number


# ──────────────────────────────────────────────────────────────────────────────
# build_exercise_progress_data
# ──────────────────────────────────────────────────────────────────────────────


def test_exercise_progress_empty_when_no_sets():
    result = build_exercise_progress_data([], "squat", "kg")
    assert result == {"labels": [], "values": [], "unit": "kg"}


def test_exercise_progress_empty_when_no_matching_sets():
    d = date(2025, 3, 1)
    s = _make_set(d, "wid1", "bench", Decimal("100"), set_number=1)

    result = build_exercise_progress_data([s], "squat", "kg")
    assert result == {"labels": [], "values": [], "unit": "kg"}


def test_exercise_progress_single_set():
    d = date(2025, 3, 1)
    s = _make_set(d, "wid1", "squat", Decimal("80"), set_number=1)

    result = build_exercise_progress_data([s], "squat", "kg")
    assert result["labels"] == ["2025-03-01"]
    assert result["values"] == [80.0]
    assert result["unit"] == "kg"


def test_exercise_progress_multiple_sets_same_day_returns_max():
    d = date(2025, 3, 1)
    s1 = _make_set(d, "wid1", "squat", Decimal("70"), set_number=1)
    s2 = _make_set(d, "wid1", "squat", Decimal("90"), set_number=2)
    s3 = _make_set(d, "wid1", "squat", Decimal("85"), set_number=3)

    result = build_exercise_progress_data([s1, s2, s3], "squat", "kg")
    assert result["labels"] == ["2025-03-01"]
    assert result["values"] == [90.0]


def test_exercise_progress_sorted_by_date_ascending():
    d1 = date(2025, 1, 1)
    d2 = date(2025, 2, 1)
    d3 = date(2025, 3, 1)
    s1 = _make_set(d1, "wid1", "squat", Decimal("60"))
    s2 = _make_set(d2, "wid2", "squat", Decimal("70"))
    s3 = _make_set(d3, "wid3", "squat", Decimal("80"))

    result = build_exercise_progress_data([s3, s1, s2], "squat", "kg")
    assert result["labels"] == ["2025-01-01", "2025-02-01", "2025-03-01"]
    assert result["values"] == [60.0, 70.0, 80.0]


def test_exercise_progress_kg_to_lb_conversion():
    d = date(2025, 3, 1)
    s = _make_set(d, "wid1", "squat", Decimal("100"), set_number=1)

    result = build_exercise_progress_data([s], "squat", "lb")
    assert result["unit"] == "lb"
    # 100 kg * 2.2046... ≈ 220.46
    assert abs(result["values"][0] - 220.46) < 0.1


def test_exercise_progress_sets_without_weight_are_ignored():
    d = date(2025, 3, 1)
    from datetime import datetime, timezone

    from app.models.workout import WorkoutSet
    from app.utils.db import build_set_sk, build_user_pk

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    s_no_weight = WorkoutSet(
        PK=build_user_pk(USER_SUB),
        SK=build_set_sk(d, "wid1", 1),
        type="set",
        exercise_id="squat",
        set_number=1,
        reps=5,
        weight_kg=None,
        created_at=now,
        updated_at=now,
    )

    result = build_exercise_progress_data([s_no_weight], "squat", "kg")
    assert result == {"labels": [], "values": [], "unit": "kg"}


def test_exercise_progress_unit_preserved_in_result():
    result = build_exercise_progress_data([], "squat", "lb")
    assert result["unit"] == "lb"


# ──────────────────────────────────────────────────────────────────────────────
# build_volume_chart_data
# ──────────────────────────────────────────────────────────────────────────────


def test_volume_chart_returns_exactly_n_entries():
    result = build_volume_chart_data([], "kg", weeks=8)
    assert len(result["labels"]) == 8
    assert len(result["values"]) == 8


def test_volume_chart_all_zeros_when_no_sets():
    result = build_volume_chart_data([], "kg", weeks=4)
    assert result["values"] == [0.0, 0.0, 0.0, 0.0]


def test_volume_chart_unit_preserved():
    result = build_volume_chart_data([], "lb", weeks=2)
    assert result["unit"] == "lb"


def test_volume_chart_accumulates_volume_in_current_week():
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    mid_week = this_monday + timedelta(days=2)

    # 3 sets × 5 reps × 100 kg = 1500 kg volume
    sets = [
        _make_set(mid_week, "wid1", "squat", Decimal("100"), set_number=i)
        for i in range(1, 4)
    ]
    # set reps=5 in _make_set already
    result = build_volume_chart_data(sets, "kg", weeks=4)
    # current week is last entry
    assert result["values"][-1] == 1500.0


def test_volume_chart_sets_outside_window_are_ignored():
    today = date.today()
    very_old = today - timedelta(weeks=52)
    s = _make_set(very_old, "wid1", "squat", Decimal("100"))
    result = build_volume_chart_data([s], "kg", weeks=4)
    assert sum(result["values"]) == 0.0


def test_volume_chart_exercise_id_filter():
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    mid_week = this_monday + timedelta(days=1)

    squat_set = _make_set(mid_week, "wid1", "squat", Decimal("100"), set_number=1)
    bench_set = _make_set(mid_week, "wid2", "bench", Decimal("80"), set_number=1)

    result = build_volume_chart_data([squat_set, bench_set], "kg", weeks=4, exercise_id="squat")
    # Only squat volume: 1 × 5 × 100 = 500
    assert result["values"][-1] == 500.0


def test_volume_chart_skips_sets_without_weight():
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    mid_week = this_monday + timedelta(days=1)

    from datetime import datetime, timezone

    from app.models.workout import WorkoutSet
    from app.utils.db import build_set_sk, build_user_pk

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    s_no_weight = WorkoutSet(
        PK=build_user_pk(USER_SUB),
        SK=build_set_sk(mid_week, "wid1", 1),
        type="set",
        exercise_id="squat",
        set_number=1,
        reps=5,
        weight_kg=None,
        created_at=now,
        updated_at=now,
    )
    result = build_volume_chart_data([s_no_weight], "kg", weeks=2)
    assert sum(result["values"]) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# build_1rm_chart_data
# ──────────────────────────────────────────────────────────────────────────────


def test_1rm_chart_empty_when_no_sets():
    result = build_1rm_chart_data([], "squat", "kg")
    assert result == {"labels": [], "values": [], "unit": "kg"}


def test_1rm_chart_empty_when_no_matching_exercise():
    d = date(2025, 3, 1)
    s = _make_set(d, "wid1", "bench", Decimal("100"), set_number=1)
    result = build_1rm_chart_data([s], "squat", "kg")
    assert result == {"labels": [], "values": [], "unit": "kg"}


def test_1rm_chart_epley_formula():
    # Epley: weight × (1 + reps / 30)
    # 100 kg × 5 reps = 100 × (1 + 5/30) = 100 × 1.1667 ≈ 116.67
    d = date(2025, 3, 1)
    s = _make_set(d, "wid1", "squat", Decimal("100"), set_number=1)
    result = build_1rm_chart_data([s], "squat", "kg")
    assert result["labels"] == ["2025-03-01"]
    expected = round(float(Decimal("100") * (1 + Decimal(5) / 30)), 2)
    assert result["values"] == [expected]


def test_1rm_chart_max_per_date():
    d = date(2025, 3, 1)
    # set1: 80 × (1 + 5/30) ≈ 93.33
    # set2: 100 × (1 + 5/30) ≈ 116.67 — should win
    s1 = _make_set(d, "wid1", "squat", Decimal("80"), set_number=1)
    s2 = _make_set(d, "wid1", "squat", Decimal("100"), set_number=2)
    result = build_1rm_chart_data([s1, s2], "squat", "kg")
    assert len(result["values"]) == 1
    assert result["values"][0] > 100.0


def test_1rm_chart_kg_to_lb_conversion():
    d = date(2025, 3, 1)
    s = _make_set(d, "wid1", "squat", Decimal("100"), set_number=1)
    result_kg = build_1rm_chart_data([s], "squat", "kg")
    result_lb = build_1rm_chart_data([s], "squat", "lb")
    assert result_lb["unit"] == "lb"
    # lb value should be roughly 2.2046x the kg value
    assert abs(result_lb["values"][0] / result_kg["values"][0] - 2.2046) < 0.01


def test_1rm_chart_skips_sets_without_weight():
    d = date(2025, 3, 1)
    from datetime import datetime, timezone

    from app.models.workout import WorkoutSet
    from app.utils.db import build_set_sk, build_user_pk

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    s_no_weight = WorkoutSet(
        PK=build_user_pk(USER_SUB),
        SK=build_set_sk(d, "wid1", 1),
        type="set",
        exercise_id="squat",
        set_number=1,
        reps=5,
        weight_kg=None,
        created_at=now,
        updated_at=now,
    )
    result = build_1rm_chart_data([s_no_weight], "squat", "kg")
    assert result == {"labels": [], "values": [], "unit": "kg"}


def test_1rm_chart_sorted_by_date_ascending():
    d1 = date(2025, 1, 1)
    d2 = date(2025, 2, 1)
    s1 = _make_set(d1, "wid1", "squat", Decimal("80"))
    s2 = _make_set(d2, "wid2", "squat", Decimal("90"))
    result = build_1rm_chart_data([s2, s1], "squat", "kg")
    assert result["labels"] == ["2025-01-01", "2025-02-01"]


# ──────────────────────────────────────────────────────────────────────────────
# build_distribution_chart_data
# ──────────────────────────────────────────────────────────────────────────────


def _make_exercise_obj(exercise_id: str, name: str, muscles: list[str]):
    from datetime import datetime, timezone

    from app.models.exercise import Exercise
    from app.utils.db import build_exercise_sk, build_user_pk

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return Exercise(
        PK=build_user_pk(USER_SUB),
        SK=build_exercise_sk(exercise_id),
        type="exercise",
        name=name,
        muscles=muscles,
        equipment="barbell",
        category="legs",
        created_at=now,
        updated_at=now,
    )


def test_distribution_chart_empty_when_no_sets():
    result = build_distribution_chart_data([], [])
    assert result == {
        "by_muscle": {"labels": [], "values": []},
        "by_exercise": {"labels": [], "values": []},
    }


def test_distribution_chart_counts_sets_by_exercise():
    d = date(2025, 3, 1)
    ex = _make_exercise_obj("squat", "Squat", ["quads"])
    s1 = _make_set(d, "wid1", "squat", Decimal("100"), set_number=1)
    s2 = _make_set(d, "wid1", "squat", Decimal("80"), set_number=2)

    result = build_distribution_chart_data([s1, s2], [ex])
    assert "Squat" in result["by_exercise"]["labels"]
    idx = result["by_exercise"]["labels"].index("Squat")
    assert result["by_exercise"]["values"][idx] == 2


def test_distribution_chart_counts_sets_by_muscle():
    d = date(2025, 3, 1)
    ex = _make_exercise_obj("squat", "Squat", ["quads", "glutes"])
    s = _make_set(d, "wid1", "squat", Decimal("100"), set_number=1)

    result = build_distribution_chart_data([s], [ex])
    assert "quads" in result["by_muscle"]["labels"]
    assert "glutes" in result["by_muscle"]["labels"]
    q_idx = result["by_muscle"]["labels"].index("quads")
    assert result["by_muscle"]["values"][q_idx] == 1


def test_distribution_chart_skips_sets_for_unknown_exercise():
    d = date(2025, 3, 1)
    # exercise list is empty — set's exercise_id won't be found
    s = _make_set(d, "wid1", "squat", Decimal("100"), set_number=1)
    result = build_distribution_chart_data([s], [])
    assert result["by_exercise"]["labels"] == []
    assert result["by_muscle"]["labels"] == []


def test_distribution_chart_top10_plus_other():
    d = date(2025, 3, 1)
    # 12 distinct exercises, each with a valid muscle group
    valid_muscles = [
        "chest", "shoulders", "triceps", "biceps", "lats",
        "upper_back", "lower_back", "core", "quads", "hamstrings",
        "glutes", "calves",
    ]
    exercises = [
        _make_exercise_obj(f"ex{i}", f"Exercise {i}", [valid_muscles[i]])
        for i in range(12)
    ]
    sets = [
        _make_set(d, "wid1", f"ex{i}", Decimal("100"), set_number=i + 1)
        for i in range(12)
    ]
    result = build_distribution_chart_data(sets, exercises)
    # Top 10 + "Other" for the 2 remaining
    assert len(result["by_exercise"]["labels"]) == 11
    assert result["by_exercise"]["labels"][-1] == "Other"
    assert result["by_exercise"]["values"][-1] == 2
