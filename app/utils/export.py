from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from app.models.export import (
    ExportExercise,
    ExportPayload,
    ExportSet,
    ExportUser,
    ExportWorkout,
)
from app.models.profile import UserProfile
from app.repositories.exercise import DynamoExerciseRepository
from app.repositories.workout import DynamoWorkoutRepository
from app.utils.dates import dt_to_iso, now

SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
_MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MB


class _ExportEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return dt_to_iso(obj)
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def build_export_payload(
    user_sub: str,
    profile: UserProfile,
    workout_repo: DynamoWorkoutRepository,
    exercise_repo: DynamoExerciseRepository,
) -> dict:
    exercises = exercise_repo.get_all_for_user(user_sub)
    workouts, sets = workout_repo.get_all_workout_data_for_user(user_sub)

    # Group sets by workout_id
    sets_by_workout: dict[str, list] = {}
    for s in sets:
        sets_by_workout.setdefault(s.workout_id, []).append(s)

    export_exercises = [
        ExportExercise(
            id=e.exercise_id,
            name=e.name,
            muscles=e.muscles,
            equipment=e.equipment,
            category=e.category,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in exercises
    ]

    export_workouts = []
    for w in workouts:
        workout_sets = sorted(
            sets_by_workout.get(w.workout_id, []), key=lambda s: s.set_number
        )
        export_sets = [
            ExportSet(
                set_number=s.set_number,
                exercise_id=s.exercise_id,
                reps=s.reps,
                weight_kg=float(s.weight_kg) if s.weight_kg is not None else None,
                rpe=s.rpe,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in workout_sets
        ]
        export_workouts.append(
            ExportWorkout(
                id=w.workout_id,
                date=w.date,
                name=w.name,
                tags=w.tags,
                notes=w.notes,
                created_at=w.created_at,
                updated_at=w.updated_at,
                sets=export_sets,
            )
        )

    payload = ExportPayload(
        schema_version=1,
        exported_at=now(),
        user=ExportUser(
            display_name=profile.display_name,
            email=profile.email,
            timezone=profile.timezone,
            preferences=profile.preferences.model_dump(),
        ),
        exercises=export_exercises,
        workouts=export_workouts,
    )

    return json.loads(json.dumps(payload.model_dump(), cls=_ExportEncoder))


def serialise_export(payload_dict: dict) -> str:
    return json.dumps(payload_dict, indent=2, cls=_ExportEncoder)


def parse_import_file(content: bytes) -> ExportPayload:
    """
    Validate raw file bytes and return a parsed ExportPayload.

    Raises ValueError with a human-readable message on any failure.
    """
    if len(content) > _MAX_IMPORT_BYTES:
        raise ValueError("File exceeds the 5 MB size limit.")

    try:
        raw = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"File is not valid JSON: {e.msg}") from e

    if not isinstance(raw, dict):
        raise ValueError("File must contain a JSON object at the top level.")

    schema_version = raw.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(
            f"Unsupported export version: {schema_version!r}. "
            "Please re-export from a current version of ElbieFit."
        )

    try:
        return ExportPayload.model_validate(raw)
    except Exception as e:
        raise ValueError(f"Import file has invalid structure: {e}") from e
