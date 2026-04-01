from decimal import Decimal

from app.routes import workout as workout_routes
from tests.conftest import FakeProfileRepo
from tests.test_data import TEST_DATE_2, TEST_WORKOUT_ID_2
from tests.unit.routes.workout._helpers import assert_html


def test_get_weight_unit_for_user_defaults_to_kg_when_profile_repo_raises():
    class BoomProfileRepo:
        def get_for_user(self, user_sub: str):
            raise Exception("kaboom")

    unit = workout_routes.get_weight_unit_for_user("test-user-sub", BoomProfileRepo())

    assert unit == "kg"


# ----------------- GET /workout/all -----------------


def test_get_all_workouts_success_renders_template(
    authenticated_client, fake_workout_repo
):
    fake_workout_repo.workouts_to_return = []

    response = authenticated_client.get("/workout/all")

    assert_html(response)
    assert fake_workout_repo.user_subs == ["test-user-sub"]


def test_get_all_workouts_handles_repo_error(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "get_all_for_user",
        workout_routes.WorkoutRepoError("boom"),
    )

    response = authenticated_client.get("/workout/all")
    assert response.status_code == 500


# ----------------- GET /workout/new-form -----------------


def test_get_new_form_renders_form(authenticated_client):
    response = authenticated_client.get("/workout/new-form")

    assert response.status_code == 200
    assert 'name="name"' in response.text


# -------------- GET /workout/{date}/{id}/set/form --------------


def test_get_new_set_form_renders_form(authenticated_client):
    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}/set/form?exercise_id=EX-1"
    )

    assert response.status_code == 200
    assert "<form" in response.text
    assert 'name="reps"' in response.text
    assert "EX-1" in response.text
    assert "Weight (kg)" in response.text


# ----------------- GET /workout/{date}/{id} (view workout) -----------------


def test_view_workout_renders_template(
    authenticated_client, fake_workout_repo, workout_factory, set_factory
):
    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = [
        set_factory(
            workout_date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2, set_number=1
        ),
        set_factory(
            workout_date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2, set_number=2
        ),
    ]

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}"
    )

    assert_html(response)
    assert "Weight (kg)" in response.text


def test_view_workout_returns_404_when_not_found(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "get_workout_with_sets",
        workout_routes.WorkoutNotFoundError("Workout not found"),
    )

    response = authenticated_client.get(f"/workout/{TEST_DATE_2.isoformat()}/NOPE")

    assert response.status_code == 404


def test_view_workout_returns_500_when_exercise_repo_raises(
    authenticated_client, fake_workout_repo, workout_factory, set_factory, app_instance
):
    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = [
        set_factory(
            workout_date=TEST_DATE_2,
            workout_id=TEST_WORKOUT_ID_2,
            exercise_id="EX-1",
        )
    ]

    class BrokenExerciseRepo:
        def get_exercise_by_id(self, user_sub, exercise_id):
            raise workout_routes.ExerciseRepoError("kaboom")

    app_instance.dependency_overrides[workout_routes.get_exercise_repo] = (
        lambda: BrokenExerciseRepo()
    )

    try:
        response = authenticated_client.get(
            f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}"
        )
        assert response.status_code == 500
    finally:
        app_instance.dependency_overrides.pop(workout_routes.get_exercise_repo, None)


def test_view_workout_returns_500_when_get_workout_with_sets_raises_repo_error(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "get_workout_with_sets",
        workout_routes.WorkoutRepoError("boom-fetch"),
    )

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}"
    )

    assert response.status_code == 500
    assert "Error fetching workout" in response.text


def test_view_workout_uses_lb_units_when_profile_imperial(
    authenticated_client, fake_workout_repo, workout_factory, set_factory, app_instance
):
    app_instance.dependency_overrides[workout_routes.get_profile_repo] = (
        lambda: FakeProfileRepo(unit="imperial")
    )

    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = [
        set_factory(
            workout_date=TEST_DATE_2,
            workout_id=TEST_WORKOUT_ID_2,
            set_number=1,
            weight_kg=Decimal("100"),
            exercise_id="EX-1",
        )
    ]

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}"
    )

    assert_html(response)
    assert "Weight (lb)" in response.text

    # Optional: assert the converted number appears (100kg -> 220.46226218lb)
    assert "220.46226218" in response.text

    app_instance.dependency_overrides.pop(workout_routes.get_profile_repo, None)


# -------------- GET /workout/{date}/{id}/edit-meta --------------


def test_edit_workout_meta_renders_form(
    authenticated_client, fake_workout_repo, workout_factory
):
    fake_workout_repo.workout_to_return = workout_factory(
        date=TEST_DATE_2, workout_id=TEST_WORKOUT_ID_2
    )
    fake_workout_repo.sets_to_return = []

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}/edit-meta"
    )

    assert response.status_code == 200
    assert 'name="tags"' in response.text
    assert 'name="notes"' in response.text


def test_edit_workout_meta_returns_404_when_not_found(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "get_workout_with_sets",
        workout_routes.WorkoutNotFoundError("Workout not found"),
    )

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/NOPE/edit-meta"
    )

    assert response.status_code == 404


def test_edit_workout_meta_returns_500_when_get_workout_with_sets_raises_repo_error(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "get_workout_with_sets",
        workout_routes.WorkoutRepoError("boom-fetch-edit"),
    )

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}/edit-meta"
    )

    assert response.status_code == 500
    assert "Error fetching workout" in response.text


# -------------- GET /workout/{date}/{id}/set/{set_number}/edit --------------


def test_get_edit_set_form_renders_form(
    authenticated_client, fake_workout_repo, set_factory
):
    fake_workout_repo.set_to_return = set_factory(
        workout_date=TEST_DATE_2,
        workout_id=TEST_WORKOUT_ID_2,
        set_number=1,
        reps=10,
        weight_kg=Decimal("70"),
        exercise_id="EX-1",
    )

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}/set/1/edit"
    )

    assert response.status_code == 200
    assert "<form" in response.text
    assert 'name="reps"' in response.text
    assert "Save Set" in response.text
    assert "#edit-set-form-container-EX-1-1" in response.text
    assert "Weight (kg)" in response.text


def test_get_edit_set_form_returns_500_when_repo_error(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "get_set",
        workout_routes.WorkoutRepoError("kaboom"),
    )

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}/set/1/edit"
    )

    assert response.status_code == 500


def test_get_edit_set_form_converts_kg_to_lb_for_imperial_user(
    authenticated_client,
    fake_workout_repo,
    set_factory,
    app_instance,
):
    class ImperialProfileRepo:
        def get_for_user(self, user_sub: str):
            class Profile:
                weight_unit = "lb"

            return Profile()

    app_instance.dependency_overrides[workout_routes.get_profile_repo] = (
        lambda: ImperialProfileRepo()
    )

    fake_workout_repo.set_to_return = set_factory(
        workout_date=TEST_DATE_2,
        workout_id=TEST_WORKOUT_ID_2,
        set_number=1,
        reps=10,
        weight_kg=Decimal("100"),
        exercise_id="EX-1",
    )

    response = authenticated_client.get(
        f"/workout/{TEST_DATE_2.isoformat()}/{TEST_WORKOUT_ID_2}/set/1/edit"
    )

    assert response.status_code == 200
    assert "Weight (lb)" in response.text
    assert "220.46226218" in response.text

    app_instance.dependency_overrides.pop(workout_routes.get_profile_repo, None)
