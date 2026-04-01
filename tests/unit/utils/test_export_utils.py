import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.utils.export import parse_import_file

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()

_MINIMAL_PAYLOAD = {
    "schema_version": 1,
    "exported_at": _NOW,
    "user": {
        "display_name": "Test User",
        "email": "test@example.com",
        "timezone": "Europe/London",
        "preferences": {"units": "metric", "theme": "light", "show_tips": True},
    },
    "exercises": [],
    "workouts": [],
}


def _encode(payload: dict) -> bytes:
    return json.dumps(payload).encode()


# ──────────────────────────────────────────────────────────────────────────────
# parse_import_file — happy path
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_import_file_valid_minimal_payload():
    result = parse_import_file(_encode(_MINIMAL_PAYLOAD))
    assert result.schema_version == 1
    assert result.exercises == []
    assert result.workouts == []


def test_parse_import_file_returns_exercises_and_workouts():
    payload = dict(_MINIMAL_PAYLOAD)
    payload["exercises"] = [
        {
            "id": "squat-id",
            "name": "Squat",
            "muscles": ["quads"],
            "equipment": "barbell",
            "category": "legs",
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    ]
    payload["workouts"] = [
        {
            "id": "wid1",
            "date": "2025-03-01",
            "name": "Leg Day",
            "created_at": _NOW,
            "updated_at": _NOW,
            "sets": [],
        }
    ]
    result = parse_import_file(_encode(payload))
    assert len(result.exercises) == 1
    assert result.exercises[0].name == "Squat"
    assert len(result.workouts) == 1
    assert result.workouts[0].name == "Leg Day"


# ──────────────────────────────────────────────────────────────────────────────
# parse_import_file — error branches
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_import_file_rejects_oversized_content():
    big = b"x" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="5 MB"):
        parse_import_file(big)


def test_parse_import_file_rejects_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_import_file(b"not json {{{")


def test_parse_import_file_rejects_non_object_json():
    with pytest.raises(ValueError, match="JSON object"):
        parse_import_file(b"[1, 2, 3]")


def test_parse_import_file_rejects_unsupported_schema_version():
    payload = dict(_MINIMAL_PAYLOAD, schema_version=99)
    with pytest.raises(ValueError, match="Unsupported export version"):
        parse_import_file(_encode(payload))


def test_parse_import_file_rejects_missing_schema_version():
    payload = {k: v for k, v in _MINIMAL_PAYLOAD.items() if k != "schema_version"}
    with pytest.raises(ValueError, match="Unsupported export version"):
        parse_import_file(_encode(payload))


def test_parse_import_file_rejects_structurally_invalid_payload():
    # schema_version is correct but required fields are missing
    with pytest.raises(ValueError, match="invalid structure"):
        parse_import_file(json.dumps({"schema_version": 1}).encode())
