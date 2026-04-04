import pytest

from app.models.profile import UserProfile
from app.repositories.errors import ProfileRepoError
from app.repositories.profile import DynamoProfileRepository
from tests.test_data import USER_EMAIL, USER_PK, USER_SUB

# ──────────────────────────── GET ────────────────────────────


def test_get_for_user_success(fake_table):
    expected_item = {
        "PK": USER_PK,
        "SK": "PROFILE",
        "display_name": "Lisa Test",
        "email": USER_EMAIL,
        "timezone": "Europe/London",
        "created_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-02T12:00:00Z",
    }

    fake_table.response = {
        "Item": expected_item,
        "ResponseMetadata": {"RequestId": "req-123"},
    }

    repo = DynamoProfileRepository(table=fake_table)

    profile = repo.get_for_user(USER_SUB)

    assert isinstance(profile, UserProfile)
    assert profile.PK == USER_PK
    assert profile.SK == "PROFILE"
    assert profile.display_name == "Lisa Test"
    assert str(profile.email) == USER_EMAIL
    assert profile.timezone == "Europe/London"

    assert fake_table.last_get_kwargs == {
        "Key": {"PK": USER_PK, "SK": "PROFILE"},
        "ConsistentRead": True,
    }


def test_get_for_user_not_found_returns_none(fake_table):
    fake_table.response = {"ResponseMetadata": {"RequestId": "req-123"}}

    repo = DynamoProfileRepository(table=fake_table)

    result = repo.get_for_user(USER_SUB)

    assert result is None


def test_get_for_user_wraps_repo_error(failing_get_table):
    repo = DynamoProfileRepository(table=failing_get_table)

    with pytest.raises(ProfileRepoError):
        repo.get_for_user(USER_SUB)


def test_get_for_user_invalid_item_raises_profile_repo_error(fake_table):
    bad_item = {
        "PK": USER_PK,
        "SK": "PROFILE",
        "display_name": "Lisa Test",
        "email": USER_EMAIL,
        "timezone": "Mars/Phobos",  # invalid -> triggers model validation failure
        "created_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-02T12:00:00Z",
    }

    fake_table.response = {
        "Item": bad_item,
        "ResponseMetadata": {"RequestId": "req-123"},
    }

    repo = DynamoProfileRepository(table=fake_table)

    with pytest.raises(ProfileRepoError) as exc:
        repo.get_for_user(USER_SUB)

    assert "Failed to create profile model from item" in str(exc.value)


# ──────────────────────────── UPDATE ────────────────────────────


def test_update_account_success(fake_table):
    expected_attrs = {
        "PK": USER_PK,
        "SK": "PROFILE",
        "display_name": "New Name",
        "email": USER_EMAIL,
        "timezone": "Europe/London",
        "created_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-03T12:00:00Z",
        "preferences": {"theme": "volt", "units": "metric"},
    }

    fake_table.response = {"Attributes": expected_attrs}

    repo = DynamoProfileRepository(table=fake_table)

    profile = repo.update_account(
        USER_SUB,
        display_name="New Name",
        timezone="Europe/London",
    )

    assert isinstance(profile, UserProfile)
    assert profile.display_name == "New Name"
    assert profile.timezone == "Europe/London"

    # Verify update_item call shape (don't assert exact updated_at value, it's "now()")
    kwargs = fake_table.last_update_kwargs
    assert kwargs["Key"] == {"PK": USER_PK, "SK": "PROFILE"}
    assert (
        kwargs["UpdateExpression"]
        == "SET display_name = :dn, #tz = :tz, updated_at = :ua"
    )
    assert kwargs["ExpressionAttributeNames"] == {"#tz": "timezone"}
    assert kwargs["ExpressionAttributeValues"][":dn"] == "New Name"
    assert kwargs["ExpressionAttributeValues"][":tz"] == "Europe/London"
    assert isinstance(kwargs["ExpressionAttributeValues"][":ua"], str)

    assert (
        kwargs["ConditionExpression"] == "attribute_exists(PK) AND attribute_exists(SK)"
    )
    assert kwargs["ReturnValues"] == "ALL_NEW"


def test_update_account_wraps_repo_error(failing_update_table):
    repo = DynamoProfileRepository(table=failing_update_table)

    with pytest.raises(ProfileRepoError):
        repo.update_account(USER_SUB, display_name="New Name", timezone="Europe/London")


def test_update_account_no_attributes_raises(fake_table):
    fake_table.response = {}  # missing Attributes

    repo = DynamoProfileRepository(table=fake_table)

    with pytest.raises(ProfileRepoError, match="Account update returned no attributes"):
        repo.update_account(USER_SUB, display_name="New Name", timezone="Europe/London")


def test_update_preferences_success(fake_table):
    expected_attrs = {
        "PK": USER_PK,
        "SK": "PROFILE",
        "display_name": "Lisa Test",
        "email": USER_EMAIL,
        "timezone": "Europe/London",
        "created_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-03T12:00:00Z",
        "preferences": {
            "theme": "arctic",
            "units": "imperial",
        },
    }

    fake_table.response = {"Attributes": expected_attrs}

    repo = DynamoProfileRepository(table=fake_table)

    profile = repo.update_preferences(
        USER_SUB,
        theme="arctic",
        units="imperial",
    )

    assert isinstance(profile, UserProfile)
    assert profile.preferences.theme == "arctic"
    assert profile.preferences.units == "imperial"

    kwargs = fake_table.last_update_kwargs
    assert kwargs["Key"] == {"PK": USER_PK, "SK": "PROFILE"}

    assert "preferences.theme" in kwargs["UpdateExpression"]
    assert "preferences.units" in kwargs["UpdateExpression"]
    assert "updated_at" in kwargs["UpdateExpression"]

    eav = kwargs["ExpressionAttributeValues"]
    assert eav[":th"] == "arctic"
    assert eav[":un"] == "imperial"
    assert isinstance(eav[":ua"], str)


def test_update_preferences_wraps_repo_error(failing_update_table):
    repo = DynamoProfileRepository(table=failing_update_table)

    with pytest.raises(ProfileRepoError):
        repo.update_preferences(
            USER_SUB, theme="prehistoric", units="metric"
        )


def test_update_preferences_no_attributes_raises(fake_table):
    fake_table.response = {}

    repo = DynamoProfileRepository(table=fake_table)

    with pytest.raises(
        ProfileRepoError, match="Preferences update returned no attributes"
    ):
        repo.update_preferences(
            USER_SUB, theme="prehistoric", units="metric"
        )
