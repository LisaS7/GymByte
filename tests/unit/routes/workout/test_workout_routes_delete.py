from app.routes import workout as workout_routes
from tests.test_data import TEST_DATE_2, TEST_WORKOUT_ID_2
from tests.unit.routes.workout._helpers import WorkoutPath

W2_PATH = WorkoutPath(TEST_DATE_2, TEST_WORKOUT_ID_2)


# ──────────────────────────── DELETE /workout/{date}/{id} ────────────────────────────


def test_delete_workout_deletes_and_redirects(authenticated_client, fake_workout_repo):
    path = W2_PATH

    response = authenticated_client.delete(path.base, follow_redirects=False)

    assert response.status_code == 204
    assert response.headers["HX-Redirect"] == "/workout/all"
    assert fake_workout_repo.deleted_calls == [
        ("test-user-sub", path.workout_date, path.workout_id)
    ]


def test_delete_workout_returns_500_when_repo_raises(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "delete_workout_and_sets",
        workout_routes.WorkoutRepoError("boom-delete"),
    )

    response = authenticated_client.delete(W2_PATH.base, follow_redirects=False)

    assert response.status_code == 500


# ───────────────────── DELETE /workout/{date}/{id}/set/{set_number} ─────────────────────


def test_delete_set_deletes_and_returns_204(authenticated_client, fake_workout_repo):
    path = W2_PATH

    response = authenticated_client.delete(path.set_edit(1), follow_redirects=False)

    assert response.status_code == 204
    assert response.headers.get("HX-Trigger") == "workoutSetChanged"


def test_delete_set_returns_500_when_repo_raises(
    authenticated_client, fake_workout_repo, repo_raises
):
    repo_raises(
        fake_workout_repo,
        "delete_set",
        workout_routes.WorkoutRepoError("kaboom"),
    )

    response = authenticated_client.delete(
        W2_PATH.set_edit(1), follow_redirects=False
    )

    assert response.status_code == 500
    assert "Error deleting set" in response.text
