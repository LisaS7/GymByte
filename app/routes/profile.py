from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.models.profile import AccountUpdateForm, PreferencesUpdateForm, UserProfile
from app.repositories.errors import ProfileRepoError
from app.repositories.profile import DynamoProfileRepository
from app.settings import settings
from app.templates.templates import render_template
from app.utils import auth
from app.utils.log import logger
from app.utils.theme import set_theme_cookie

router = APIRouter(prefix="/profile", tags=["profile"])

# ------------------------- Helpers ------------------------


_TZ_OPTIONS: list[str] = sorted(available_timezones())


def _errors_dict(e: ValidationError) -> dict[str, str]:
    return {str(err["loc"][0]): err["msg"] for err in e.errors() if err["loc"]}


def get_profile_repo() -> DynamoProfileRepository:  # pragma: no cover
    return DynamoProfileRepository()


def _get_profile_or_404(repo: DynamoProfileRepository, user_sub: str) -> UserProfile:
    try:
        profile = repo.get_for_user(user_sub)
    except ProfileRepoError as e:
        logger.exception(f"Error fetching profile user_sub={user_sub} err={e}")
        raise HTTPException(status_code=500, detail="Internal error reading profile")

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return profile


# ------------------------- GET ------------------------


@router.get("/")
def profile(
    request: Request,
    claims=Depends(auth.require_auth),
    repo: DynamoProfileRepository = Depends(get_profile_repo),
    # Import flash params (set by redirect after a successful/failed import)
    import_error: str | None = None,
    import_exercises: int | None = None,
    import_matched: int | None = None,
    import_workouts: int | None = None,
    import_skipped: int | None = None,
    import_sets: int | None = None,
    import_warnings: int | None = None,
):
    """Get the profile of the current authenticated user."""
    user_sub = claims["sub"]
    logger.info(f"Fetching profile for user_sub={user_sub}")

    try:
        profile = _get_profile_or_404(repo, user_sub)
    except HTTPException as e:
        if e.status_code == 404:
            return render_template(
                request,
                "profile/profile.html",
                context={"request": request, "profile": None, "user_sub": user_sub},
                status_code=404,
            )
        raise

    logger.debug(f"Profile retrieved for user_sub={user_sub}")

    import_success = import_workouts is not None

    return render_template(
        request,
        "profile/profile.html",
        context={
            "request": request,
            "themes": settings.THEMES,
            "profile": profile,
            "user_sub": user_sub,
            "tz_options": _TZ_OPTIONS,
            # placeholders for card swaps / validation later
            "account_form": None,
            "account_errors": None,
            "account_success": False,
            "prefs_form": None,
            "prefs_errors": None,
            "prefs_success": False,
            # data card
            "csrf_token": request.cookies.get("csrf_token", ""),
            "import_error": import_error,
            "import_success": import_success,
            "import_exercises": import_exercises,
            "import_matched": import_matched,
            "import_workouts": import_workouts,
            "import_skipped": import_skipped,
            "import_sets": import_sets,
            "import_warnings": import_warnings,
        },
        status_code=200,
    )


# ------------------------- POST ------------------------


@router.post("/account")
async def update_account(
    request: Request,
    claims=Depends(auth.require_auth),
    repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]
    logger.info(f"Updating account user_sub={user_sub}")
    profile = _get_profile_or_404(repo, user_sub)

    form = await request.form()
    data = {
        "display_name": form.get("display_name") or "",
        "timezone": form.get("timezone") or "",
    }

    try:
        account_form = AccountUpdateForm.model_validate(data)
    except ValidationError as e:
        errors = _errors_dict(e)

        return render_template(
            request,
            "profile/_account_card.html",
            context={
                "request": request,
                "profile": profile,
                "tz_options": _TZ_OPTIONS,
                "account_form": data,
                "account_errors": errors,
                "account_success": False,
            },
            status_code=400,
        )

    try:
        profile = repo.update_account(
            user_sub,
            display_name=account_form.display_name,
            timezone=account_form.timezone,
        )
    except ProfileRepoError as e:
        logger.exception(f"Error updating account user_sub={user_sub} err={e}")
        raise HTTPException(status_code=500, detail="Internal error updating account")

    return render_template(
        request,
        "profile/_account_card.html",
        context={
            "request": request,
            "profile": profile,
            "tz_options": _TZ_OPTIONS,
            "account_form": None,
            "account_errors": None,
            "account_success": True,
        },
        status_code=200,
    )


@router.post("/preferences")
async def update_preferences(
    request: Request,
    claims=Depends(auth.require_auth),
    repo: DynamoProfileRepository = Depends(get_profile_repo),
):
    user_sub = claims["sub"]
    logger.info(f"Updating preferences user_sub={user_sub}")
    profile = _get_profile_or_404(repo, user_sub)

    form = await request.form()
    data = {
        "show_tips": form.get("show_tips") == "true",
        "theme": form.get("theme") or "",
        "units": form.get("units") or "",
    }

    try:
        validated = PreferencesUpdateForm.model_validate(data)
    except ValidationError as e:
        errors = _errors_dict(e)
        return render_template(
            request,
            "profile/_preferences_card.html",
            context={
                "request": request,
                "themes": settings.THEMES,
                "profile": profile,
                "prefs_form": data,
                "prefs_errors": errors,
                "prefs_success": False,
            },
            status_code=400,
        )

    try:
        profile = repo.update_preferences(
            user_sub,
            show_tips=validated.show_tips,
            theme=validated.theme,
            units=validated.units,
        )
    except ProfileRepoError as e:
        logger.exception(f"Error updating preferences user_sub={user_sub} err={e}")
        raise HTTPException(
            status_code=500, detail="Internal error updating preferences"
        )

    headers = {"HX-Refresh": "true"}

    response = render_template(
        request,
        "profile/_preferences_card.html",
        context={
            "request": request,
            "themes": settings.THEMES,
            "profile": profile,
            "prefs_form": None,
            "prefs_errors": None,
            "prefs_success": True,
        },
        status_code=200,
        headers=headers,
    )

    # Set cookie so ThemeMiddleware picks it up next request
    set_theme_cookie(response, validated.theme)

    return response
