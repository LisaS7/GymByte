from datetime import date as DateType
from datetime import datetime

from pydantic import BaseModel


class ExportSet(BaseModel):
    set_number: int
    exercise_id: str
    reps: int
    weight_kg: float | None = None
    rpe: int | None = None
    created_at: datetime
    updated_at: datetime


class ExportWorkout(BaseModel):
    id: str
    date: DateType
    name: str
    tags: list[str] | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    sets: list[ExportSet] = []


class ExportExercise(BaseModel):
    id: str
    name: str
    muscles: list[str]
    equipment: str
    category: str | None = None
    created_at: datetime
    updated_at: datetime


class ExportUser(BaseModel):
    display_name: str
    email: str
    timezone: str
    preferences: dict


class ExportPayload(BaseModel):
    schema_version: int
    exported_at: datetime
    user: ExportUser
    exercises: list[ExportExercise] = []
    workouts: list[ExportWorkout] = []


class ImportSummary(BaseModel):
    exercises_created: int = 0
    exercises_matched: int = 0
    workouts_created: int = 0
    workouts_skipped: int = 0
    sets_created: int = 0
    warnings: list[str] = []
