import time
from datetime import date as DateType

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.settings import settings
from app.utils.log import logger

REGION_NAME = settings.REGION
TABLE_NAME = settings.DDB_TABLE_NAME


def get_dynamo_resource():
    kwargs = {"region_name": REGION_NAME}
    if settings.DDB_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.DDB_ENDPOINT_URL
    return boto3.resource("dynamodb", **kwargs)


def get_table():
    resource = get_dynamo_resource()
    return resource.Table(TABLE_NAME)  # type: ignore


def build_user_pk(user_sub: str) -> str:
    """
    Partition key for all user-owned items.
    Example: USER#abc-123
    """
    return f"USER#{user_sub}"


def build_workout_sk(workout_date: DateType, workout_id: str) -> str:
    """
    Build the SK for a workout item, e.g.:
    WORKOUT#2025-11-04#W1
    """
    return f"WORKOUT#{workout_date.isoformat()}#{workout_id}"


def build_set_prefix(workout_date: DateType, workout_id: str) -> str:
    """
    Prefix for set items under a workout, e.g.:
    WORKOUT#2025-11-04#W1#SET#
    """
    return f"{build_workout_sk(workout_date, workout_id)}#SET#"


def build_set_sk(workout_date: DateType, workout_id: str, set_number: int) -> str:
    """
    Build the SK for a set item, e.g.:
    WORKOUT#2025-11-04#W1#SET#001
    """
    prefix = build_set_prefix(workout_date, workout_id)
    return f"{prefix}{set_number:03d}"


def build_exercise_sk(exercise_id: str) -> str:
    """
    Sort key for an exercise item.
    Example: EXERCISE#E1
    """
    return f"EXERCISE#{exercise_id}"


# ─────────────────────────────────────────────────────────────
# Rate limiting
# ─────────────────────────────────────────────────────────────


def build_rate_limit_pk(client_id: str) -> str:
    return f"RATE#{client_id}"


def build_rate_limit_sk(window_id: int) -> str:
    return f"WIN#{window_id}"


class RateLimitDdbError(Exception):
    pass


def rate_limit_hit(
    *, client_id: str, limit: int, ttl_seconds: int = 600
) -> tuple[bool, int]:
    """
    Increment rate-limit counter for the current minute window.

    Returns: (allowed, retry_after_seconds)
    - allowed: True if within limit, False if exceeded
    - retry_after_seconds: seconds until next window (only meaningful when allowed=False)

    Notes:
    - Fixed window: 60 seconds
    - Uses DynamoDB UpdateItem ADD for atomic increment
    - Sets expires_at for TTL cleanup
    """
    now = int(time.time())
    window_id = now // 60

    pk = build_rate_limit_pk(client_id)
    sk = build_rate_limit_sk(window_id)

    expires_at = now + ttl_seconds
    retry_after = 60 - (now % 60)

    table = get_table()

    try:
        resp = table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression="ADD #count :inc SET #expires_at = :expires_at",
            ExpressionAttributeNames={
                "#count": "count",
                "#expires_at": "expires_at",
            },
            ExpressionAttributeValues={
                ":inc": 1,
                ":expires_at": expires_at,
            },
            ReturnValues="UPDATED_NEW",
        )
    except ClientError as e:
        logger.warning(
            f"Rate limit storage error; failing open.\nClient bucket: {client_id[:64]}\nError: {e.response.get("Error", {}).get("Code")}",
        )
        raise RateLimitDdbError(str(e)) from e
    except BotoCoreError as e:
        logger.warning(
            f"Rate limit connectivity error; failing open.\nClient bucket: {client_id[:64]}\nError: {e}",
        )
        raise RateLimitDdbError(str(e)) from e

    count = int(resp["Attributes"]["count"])
    if count > limit:
        logger.info(
            f"Rate limit exceeded.\nClient bucket: {client_id[:64]}\nCount: {count}\nLimit: {limit}\nWindow id: {window_id}\nRetry after: {retry_after}",
        )
        return (False, retry_after)

    return (True, retry_after)
