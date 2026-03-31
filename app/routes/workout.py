from datetime import date as DateType
from typing import Annotated, Literal, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.models.workout import (
    WorkoutCreate,
    WorkoutSet,
    WorkoutSetCreate,
    WorkoutSetUpdate,
    WorkoutUpdate,
)
from app.repositories.errors import (
    ExerciseRepoError,
    WorkoutNotFoundError,
    WorkoutRepoError,
)
from app.repositories.exercise import DynamoExerciseRepository
from app.repositories.profile import DynamoProfileRepository
from app.repositories.workout import DynamoWorkoutRepository
from app.templates.templates import render_template
from app.utils import auth, dates
from app.utils.log import logger
from app.utils.units import kg_to_lb, lb_to_kg

router = APIRouter(prefix="/workout", tags=["workout"])


def get_workout_repo() -> DynamoWorkoutRepository:  # pragma: no cover
    """Fetch the workout repo"""
    return DynamoWorkoutRepository()


def get_exercise_repo() -> DynamoExerciseRepository:  # pragma: no cover
    """Fetch the exercise repo"""
    return DynamoExerciseRepository()


def get_profile_repo() -> DynamoProfileRepository:  # pragma: no cover
    """Fetch the profile repo"""
    return DynamoProfileRepository()


def get_weight_unit_for_user(
    user_sub: str,
    profile_repo: DynamoProfileRepository,
) -> Literal["kg", "lb"]:
    try:
        profile = profile_repo.get_for_user(user_sub)
    except Exception:
        logger.exception(f"Error fetching profile for user_sub={user_sub}")
        return "kg"
    return profile.weight_unit if profile else "kg"


def get_sorted_sets_and_defaults(
    sets: Sequence[WorkoutSet],
) -> tuple[list[WorkoutSet], dict]:
    """
    Return sets sorted by created_at, and the defaults for the "add set" form.
    """

    sorted_sets = sorted(sets, key=lambda s: s.created_at)

    defaults = {"exercise": "", "reps": "", "weight": ""}

    if sorted_sets:
        last = sorted_sets[-1]
        defaults = {
            "exercise": last.exercise_id,
            "reps": last.reps,
            "weight": last.weight_kg,
        }

    return sorted_sets, defaults


# ---------------------- List all ---------------------------


@router.get("/all")
def get_all_workouts(
    request: Request,
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
):
    """Get all workouts for the current authenticated user"""
    user_sub = claims["sub"]

    logger.info(f"Fetching workouts for user {user_sub}")

    try:
        workouts = repo.get_all_for_user(user_sub)
    except WorkoutRepoError:
        logger.exception(f"Error fetching workouts for user {user_sub}")
        raise HTTPException(status_code=500, detail="Error fetching workouts")
    return render_template(
        request,
        "workouts/workouts.html",
        context={"workouts": workouts},
        status_code=200,
    )


# ---------------------- Create ---------------------------


@router.get("/new-form")
def get_new_form(
    request: Request,
    claims=Depends(auth.require_auth),
    profile_repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]
    profile = profile_repo.get_for_user(user_sub)
    tz = profile.timezone if profile else None

    return render_template(
        request,
        "workouts/_new_form.html",
        context={"default_date": dates.today_in_tz(tz)},
    )


@router.get("/{workout_date}/{workout_id}/set/form")
def get_new_set_form(
    request: Request,
    workout_date: DateType,
    workout_id: str,
    exercise_id: str,
    claims=Depends(auth.require_auth),
    profile_repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    logger.debug(
        f"Getting new set form for workout {workout_id} on {workout_date} for exercise {exercise_id}"
    )

    user_sub = claims["sub"]
    unit = get_weight_unit_for_user(user_sub, profile_repo)

    action_url = (
        str(
            request.url_for("add_set", workout_date=workout_date, workout_id=workout_id)
        )
        + f"?exercise_id={exercise_id}"
    )

    context = {
        "workout_date": workout_date,
        "workout_id": workout_id,
        "exercise_id": exercise_id,
        "action_url": action_url,
        "submit_label": "Add Set",
        "set": None,
        "cancel_target": f"#new-set-form-container-{exercise_id}",
        "weight_unit": unit,
    }

    return render_template(
        request,
        "workouts/_set_form.html",
        context=context,
    )


@router.post("/create")
def create_workout(
    request: Request,
    form: Annotated[WorkoutCreate, Depends(WorkoutCreate.as_form)],
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
):
    user_sub = claims["sub"]

    try:
        workout = repo.create_workout(user_sub, data=form)
    except WorkoutRepoError:
        logger.exception("Error creating workout")
        raise HTTPException(status_code=500, detail="Error creating workout")

    return RedirectResponse(
        url=f"/workout/{workout.date.isoformat()}/{workout.workout_id}", status_code=303
    )


@router.post("/{workout_date}/{workout_id}/set/add")
def add_set(
    workout_date: DateType,
    workout_id: str,
    exercise_id: str,
    form: Annotated[WorkoutSetCreate, Depends(WorkoutSetCreate.as_form)],
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
    profile_repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]
    unit = get_weight_unit_for_user(user_sub, profile_repo)

    if unit == "lb" and form.weight_kg is not None:
        form.weight_kg = lb_to_kg(form.weight_kg)

    try:
        repo.add_set(user_sub, workout_date, workout_id, exercise_id, form)
    except WorkoutRepoError:
        logger.exception("Error creating workout set")
        raise HTTPException(status_code=500, detail="Error creating workout set")

    return Response(status_code=204, headers={"HX-Trigger": "workoutSetChanged"})


# ---------------------- Detail ---------------------------


@router.get("/{workout_date}/{workout_id}")
def view_workout(
    request: Request,
    workout_date: DateType,
    workout_id: str,
    claims=Depends(auth.require_auth),
    workout_repo: DynamoWorkoutRepository = Depends(get_workout_repo),
    exercise_repo: DynamoExerciseRepository = Depends(get_exercise_repo),
    profile_repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]

    # ---- Fetch workout and sets -----
    try:
        workout, sets = workout_repo.get_workout_with_sets(
            user_sub, workout_date, workout_id
        )
    except WorkoutNotFoundError:
        logger.warning(
            f"Workout {workout_id} not found for {user_sub}",
        )
        raise HTTPException(status_code=404, detail="Workout not found")
    except WorkoutRepoError:
        logger.exception(
            f"Error fetching workout {workout_id}",
        )
        raise HTTPException(status_code=500, detail="Error fetching workout")

    logger.debug(
        f"Fetched workout {workout_id} and {len(sets)} sets. Set numbers: {[s.set_number for s in sets]}",
    )

    sets, defaults = get_sorted_sets_and_defaults(sets)

    # ---- Sort out units -----
    unit = get_weight_unit_for_user(user_sub, profile_repo)

    if unit == "lb":
        for s in sets:
            if s.weight_kg is not None:
                s.weight_kg = kg_to_lb(s.weight_kg)

        if defaults.get("weight") is not None and defaults.get("weight") != "":
            defaults["weight"] = kg_to_lb(defaults["weight"])

    # ---- Fetch exercise details -----
    exercise_map = {}

    try:
        for s in sets:
            exercise_id = s.exercise_id
            if exercise_id not in exercise_map:
                exercise = exercise_repo.get_exercise_by_id(user_sub, exercise_id)
                if exercise:
                    exercise_map[exercise_id] = exercise
    except ExerciseRepoError:
        logger.exception(
            f"Error fetching exercise details for user {user_sub} and {workout_id}",
        )
        raise HTTPException(status_code=500, detail="Error fetching exercise details")

    # ---- Finish ----
    return render_template(
        request,
        "workouts/workout_detail.html",
        context={
            "workout": workout,
            "sets": sets,
            "defaults": defaults,
            "exercises": exercise_map,
            "weight_unit": unit,
        },
    )


# ---------------------- Edit ---------------------------


# ---- Return the workout meta form -----
@router.get("/{workout_date}/{workout_id}/edit-meta")
def edit_workout_meta(
    request: Request,
    workout_date: DateType,
    workout_id: str,
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
):
    user_sub = claims["sub"]

    try:
        workout, sets = repo.get_workout_with_sets(user_sub, workout_date, workout_id)
    except WorkoutNotFoundError:
        logger.warning(
            f"Workout {workout_id} on {workout_date.isoformat()} not found for edit",
        )
        raise HTTPException(status_code=404, detail="Workout not found")
    except WorkoutRepoError:
        logger.exception(
            f"Error fetching workout {workout_id} for edit",
        )
        raise HTTPException(status_code=500, detail="Error fetching workout")

    logger.debug(f"Loading edit meta form for workout {workout.workout_id}")

    return render_template(
        request, "workouts/_edit_meta_form.html", context={"workout": workout}
    )


# ---- Make the update -----
@router.post("/{workout_date}/{workout_id}/meta")
def update_workout_meta(
    request: Request,
    workout_date: DateType,
    workout_id: str,
    form: WorkoutUpdate = Depends(WorkoutUpdate.as_form),
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
):
    user_sub = claims["sub"]

    logger.info(
        f"Updating workout meta\nUser: {user_sub}\nDate: {workout_date.isoformat()}\nID: {workout_id}",
    )

    try:
        workout, sets = repo.get_workout_with_sets(user_sub, workout_date, workout_id)
    except WorkoutNotFoundError:
        logger.warning(
            f"Workout {workout_id} not found for update",
        )
        raise HTTPException(status_code=404, detail="Workout not found")
    except WorkoutRepoError:
        logger.exception(
            f"Error fetching workout {workout_id} for update",
        )
        raise HTTPException(status_code=500, detail="Error fetching workout")

    old_date = workout.date
    new_date = form.date

    workout.name = form.name
    workout.notes = form.notes or None
    workout.tags = form.tags
    workout.updated_at = dates.now()

    # if date hasn't changed then update existing item
    if new_date == old_date:
        try:
            repo.edit_workout(workout)
        except WorkoutRepoError:
            logger.exception(
                f"Error updating workout{workout_id}",
            )
            raise HTTPException(status_code=500, detail="Error updating workout")

        sets, defaults = get_sorted_sets_and_defaults(sets)

        logger.debug(f"Updated metadata for workout {workout_id}. No date change.")

        return render_template(
            request,
            "workouts/workout_detail.html",
            context={"workout": workout, "sets": sets, "defaults": defaults},
        )

    # if date has changed then create new and delete old
    else:
        try:
            logger.debug(
                f"Moving workout date from {old_date} to {new_date} for {workout.workout_id}"
            )
            workout = repo.move_workout_date(user_sub, workout, new_date, sets)
        except WorkoutRepoError:
            logger.exception(
                f"Error updating workout {workout_id} with date change {old_date} to {new_date}",
            )
            raise HTTPException(status_code=500, detail="Error updating workout")

        new_url = request.url_for(
            "view_workout",
            workout_date=workout.date,
            workout_id=workout.workout_id,
        )

        logger.info(
            f"Workout date changed for {workout_id}, issuing HX-Redirect to {new_url}",
        )

        return Response(status_code=204, headers={"HX-Redirect": str(new_url)})


# ---- Edit sets -----


@router.get("/{workout_date}/{workout_id}/set/{set_number}/edit")
def get_edit_set_form(
    request: Request,
    workout_date: DateType,
    workout_id: str,
    set_number: int,
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
    profile_repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]

    try:
        set_ = repo.get_set(user_sub, workout_date, workout_id, set_number)
    except WorkoutRepoError:
        logger.exception(
            f"Error fetching set {set_number} for edit in workout {workout_id}",
        )
        raise HTTPException(status_code=500, detail="Error fetching set")

    unit = get_weight_unit_for_user(user_sub, profile_repo)

    if unit == "lb" and set_.weight_kg is not None:
        set_.weight_kg = kg_to_lb(set_.weight_kg)

    action_url = request.url_for(
        "edit_set",
        workout_date=workout_date,
        workout_id=workout_id,
        set_number=set_number,
    )

    cancel_target = f"#edit-set-form-container-{set_.exercise_id}-{set_number}"

    return render_template(
        request,
        "workouts/_set_form.html",
        context={
            "workout_date": workout_date,
            "workout_id": workout_id,
            "set_number": set_number,
            "set": set_,
            "exercise_id": None,  # we don't change exercise on edit
            "action_url": action_url,
            "submit_label": "Save Set",
            "cancel_target": cancel_target,
            "weight_unit": unit,
        },
    )


@router.post("/{workout_date}/{workout_id}/set/{set_number}")
def edit_set(
    workout_date: DateType,
    workout_id: str,
    set_number: int,
    form: Annotated[WorkoutSetUpdate, Depends(WorkoutSetUpdate.as_form)],
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
    profile_repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]

    unit = get_weight_unit_for_user(user_sub, profile_repo)

    if unit == "lb" and form.weight_kg is not None:
        form.weight_kg = lb_to_kg(form.weight_kg)

    try:
        repo.edit_set(user_sub, workout_date, workout_id, set_number, form)
    except WorkoutNotFoundError:
        raise HTTPException(status_code=404, detail="Set not found")
    except WorkoutRepoError:
        logger.exception(
            f"Error updating set {set_number} for {workout_id} on {workout_date.isoformat()}",
        )
        raise HTTPException(status_code=500, detail="Error updating set")

    return Response(status_code=204, headers={"HX-Trigger": "workoutSetChanged"})


# ---------------------- Delete ---------------------------


@router.delete("/{workout_date}/{workout_id}")
def delete_workout(
    workout_date: DateType,
    workout_id: str,
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
):
    user_sub = claims["sub"]

    try:
        logger.debug(f"Deleting workout {workout_id}")
        repo.delete_workout_and_sets(user_sub, workout_date, workout_id)
    except WorkoutRepoError:
        logger.exception(
            f"Error deleting workout {workout_id}",
        )
        raise HTTPException(status_code=500, detail="Error deleting workout")

    return Response(status_code=204, headers={"HX-Redirect": "/workout/all"})


@router.delete("/{workout_date}/{workout_id}/set/{set_number}")
def delete_set(
    request: Request,
    workout_date: DateType,
    workout_id: str,
    set_number: int,
    claims=Depends(auth.require_auth),
    repo: DynamoWorkoutRepository = Depends(get_workout_repo),
):

    user_sub = claims["sub"]

    try:
        logger.debug(f"Deleting set {set_number} for workout {workout_id}")
        repo.delete_set(user_sub, workout_date, workout_id, set_number)
    except WorkoutRepoError:
        logger.exception(
            f"Error deleting set {set_number} from workout {workout_id}",
        )
        raise HTTPException(status_code=500, detail="Error deleting set")

    # Fire an event which htmx picks up to reload the page
    return Response(status_code=204, headers={"HX-Trigger": "workoutSetChanged"})
