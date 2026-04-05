# Export all data for a given Cognito user sub to a JSON file.
#
# Run using:
#   uv run python -m scripts.export_user_data \
#     --sub "<cognito sub>" \
#     --output ./backup.json

import argparse
import sys

from app.repositories.exercise import DynamoExerciseRepository
from app.repositories.profile import DynamoProfileRepository
from app.repositories.workout import DynamoWorkoutRepository
from app.utils.export import build_export_payload, serialise_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export ElbieFit user data to JSON")
    parser.add_argument("--sub", required=True, help="Cognito user sub to export")
    parser.add_argument(
        "--output",
        default="backup.json",
        help="Output file path (default: backup.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user_sub: str = args.sub
    output_path: str = args.output

    profile_repo = DynamoProfileRepository()
    workout_repo = DynamoWorkoutRepository()
    exercise_repo = DynamoExerciseRepository()

    profile = profile_repo.get_for_user(user_sub)
    if not profile:
        print(f"Error: no profile found for sub={user_sub}", file=sys.stderr)
        sys.exit(1)

    payload_dict = build_export_payload(user_sub, profile, workout_repo, exercise_repo)
    json_str = serialise_export(payload_dict)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)

    import json
    data = json.loads(json_str)
    print(
        f"Exported to {output_path}: "
        f"{len(data['exercises'])} exercise(s), "
        f"{len(data['workouts'])} workout(s)"
    )


if __name__ == "__main__":
    main()
