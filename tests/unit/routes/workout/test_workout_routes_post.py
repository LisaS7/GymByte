from datetime import date
from decimal import Decimal

from app.routes import workout as workout_routes
from tests.test_data import TEST_DATE_2, TEST_WORKOUT_ID_2
from tests.unit.routes.workout._helpers import (
    WorkoutPath,
    post_edit_set,
    post_meta,
    post_set,
)

W2_PATH = WorkoutPath(TEST_DATE_2, TEST_WORKOUT_ID_2)


# ───────────────────────── POST /workout/create ─────────────────────────


def test_create_workout_creates_item_and_redirects(
    authenticated_client, fake_workout_repo
):
    response = authenticated_client.post(
        "/workout/create",
        data={"date": TEST_DATE_2.isoformat(), "name": "Bench Party"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert len(fake_workout_repo.created_workouts) == 1

    created = fake_workout_repo.created_workouts[0]
    assert created.date == TEST_DATE_2
    assert created.name == "Bench Party"
    assert fake_workout_repo.user_subs == ["test-user-sub"]

    expected_location = f"/workout/{created.date.isoformat()}/{created.workout_id}"
    assert response.headers["location"] == expected_location


def test_create_workout_returns_500_when_repo_raises(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "create_workout",
        workout_routes.WorkoutRepoError("boom-create"),
    )

    response = authenticated_client.post(
        "/workout/create",
        data={"date": TEST_DATE_2.isoformat(), "name": "Broken Bench"},
        follow_redirects=False,
    )

    assert response.status_code == 500


# ───────────────────── POST /workout/{date}/{id}/set/add ─────────────────────


def test_create_workout_set_adds_set_and_returns_204(
    authenticated_client, fake_workout_repo
):
    path = W2_PATH

    response = post_set(authenticated_client, path, exercise_id="EX-BENCH")

    assert response.status_code == 204
    assert response.headers.get("HX-Trigger") == "workoutSetChanged"

    assert len(fake_workout_repo.added_sets) == 1
    user_sub, w_date, w_id, exercise_id, form = fake_workout_repo.added_sets[0]

    assert user_sub == "test-user-sub"
    assert w_date == TEST_DATE_2
    assert w_id == TEST_WORKOUT_ID_2
    assert exercise_id == "EX-BENCH"

    assert form.reps == 8
    assert form.weight_kg == Decimal("60.5")
    assert form.rpe == 9


def test_create_workout_set_returns_500_when_repo_raises(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "add_set",
        workout_routes.WorkoutRepoError("boom-add-set"),
    )

    response = post_set(authenticated_client, W2_PATH)

    assert response.status_code == 500


def test_add_set_converts_lb_to_kg_for_imperial_user(
    authenticated_client,
    fake_workout_repo,
    app_instance,
):
    # Fake imperial profile repo
    class ImperialProfileRepo:
        def get_for_user(self, user_sub: str):
            class Profile:
                weight_unit = "lb"

            return Profile()

    app_instance.dependency_overrides[workout_routes.get_profile_repo] = (
        lambda: ImperialProfileRepo()
    )

    # Capture what gets passed into the repo
    captured = {}

    def fake_add_set(user_sub, workout_date, workout_id, exercise_id, form):
        captured["weight_kg"] = form.weight_kg

    fake_workout_repo.add_set = fake_add_set

    response = authenticated_client.post(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}/set/add?exercise_id=EX-1",
        data={
            "reps": 5,
            "weight_kg": "225",  # user-entered *lb*
        },
    )

    assert response.status_code == 204

    # 225 lb ≈ 102.058 kg
    assert captured["weight_kg"] is not None
    assert captured["weight_kg"] != Decimal("225")
    assert captured["weight_kg"].quantize(Decimal("0.001")) == Decimal("102.058")

    app_instance.dependency_overrides.pop(workout_routes.get_profile_repo, None)


# ─────────────────── POST /workout/{date}/{id}/meta ───────────────────


def test_update_workout_meta_updates_workout_and_renders(
    authenticated_client,
    fake_workout_repo,
    fixed_now,
    workout_factory,
    set_factory,
):
    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = [
        set_factory(workout_date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2)
    ]

    response = post_meta(
        authenticated_client,
        W2_PATH,
        tags="push, legs, heavy",
        notes="Felt strong",
    )

    assert response.status_code == 200
    assert len(fake_workout_repo.updated_workouts) == 1

    updated = fake_workout_repo.updated_workouts[0]
    assert updated.tags == ["push", "legs", "heavy"]
    assert updated.notes == "Felt strong"
    assert updated.updated_at == fixed_now


def test_update_workout_meta_returns_404_when_not_found(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "get_workout_with_sets",
        workout_routes.WorkoutNotFoundError("Workout not found"),
    )

    response = post_meta(authenticated_client, W2_PATH)

    assert response.status_code == 404


def test_update_workout_meta_returns_500_when_get_workout_with_sets_raises_repo_error(
    authenticated_client, fake_workout_repo, repo_raises
):
    path = W2_PATH
    repo_raises(
        fake_workout_repo,
        "get_workout_with_sets",
        workout_routes.WorkoutRepoError("boom-fetch-update"),
    )

    response = post_meta(authenticated_client, path)

    assert response.status_code == 500
    assert "Error fetching workout" in response.text


def test_update_workout_meta_returns_500_when_update_fails(
    authenticated_client,
    fake_workout_repo,
    workout_factory,
    set_factory,
    repo_raises,
):
    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = [
        set_factory(workout_date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2)
    ]

    repo_raises(
        fake_workout_repo,
        "edit_workout",
        workout_routes.WorkoutRepoError("boom-update"),
    )

    response = post_meta(authenticated_client, W2_PATH)

    assert response.status_code == 500


def test_update_workout_meta_returns_500_when_move_date_fails(
    authenticated_client,
    fake_workout_repo,
    workout_factory,
    set_factory,
):
    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = [
        set_factory(workout_date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2)
    ]

    new_date = date(2025, 11, 4)

    def broken_move(user_sub, workout, new_date_param, sets):
        raise workout_routes.WorkoutRepoError("kaboom")

    fake_workout_repo.move_workout_date = broken_move

    response = post_meta(authenticated_client, W2_PATH, date=new_date.isoformat())

    assert response.status_code == 500


def test_update_workout_meta_moves_date_and_sets_hx_redirect(
    authenticated_client,
    fake_workout_repo,
    workout_factory,
    set_factory,
):
    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = [
        set_factory(workout_date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2)
    ]

    new_date = date(2025, 11, 4)
    moved_workout = workout_factory(date=new_date, workout_id=TEST_WORKOUT_ID_2)

    def fake_move_workout_date(user_sub, workout, new_date_param, sets):
        assert user_sub == "test-user-sub"
        assert new_date_param == new_date
        return moved_workout

    fake_workout_repo.move_workout_date = fake_move_workout_date

    response = post_meta(authenticated_client, W2_PATH, date=new_date.isoformat())
    expected_url = f"/workout/{new_date.isoformat()}/{TEST_WORKOUT_ID_2}"

    assert response.status_code == 204
    assert response.headers.get("HX-Redirect").endswith(expected_url)


# ───────────── POST /workout/{date}/{id}/set/{set_number} ─────────────


def test_edit_set_updates_and_returns_204(authenticated_client, fake_workout_repo):
    calls: dict = {}

    def fake_edit_set(user_sub, workout_date, workout_id, set_number, form):
        calls["user_sub"] = user_sub
        calls["workout_date"] = workout_date
        calls["workout_id"] = workout_id
        calls["set_number"] = set_number
        calls["form"] = form

    fake_workout_repo.edit_set = fake_edit_set

    response = post_edit_set(authenticated_client, W2_PATH)

    assert response.status_code == 204
    assert response.headers.get("HX-Trigger") == "workoutSetChanged"

    assert calls["user_sub"] == "test-user-sub"
    assert calls["workout_date"] == TEST_DATE_2
    assert calls["workout_id"] == TEST_WORKOUT_ID_2
    assert calls["set_number"] == 1

    form = calls["form"]
    assert form.reps == 10
    assert form.weight_kg == Decimal("70.5")
    assert form.rpe == 8


def test_edit_set_returns_404_when_set_not_found(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "edit_set",
        workout_routes.WorkoutNotFoundError("nope"),
    )

    response = post_edit_set(authenticated_client, W2_PATH)

    assert response.status_code == 404
    assert "Set not found" in response.text


def test_edit_set_returns_500_when_repo_error(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "edit_set",
        workout_routes.WorkoutRepoError("kaboom"),
    )

    response = post_edit_set(authenticated_client, W2_PATH)

    assert response.status_code == 500
    assert "Error updating set" in response.text
