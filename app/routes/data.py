from __future__ import annotations

import secrets
import uuid
from datetime import date as DateType
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from app.models.export import ImportSummary
from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutSet
from app.repositories.exercise import DynamoExerciseRepository
from app.repositories.errors import RepoError
from app.repositories.profile import DynamoProfileRepository
from app.repositories.workout import DynamoWorkoutRepository
from app.utils import auth, db
from app.utils.db import RateLimitDdbError, rate_limit_hit
from app.utils.export import build_export_payload, parse_import_file, serialise_export
from app.utils.log import logger

router = APIRouter(prefix="/profile/data", tags=["data"])

_EXPORT_RATE_LIMIT = 5  # per minute window — prevents hammering the export endpoint


def get_workout_repo() -> DynamoWorkoutRepository:  # pragma: no cover
    return DynamoWorkoutRepository()


def get_exercise_repo() -> DynamoExerciseRepository:  # pragma: no cover
    return DynamoExerciseRepository()


def get_profile_repo() -> DynamoProfileRepository:  # pragma: no cover
    return DynamoProfileRepository()


# ─────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────


@router.get("/export")
def export_data(
    request: Request,
    claims=Depends(auth.require_auth),
    workout_repo: DynamoWorkoutRepository = Depends(get_workout_repo),
    exercise_repo: DynamoExerciseRepository = Depends(get_exercise_repo),
    profile_repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]
    logger.info(f"Data export requested user_sub={user_sub}")

    # Per-user export rate limit
    try:
        allowed, retry_after = rate_limit_hit(
            client_id=f"export#{user_sub}",
            limit=_EXPORT_RATE_LIMIT,
        )
    except RateLimitDdbError:
        allowed = True  # fail open

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Export rate limit exceeded. Please try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    profile = profile_repo.get_for_user(user_sub)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    payload_dict = build_export_payload(user_sub, profile, workout_repo, exercise_repo)
    json_str = serialise_export(payload_dict)

    today = DateType.today().isoformat()
    filename = f"elbiefit-export-{today}.json"

    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────────────────────


@router.post("/import")
async def import_data(
    request: Request,
    claims=Depends(auth.require_auth),
    workout_repo: DynamoWorkoutRepository = Depends(get_workout_repo),
    exercise_repo: DynamoExerciseRepository = Depends(get_exercise_repo),
):
    user_sub = claims["sub"]
    logger.info(f"Data import requested user_sub={user_sub}")

    form = await request.form()

    # CSRF is not checked by middleware for multipart requests (reading the
    # body there would consume the stream). Verify the token here instead.
    cookie_token = request.cookies.get("csrf_token", "")
    form_token = str(form.get("csrf_token", ""))
    if not cookie_token or not secrets.compare_digest(cookie_token, form_token):
        logger.warning(f"CSRF validation failed on import user_sub={user_sub}")
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")

    file: UploadFile | None = form.get("file")  # type: ignore[assignment]

    if not file or not file.filename:
        return _import_redirect(error="No file provided.")

    content = await file.read()

    try:
        payload = parse_import_file(content)
    except ValueError as e:
        return _import_redirect(error=str(e))

    summary = ImportSummary()

    # ── Fetch existing data for deduplication ──
    try:
        existing_exercises = exercise_repo.get_all_for_user(user_sub)
        existing_workouts = workout_repo.get_all_for_user(user_sub)
    except RepoError as e:
        logger.exception(f"Failed to fetch existing data for import user_sub={user_sub} err={e}")
        return _import_redirect(error="Could not read existing data. Please try again.")

    existing_workout_ids = {w.workout_id for w in existing_workouts}

    # Build lookup: (name.lower(), equipment.lower()) -> [exercise_id, ...]
    existing_by_name_equip: dict[tuple, list[str]] = {}
    for e in existing_exercises:
        key = (e.name.lower(), e.equipment.lower())
        existing_by_name_equip.setdefault(key, []).append(e.exercise_id)

    # ── Process exercises ──
    id_remap: dict[str, str] = {}  # imported_id -> resolved_id in this account
    items_to_write: list[dict] = []

    for ex in payload.exercises:
        key = (ex.name.lower(), ex.equipment.lower())
        matches = existing_by_name_equip.get(key, [])

        if len(matches) == 1:
            id_remap[ex.id] = matches[0]
            summary.exercises_matched += 1
        else:
            new_id = str(uuid.uuid4())
            id_remap[ex.id] = new_id
            if len(matches) > 1:
                summary.warnings.append(
                    f"Exercise '{ex.name}' ({ex.equipment}) matched multiple existing entries — created fresh"
                )
            try:
                exercise = Exercise(
                    PK=db.build_user_pk(user_sub),
                    SK=db.build_exercise_sk(new_id),
                    type="exercise",
                    name=ex.name,
                    muscles=ex.muscles,
                    equipment=ex.equipment,
                    category=ex.category,
                    created_at=ex.created_at,
                    updated_at=ex.updated_at,
                )
                items_to_write.append(exercise.to_ddb_item())
                summary.exercises_created += 1
            except Exception as exc:
                summary.warnings.append(
                    f"Exercise '{ex.name}' could not be imported ({exc}) — skipped"
                )
                del id_remap[ex.id]  # no valid mapping

    # ── Process workouts and sets ──
    for w in payload.workouts:
        if w.id in existing_workout_ids:
            summary.workouts_skipped += 1
            continue

        pk = db.build_user_pk(user_sub)
        sk = db.build_workout_sk(w.date, w.id)

        try:
            workout = Workout(
                PK=pk,
                SK=sk,
                type="workout",
                date=w.date,
                name=w.name,
                tags=w.tags,
                notes=w.notes,
                created_at=w.created_at,
                updated_at=w.updated_at,
            )
        except Exception as exc:
            summary.warnings.append(
                f"Workout '{w.name}' ({w.date}) could not be imported ({exc}) — skipped"
            )
            continue

        items_to_write.append(workout.to_ddb_item())
        summary.workouts_created += 1

        for s in w.sets:
            resolved_exercise_id = id_remap.get(s.exercise_id)
            if resolved_exercise_id is None:
                summary.warnings.append(
                    f"Set #{s.set_number} in workout '{w.name}' ({w.date}) references "
                    f"unknown exercise — skipped"
                )
                continue

            set_sk = db.build_set_sk(w.date, w.id, s.set_number)
            weight = Decimal(str(s.weight_kg)) if s.weight_kg is not None else None

            try:
                workout_set = WorkoutSet(
                    PK=pk,
                    SK=set_sk,
                    type="set",
                    exercise_id=resolved_exercise_id,
                    set_number=s.set_number,
                    reps=s.reps,
                    weight_kg=weight,
                    rpe=s.rpe,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
            except Exception as exc:
                summary.warnings.append(
                    f"Set #{s.set_number} in workout '{w.name}' ({w.date}) is invalid ({exc}) — skipped"
                )
                continue

            items_to_write.append(workout_set.to_ddb_item())
            summary.sets_created += 1

    # ── Batch write ──
    if items_to_write:
        try:
            table = db.get_table()
            with table.batch_writer() as batch:
                for item in items_to_write:
                    batch.put_item(Item=item)
        except Exception as e:
            logger.exception(f"Batch write failed during import user_sub={user_sub} err={e}")
            return _import_redirect(error="Import failed while writing to database. Some items may have been saved.")

    logger.info(
        f"Import complete user_sub={user_sub} "
        f"exercises_created={summary.exercises_created} exercises_matched={summary.exercises_matched} "
        f"workouts_created={summary.workouts_created} workouts_skipped={summary.workouts_skipped} "
        f"sets_created={summary.sets_created} warnings={len(summary.warnings)}"
    )

    return _import_redirect(summary=summary)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _import_redirect(
    summary: ImportSummary | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        from urllib.parse import quote

        return RedirectResponse(
            f"/profile/?import_error={quote(error)}",
            status_code=303,
        )

    assert summary is not None
    from urllib.parse import urlencode

    params: dict[str, str | int] = {
        "import_exercises": summary.exercises_created,
        "import_matched": summary.exercises_matched,
        "import_workouts": summary.workouts_created,
        "import_skipped": summary.workouts_skipped,
        "import_sets": summary.sets_created,
        "import_warnings": len(summary.warnings),
    }
    return RedirectResponse(f"/profile/?{urlencode(params)}", status_code=303)
