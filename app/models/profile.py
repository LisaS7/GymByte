from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.settings import settings
from app.utils.dates import dt_to_iso

DisplayNameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
Units = Literal["metric", "imperial"]
WeightUnit = Literal["kg", "lb"]
ProfileSK = Literal["PROFILE"]


def _check_theme(v: str) -> str:
    if v not in settings.THEMES:
        raise ValueError(f"Invalid theme: {v}")
    return v


def _check_timezone(v: str) -> str:
    if v not in available_timezones():
        raise ValueError(f"Invalid timezone: {v}")
    return v


class Preferences(BaseModel):
    show_tips: bool = True
    theme: str = settings.DEFAULT_THEME
    units: Units = "metric"
    # allows arbitrary extra keys
    model_config = {"extra": "allow"}

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        return _check_theme(v)


class UserProfile(BaseModel):
    PK: str
    SK: ProfileSK

    display_name: DisplayNameStr
    email: EmailStr

    created_at: datetime
    updated_at: datetime
    timezone: str = Field(..., min_length=1)

    preferences: Preferences = Preferences()

    @model_validator(mode="after")
    def validate_timezone(self) -> "UserProfile":
        _check_timezone(self.timezone)
        return self

    @property
    def weight_unit(self) -> Literal["kg", "lb"]:
        return "lb" if self.preferences.units == "imperial" else "kg"

    def to_ddb_item(self) -> dict:
        data = self.model_dump()
        data["created_at"] = dt_to_iso(self.created_at)
        data["updated_at"] = dt_to_iso(self.updated_at)
        return data


class AccountUpdateForm(BaseModel):
    display_name: DisplayNameStr
    timezone: str = Field(..., min_length=1)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        return _check_timezone(v)


class PreferencesUpdateForm(BaseModel):
    show_tips: bool = False
    theme: str
    units: Units

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        return _check_theme(v)
