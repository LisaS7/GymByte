from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from test_data import USER_EMAIL, USER_PK

from app.models.profile import AccountUpdateForm, UserProfile
from app.routes.profile import _errors_dict


@pytest.fixture(autouse=True)
def clear_dependency_overrides_after_each_test(client):
    # tests run here
    yield
    # cleanup after
    client.app.dependency_overrides.clear()


# --------------------- Helpers --------------------


def test_errors_dict_maps_field_errors_to_field_name():
    try:
        AccountUpdateForm.model_validate(
            {"display_name": "Lisa", "timezone": "Narnia/Aslan"}
        )
    except ValidationError as e:
        errors = _errors_dict(e)

    assert "timezone" in errors
    assert "Invalid timezone: Narnia/Aslan" in errors["timezone"]


# --------------------- Get --------------------


def test_get_user_profile_success(authenticated_client, fake_profile_repo):
    profile = UserProfile(
        PK=USER_PK,
        SK="PROFILE",
        display_name="Lisa Test",
        email=USER_EMAIL,
        timezone="Europe/London",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
        # preferences omitted -> defaults are fine
    )

    fake_profile_repo(profile=profile)

    response = authenticated_client.get("/profile/")

    assert response.status_code == 200
    assert USER_EMAIL in response.text
    assert "Lisa Test" in response.text
    assert "Europe/London" in response.text


def test_get_user_profile_not_found_shows_message(
    authenticated_client, fake_profile_repo
):
    fake_profile_repo(profile=None)

    response = authenticated_client.get("/profile/")

    assert response.status_code == 404
    assert "Profile not found" in response.text


def test_profile_db_error_returns_500(authenticated_client, fake_profile_repo):
    fake_profile_repo(profile=None, raise_on_get=True)

    response = authenticated_client.get("/profile/")

    assert response.status_code == 500
    text = response.text
    assert "Error 500" in text or "Something went wrong" in text
    assert "ElbieFit" in text


# --------------------- Update --------------------


def _profile(display_name="Lisa Test", tz="Europe/London") -> UserProfile:
    return UserProfile(
        PK=USER_PK,
        SK="PROFILE",
        display_name=display_name,
        email=USER_EMAIL,
        timezone=tz,
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
    )


# ──────────────── /profile/account ────────────────


def test_post_account_success_returns_card_with_saved(
    authenticated_client, fake_profile_repo
):
    original = _profile()
    updated = _profile(display_name="New Name")

    repo = fake_profile_repo(profile=original, updated_profile=updated)

    resp = authenticated_client.post(
        "/profile/account",
        data={"display_name": "New Name", "timezone": "Europe/London"},
    )

    assert resp.status_code == 200
    assert "Saved" in resp.text
    assert "New Name" in resp.text
    assert "Europe/London" in resp.text

    assert repo.last_update_account == {
        "user_sub": repo.last_update_account["user_sub"],  # don't hardcode sub
        "display_name": "New Name",
        "timezone": "Europe/London",
    }


def test_post_account_validation_error_returns_400_and_shows_error(
    authenticated_client, fake_profile_repo
):
    fake_profile_repo(profile=_profile())

    resp = authenticated_client.post(
        "/profile/account",
        data={"display_name": "New Name", "timezone": "Narnia/Aslan"},
    )

    assert resp.status_code == 400
    assert "Invalid timezone" in resp.text
    assert "Narnia/Aslan" in resp.text


def test_post_account_repo_error_returns_500(authenticated_client, fake_profile_repo):
    fake_profile_repo(profile=_profile(), raise_on_update=True)

    resp = authenticated_client.post(
        "/profile/account",
        data={"display_name": "New Name", "timezone": "Europe/London"},
    )

    assert resp.status_code == 500


# ──────────────── /profile/preferences ────────────────


def test_post_preferences_success_returns_card_with_saved(
    authenticated_client, fake_profile_repo
):
    original = _profile()
    updated = original.model_copy(
        update={
            "preferences": original.preferences.model_copy(
                update={"theme": "volt", "units": "imperial"}
            )
        }
    )

    repo = fake_profile_repo(profile=original, updated_profile=updated)

    resp = authenticated_client.post(
        "/profile/preferences",
        data={"theme": "volt", "units": "imperial"},
    )

    assert resp.status_code == 200
    assert "Saved" in resp.text

    assert repo.last_update_prefs == {
        "user_sub": repo.last_update_prefs["user_sub"],
        "theme": "volt",
        "units": "imperial",
    }


def test_post_preferences_success_saves_theme_and_units(
    authenticated_client, fake_profile_repo
):
    original = _profile()
    updated = original.model_copy(
        update={
            "preferences": original.preferences.model_copy(
                update={"theme": "volt", "units": "metric"}
            )
        }
    )

    repo = fake_profile_repo(profile=original, updated_profile=updated)

    resp = authenticated_client.post(
        "/profile/preferences",
        data={"theme": "volt", "units": "metric"},
    )

    assert resp.status_code == 200


def test_post_preferences_validation_error_returns_400(
    authenticated_client, fake_profile_repo
):
    fake_profile_repo(profile=_profile())

    resp = authenticated_client.post(
        "/profile/preferences",
        data={"theme": "prehistoric", "units": "goblin"},
    )

    assert resp.status_code == 400
    assert "units" in resp.text.lower()
    assert "metric" in resp.text.lower() or "imperial" in resp.text.lower()


def test_post_preferences_repo_error_returns_500(
    authenticated_client, fake_profile_repo
):
    # Arrange: profile exists, but repo will fail on update
    fake_profile_repo(
        profile=_profile(),
        raise_on_update=True,
    )

    # Act
    resp = authenticated_client.post(
        "/profile/preferences",
        data={
            "theme": "volt",
            "units": "metric",
        },
    )

    # Assert
    assert resp.status_code == 500
    assert "Internal error updating preferences" in resp.text
