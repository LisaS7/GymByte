from datetime import datetime
from zoneinfo import available_timezones

import pytest
from pydantic import ValidationError
from test_data import USER_EMAIL, USER_PK

from app.models.profile import AccountUpdateForm, Preferences

# ---------- Preferences ----------


def test_preferences_defaults():
    prefs = Preferences()

    assert prefs.theme == "volt"
    assert prefs.units == "metric"


def test_preferences_invalid_units_raises():
    with pytest.raises(ValidationError):
        Preferences(units="goblin")  # type: ignore


# ---------- UserProfile ----------


def test_user_profile_valid_instance_and_default_preferences(example_profile):
    assert example_profile.PK == USER_PK
    assert example_profile.SK == "PROFILE"
    assert example_profile.display_name == "Lisa Test"
    assert example_profile.email == USER_EMAIL

    # created/updated are parsed as datetime
    assert isinstance(example_profile.created_at, datetime)
    assert isinstance(example_profile.updated_at, datetime)

    # preferences should be a Preferences instance with defaults
    assert isinstance(example_profile.preferences, Preferences)
    assert example_profile.preferences.units == "metric"


def test_user_profile_requires_sk_profile_literal(profile):
    with pytest.raises(ValidationError):
        profile(SK="NOT_PROFILE")


def test_user_profile_validates_email(profile):
    with pytest.raises(ValidationError):
        profile(email="not-an-email")


def test_to_ddb_item_serializes_datetimes_and_nests_preferences(example_profile):
    ddb_item = example_profile.to_ddb_item()

    # top-level keys preserved
    assert ddb_item["PK"] == USER_PK
    assert ddb_item["SK"] == "PROFILE"
    assert ddb_item["display_name"] == "Lisa Test"
    assert ddb_item["email"] == USER_EMAIL
    assert ddb_item["timezone"] == "Europe/London"

    # datetimes should have been converted to strings by dt_to_iso
    assert isinstance(ddb_item["created_at"], str)
    assert isinstance(ddb_item["updated_at"], str)

    # preferences should be a nested dict, not a model instance
    prefs = ddb_item["preferences"]
    assert isinstance(prefs, dict)
    assert prefs["units"] == "metric"


def test_userprofile_accepts_valid_timezone(profile):
    tz = next(iter(available_timezones()))  # any valid tz
    p = profile(timezone=tz)
    assert p.timezone == tz


def test_userprofile_rejects_invalid_timezone(profile):
    with pytest.raises(ValidationError, match="Invalid timezone: Narnia/Aslan"):
        profile(timezone="Narnia/Aslan")


def test_account_update_form_accepts_valid_timezone():
    tz = next(iter(available_timezones()))
    form = AccountUpdateForm(display_name="Lisa Test", timezone=tz)
    assert form.timezone == tz


def test_account_update_form_rejects_invalid_timezone():
    with pytest.raises(ValidationError, match="Invalid timezone: Narnia/Aslan"):
        AccountUpdateForm(display_name="Lisa Test", timezone="Narnia/Aslan")
