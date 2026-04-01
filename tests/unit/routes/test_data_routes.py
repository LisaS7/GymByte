"""
Tests for data export/import routes in app/routes/data.py.

The import route reads multipart form data (including CSRF token), deduplicates
exercises by name+equipment, remaps exercise IDs, and batch-writes to DynamoDB.
CSRF middleware is disabled globally in conftest, but the route does its own
manual CSRF check for multipart — we test that explicitly here.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.main import app
from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutSet
from app.repositories.errors import RepoError
from app.routes import data as data_routes
from app.utils import auth as auth_utils, db

USER_SUB = "test-import-user"

_NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Fake repos
# ──────────────────────────────────────────────────────────────────────────────


class FakeImportWorkoutRepo:
    def __init__(self):
        self.workouts_to_return: list[Workout] = []
        self.sets_to_return: list[WorkoutSet] = []

    def get_all_for_user(self, user_sub: str) -> list[Workout]:
        return self.workouts_to_return

    def get_all_workout_data_for_user(
        self, user_sub: str
    ) -> tuple[list[Workout], list[WorkoutSet]]:
        return self.workouts_to_return, self.sets_to_return


class FakeImportExerciseRepo:
    def __init__(self, exercises: list[Exercise] | None = None):
        self._exercises: list[Exercise] = exercises or []
        self.raise_on_get: bool = False

    def get_all_for_user(self, user_sub: str) -> list[Exercise]:
        if self.raise_on_get:
            raise RepoError("boom")
        return self._exercises


class FakeProfileRepo:
    def __init__(self, profile=None):
        self._profile = profile

    def get_for_user(self, user_sub: str):
        return self._profile


class FakeBatchWriter:
    def __init__(self):
        self.put_calls: list[dict] = []
        self.raise_on_exit: bool = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.raise_on_exit:
            raise Exception("batch write failed")
        return False

    def put_item(self, Item: dict) -> None:
        self.put_calls.append(Item)


class FakeDdbTable:
    def __init__(self):
        self._batch_writer = FakeBatchWriter()

    def batch_writer(self):
        return self._batch_writer


# ──────────────────────────────────────────────────────────────────────────────
# Fixture
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def data_client(app_instance, monkeypatch):
    """
    TestClient with auth stubbed out and data-route repo/table overrides.
    Yields (client, workout_repo, exercise_repo, fake_table).
    """
    workout_repo = FakeImportWorkoutRepo()
    exercise_repo = FakeImportExerciseRepo()
    profile_repo = FakeProfileRepo()
    fake_table = FakeDdbTable()

    def fake_auth(request: Request):
        return {"sub": USER_SUB}

    app_instance.dependency_overrides[auth_utils.require_auth] = fake_auth
    app_instance.dependency_overrides[data_routes.get_workout_repo] = (
        lambda: workout_repo
    )
    app_instance.dependency_overrides[data_routes.get_exercise_repo] = (
        lambda: exercise_repo
    )
    app_instance.dependency_overrides[data_routes.get_profile_repo] = (
        lambda: profile_repo
    )
    monkeypatch.setattr(db, "get_table", lambda: fake_table)

    client = TestClient(app_instance, raise_server_exceptions=False)

    try:
        yield client, workout_repo, exercise_repo, fake_table
    finally:
        app_instance.dependency_overrides.pop(auth_utils.require_auth, None)
        app_instance.dependency_overrides.pop(data_routes.get_workout_repo, None)
        app_instance.dependency_overrides.pop(data_routes.get_exercise_repo, None)
        app_instance.dependency_overrides.pop(data_routes.get_profile_repo, None)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

CSRF_TOKEN = "test-csrf-token"

_MINIMAL_EXPORT = {
    "schema_version": 1,
    "exported_at": _NOW_ISO,
    "user": {
        "display_name": "Test",
        "email": "t@t.com",
        "timezone": "UTC",
        "preferences": {"units": "metric", "theme": "light", "show_tips": True},
    },
    "exercises": [],
    "workouts": [],
}


def _post_import(client, payload: dict, *, csrf_cookie: str = CSRF_TOKEN, csrf_field: str = CSRF_TOKEN):
    """Post an import request with multipart data."""
    content = json.dumps(payload).encode()
    return client.post(
        "/profile/data/import",
        data={"csrf_token": csrf_field},
        files={"file": ("export.json", content, "application/json")},
        cookies={"csrf_token": csrf_cookie},
        follow_redirects=False,
    )


def _make_exercise(exercise_id: str, name: str, equipment: str = "barbell") -> Exercise:
    return Exercise(
        PK=db.build_user_pk(USER_SUB),
        SK=db.build_exercise_sk(exercise_id),
        type="exercise",
        name=name,
        muscles=["quads"],
        equipment=equipment,
        category="legs",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_workout(workout_id: str, date_str: str = "2025-03-01") -> Workout:
    from datetime import date
    d = date.fromisoformat(date_str)
    return Workout(
        PK=db.build_user_pk(USER_SUB),
        SK=db.build_workout_sk(d, workout_id),
        type="workout",
        date=d,
        name="Existing Workout",
        created_at=_NOW,
        updated_at=_NOW,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Import — CSRF checks
# ──────────────────────────────────────────────────────────────────────────────


def test_import_csrf_mismatch_returns_403(data_client):
    client, *_ = data_client
    resp = client.post(
        "/profile/data/import",
        data={"csrf_token": "wrong-token"},
        files={"file": ("f.json", b"{}", "application/json")},
        cookies={"csrf_token": "correct-token"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_import_missing_csrf_cookie_returns_403(data_client):
    client, *_ = data_client
    # No csrf_token cookie — cookie defaults to ""
    resp = client.post(
        "/profile/data/import",
        data={"csrf_token": CSRF_TOKEN},
        files={"file": ("f.json", b"{}", "application/json")},
        follow_redirects=False,
    )
    assert resp.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Import — file validation errors redirect back to profile
# ──────────────────────────────────────────────────────────────────────────────


def test_import_no_file_redirects_with_error(data_client):
    client, *_ = data_client
    resp = client.post(
        "/profile/data/import",
        data={"csrf_token": CSRF_TOKEN},
        cookies={"csrf_token": CSRF_TOKEN},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "import_error" in resp.headers["location"]


def test_import_invalid_json_redirects_with_error(data_client):
    client, *_ = data_client
    resp = client.post(
        "/profile/data/import",
        data={"csrf_token": CSRF_TOKEN},
        files={"file": ("bad.json", b"not json", "application/json")},
        cookies={"csrf_token": CSRF_TOKEN},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "import_error" in resp.headers["location"]


def test_import_wrong_schema_version_redirects_with_error(data_client):
    client, *_ = data_client
    payload = dict(_MINIMAL_EXPORT, schema_version=99)
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    assert "import_error" in resp.headers["location"]


# ──────────────────────────────────────────────────────────────────────────────
# Import — repo read failure redirects with error
# ──────────────────────────────────────────────────────────────────────────────


def test_import_redirects_when_exercise_repo_raises(data_client):
    client, _, exercise_repo, _ = data_client
    exercise_repo.raise_on_get = True
    resp = _post_import(client, _MINIMAL_EXPORT)
    assert resp.status_code == 303
    assert "import_error" in resp.headers["location"]


# ──────────────────────────────────────────────────────────────────────────────
# Import — happy path: empty payload redirects with summary
# ──────────────────────────────────────────────────────────────────────────────


def test_import_empty_payload_redirects_with_summary(data_client):
    client, *_ = data_client
    resp = _post_import(client, _MINIMAL_EXPORT)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert "import_exercises=0" in loc
    assert "import_workouts=0" in loc


# ──────────────────────────────────────────────────────────────────────────────
# Import — exercise deduplication
# ──────────────────────────────────────────────────────────────────────────────


def test_import_matches_existing_exercise_by_name_and_equipment(data_client):
    client, _, exercise_repo, fake_table = data_client
    exercise_repo._exercises = [_make_exercise("existing-id", "Squat", "barbell")]

    payload = dict(_MINIMAL_EXPORT)
    payload["exercises"] = [
        {
            "id": "imported-id",
            "name": "Squat",
            "muscles": ["quads"],
            "equipment": "barbell",
            "category": "legs",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
        }
    ]
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    # Matched, not created
    assert "import_matched=1" in loc
    assert "import_exercises=0" in loc
    # No DDB write for the matched exercise
    assert fake_table._batch_writer.put_calls == []


def test_import_creates_new_exercise_when_no_match(data_client):
    client, _, exercise_repo, fake_table = data_client
    exercise_repo._exercises = []

    payload = dict(_MINIMAL_EXPORT)
    payload["exercises"] = [
        {
            "id": "new-id",
            "name": "Deadlift",
            "muscles": ["hamstrings"],
            "equipment": "barbell",
            "category": "legs",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
        }
    ]
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    assert "import_exercises=1" in resp.headers["location"]
    assert len(fake_table._batch_writer.put_calls) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Import — workout deduplication
# ──────────────────────────────────────────────────────────────────────────────


def test_import_skips_workout_with_existing_id(data_client):
    client, workout_repo, _, _ = data_client
    workout_repo.workouts_to_return = [_make_workout("wid-existing")]

    payload = dict(_MINIMAL_EXPORT)
    payload["workouts"] = [
        {
            "id": "wid-existing",
            "date": "2025-03-01",
            "name": "Old Workout",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
            "sets": [],
        }
    ]
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    assert "import_skipped=1" in resp.headers["location"]
    assert "import_workouts=0" in resp.headers["location"]


def test_import_creates_new_workout_when_id_not_existing(data_client):
    client, workout_repo, _, fake_table = data_client
    workout_repo.workouts_to_return = []

    payload = dict(_MINIMAL_EXPORT)
    payload["workouts"] = [
        {
            "id": "wid-new",
            "date": "2025-04-01",
            "name": "New Workout",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
            "sets": [],
        }
    ]
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    assert "import_workouts=1" in resp.headers["location"]
    assert len(fake_table._batch_writer.put_calls) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Import — set ID remapping
# ──────────────────────────────────────────────────────────────────────────────


def test_import_sets_use_remapped_exercise_id(data_client):
    client, _, exercise_repo, fake_table = data_client
    exercise_repo._exercises = [_make_exercise("real-id", "Squat", "barbell")]

    payload = dict(_MINIMAL_EXPORT)
    payload["exercises"] = [
        {
            "id": "export-id",
            "name": "Squat",
            "muscles": ["quads"],
            "equipment": "barbell",
            "category": "legs",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
        }
    ]
    payload["workouts"] = [
        {
            "id": "wid-new",
            "date": "2025-04-01",
            "name": "Workout",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
            "sets": [
                {
                    "set_number": 1,
                    "exercise_id": "export-id",
                    "reps": 5,
                    "weight_kg": 100.0,
                    "rpe": 8,
                    "created_at": _NOW_ISO,
                    "updated_at": _NOW_ISO,
                }
            ],
        }
    ]
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    assert "import_sets=1" in resp.headers["location"]

    # The written set item should use the remapped "real-id"
    set_items = [
        item for item in fake_table._batch_writer.put_calls
        if item.get("type") == "set"
    ]
    assert len(set_items) == 1
    assert set_items[0]["exercise_id"] == "real-id"


def test_import_set_with_unknown_exercise_id_is_skipped(data_client):
    client, _, exercise_repo, fake_table = data_client
    exercise_repo._exercises = []  # no exercises in account

    payload = dict(_MINIMAL_EXPORT)
    payload["workouts"] = [
        {
            "id": "wid-new",
            "date": "2025-04-01",
            "name": "Workout",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
            "sets": [
                {
                    "set_number": 1,
                    "exercise_id": "unknown-id",
                    "reps": 5,
                    "weight_kg": 100.0,
                    "created_at": _NOW_ISO,
                    "updated_at": _NOW_ISO,
                }
            ],
        }
    ]
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    # Workout created, set skipped — no set items written
    set_items = [
        item for item in fake_table._batch_writer.put_calls
        if item.get("type") == "set"
    ]
    assert set_items == []


# ──────────────────────────────────────────────────────────────────────────────
# Import — batch write failure redirects with error
# ──────────────────────────────────────────────────────────────────────────────


def test_import_redirects_when_batch_write_fails(data_client):
    client, _, _, fake_table = data_client
    fake_table._batch_writer.raise_on_exit = True

    payload = dict(_MINIMAL_EXPORT)
    payload["exercises"] = [
        {
            "id": "new-id",
            "name": "Bench Press",
            "muscles": ["chest"],
            "equipment": "barbell",
            "category": "push",
            "created_at": _NOW_ISO,
            "updated_at": _NOW_ISO,
        }
    ]
    resp = _post_import(client, payload)
    assert resp.status_code == 303
    assert "import_error" in resp.headers["location"]
