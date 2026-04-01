import pytest
from tests.test_data import TEST_WORKOUT_SK_1, USER_PK

from app.repositories.base import DynamoRepository
from app.repositories.errors import RepoError

TEST_DATA = {"PK": USER_PK, "SK": TEST_WORKOUT_SK_1}


class FakeRepo(DynamoRepository[dict]):
    """
    Minimal concrete subclass so we can instantiate DynamoRepository.
    We don't call _to_model in these tests, so returning the item is fine.
    """

    def _to_model(self, item: dict) -> dict:
        return item


def test_base_repo_to_model_raises_not_implemented(fake_table):
    # Use the base class directly so we hit the NotImplementedError path
    repo = DynamoRepository(table=fake_table)

    with pytest.raises(NotImplementedError):
        repo._to_model({"PK": USER_PK})


# ──────────────────────────── __init__ behaviour ────────────────────────────


def test_init_uses_explicit_table(fake_table):
    repo = FakeRepo(table=fake_table)
    assert repo._table is fake_table


def test_init_uses_db_get_table_when_table_not_provided(monkeypatch):
    # We'll patch app.utils.db.get_table to return a sentinel object
    from app.utils import db as db_module

    sentinel_table = object()

    def fake_get_table():
        return sentinel_table

    monkeypatch.setattr(db_module, "get_table", fake_get_table)

    repo = FakeRepo()
    assert repo._table is sentinel_table


# ──────────────────────────── _safe_query ────────────────────────────


def test_safe_query_returns_items(fake_table):
    fake_table.response = {"Items": [{"PK": USER_PK}, {"PK": "USER#2"}]}
    repo = FakeRepo(table=fake_table)

    result = repo._safe_query(KeyConditionExpression="whatever")

    assert result == fake_table.response["Items"]
    assert fake_table.last_query_kwargs == {"KeyConditionExpression": "whatever"}


def test_safe_query_missing_items_returns_empty_list(fake_table):
    fake_table.response = {}
    repo = FakeRepo(table=fake_table)

    result = repo._safe_query()

    assert result == []


def test_safe_query_wraps_client_error(failing_query_table):
    repo = FakeRepo(table=failing_query_table)

    with pytest.raises(RepoError) as excinfo:
        repo._safe_query()

    assert "Failed to query database" in str(excinfo.value)


# ──────────────────────────── _safe_put ────────────────────────────


def test_safe_put_calls_table_put_item(fake_table):
    repo = FakeRepo(table=fake_table)

    repo._safe_put(TEST_DATA)

    assert fake_table.last_put_kwargs == {"Item": TEST_DATA}


def test_safe_put_wraps_client_error(failing_put_table):
    repo = FakeRepo(table=failing_put_table)

    with pytest.raises(RepoError) as excinfo:
        repo._safe_put({"PK": USER_PK})

    assert "Failed to write to database" in str(excinfo.value)


# ──────────────────────────── _safe_get ────────────────────────────


def test_safe_get_returns_item(fake_table):
    fake_table.response = {"Item": TEST_DATA}
    repo = FakeRepo(table=fake_table)

    result = repo._safe_get(Key=TEST_DATA)

    assert result == TEST_DATA
    assert fake_table.last_get_kwargs == {"Key": TEST_DATA}


def test_safe_get_returns_none_when_item_missing(fake_table):
    fake_table.response = {}
    repo = FakeRepo(table=fake_table)

    result = repo._safe_get(Key={"PK": USER_PK})

    assert result is None


def test_safe_get_wraps_client_error(failing_get_table):
    repo = FakeRepo(table=failing_get_table)

    with pytest.raises(RepoError) as excinfo:
        repo._safe_get(Key={"PK": USER_PK})

    assert "Failed to read from database" in str(excinfo.value)


# ──────────────────────────── _safe_delete ────────────────────────────


def test_safe_delete_calls_table_delete_item(fake_table):
    repo = FakeRepo(table=fake_table)

    repo._safe_delete(Key=TEST_DATA)

    assert fake_table.last_delete_kwargs == {"Key": TEST_DATA}


def test_safe_delete_wraps_client_error(failing_delete_table):
    repo = FakeRepo(table=failing_delete_table)

    with pytest.raises(RepoError) as excinfo:
        repo._safe_delete(Key={"PK": USER_PK})

    assert "Failed to delete from database" in str(excinfo.value)


# ──────────────────────────── _safe_update ────────────────────────────


def test_safe_update_calls_table_update_item(fake_table):
    fake_table.response = {"Attributes": TEST_DATA}
    repo = FakeRepo(table=fake_table)

    result = repo._safe_update(Key=TEST_DATA, UpdateExpression="SET #n = :v")

    assert fake_table.last_update_kwargs == {
        "Key": TEST_DATA,
        "UpdateExpression": "SET #n = :v",
    }
    assert result == {"Attributes": TEST_DATA}


def test_safe_update_wraps_client_error(failing_update_table):
    repo = FakeRepo(table=failing_update_table)

    with pytest.raises(RepoError) as excinfo:
        repo._safe_update(Key={"PK": USER_PK})

    assert "Failed to update database" in str(excinfo.value)


# ──────────────────────────── _safe_query pagination ────────────────────────────


def test_safe_query_follows_last_evaluated_key(fake_table):
    """The while-True pagination loop should accumulate items across pages."""
    from tests.unit.repos.conftest import FakeTable

    page1 = {"Items": [{"PK": "USER#1"}], "LastEvaluatedKey": {"PK": "USER#1"}}
    page2 = {"Items": [{"PK": "USER#2"}, {"PK": "USER#3"}]}

    paginated_table = FakeTable(paginated_responses=[page1, page2])
    repo = FakeRepo(table=paginated_table)

    result = repo._safe_query(KeyConditionExpression="pk = :pk")

    assert len(result) == 3
    assert result[0] == {"PK": "USER#1"}
    assert result[1] == {"PK": "USER#2"}
    assert result[2] == {"PK": "USER#3"}
    # Second call should have received ExclusiveStartKey from page1
    assert paginated_table.last_query_kwargs["ExclusiveStartKey"] == {"PK": "USER#1"}
