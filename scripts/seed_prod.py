# One-time script to seed Lisa's prod profile and exercises.
# Run with:  ENV=prod uv run python -m scripts.seed_prod

import uuid

from app.models.exercise import Exercise
from app.utils.dates import now
from app.utils.db import get_table
from app.utils.seed_data import build_profile

PROD_USER_SUB = "4612f254-20b1-708a-adc2-4f0d02009610"
PK = f"USER#{PROD_USER_SUB}"


def main():
    table = get_table()
    ts = now()

    # ── Profile ──────────────────────────────────────────────────────────────
    profile = build_profile(PK, display_name="Lisa", email="lisa@lisa.com")
    table.put_item(Item=profile.to_ddb_item())
    print(f"Created profile for {profile.display_name} ({profile.email})")

    # ── Exercises ─────────────────────────────────────────────────────────────
    exercises = [
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Overhead Press",
            muscles=["shoulders", "triceps"],
            equipment="dumbbells",
            category="push",
            created_at=ts,
            updated_at=ts,
        ),
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Goblet Squat",
            muscles=["quads", "glutes", "hamstrings", "core"],
            equipment="kettlebell",
            category="legs",
            created_at=ts,
            updated_at=ts,
        ),
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Lateral Raise",
            muscles=["shoulders"],
            equipment="dumbbells",
            category="push",
            created_at=ts,
            updated_at=ts,
        ),
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Bicep Curl",
            muscles=["biceps"],
            equipment="dumbbells",
            category="pull",
            created_at=ts,
            updated_at=ts,
        ),
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Deadlift",
            muscles=["glutes", "hamstrings", "lower_back"],
            equipment="dumbbells",
            category="legs",
            created_at=ts,
            updated_at=ts,
        ),
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Lunge",
            muscles=["quads", "glutes", "hamstrings"],
            equipment="dumbbells",
            category="legs",
            created_at=ts,
            updated_at=ts,
        ),
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Bent Over Row",
            muscles=["lats", "upper_back", "biceps"],
            equipment="dumbbells",
            category="pull",
            created_at=ts,
            updated_at=ts,
        ),
        Exercise(
            PK=PK,
            SK=f"EXERCISE#{uuid.uuid4()}",
            type="exercise",
            name="Chest Press",
            muscles=["chest", "triceps", "shoulders"],
            equipment="dumbbells",
            category="push",
            created_at=ts,
            updated_at=ts,
        ),
    ]

    for ex in exercises:
        table.put_item(Item=ex.to_ddb_item())
        print(f"  Created exercise: {ex.name}")

    print(f"\nDone — {len(exercises)} exercises added.")


if __name__ == "__main__":
    main()
