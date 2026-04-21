"""
Cross-tenant isolation tests.

These tests pin the contract that every tenant-data code path filters on
``owner_user_id``. They work at two levels:

1. ``DatabaseManager`` methods get a fake Supabase client injected and we
   assert that each read/write carries an ``.eq("owner_user_id", ...)``
   constraint and stamps ``owner_user_id`` on every insert.
2. A handful of FastAPI routes are exercised with the ``get_current_user``
   dependency overridden to two different users; we then assert the
   ``db_manager`` / ``service`` layers received the caller's id as
   ``owner_user_id``.

Together these cover the regression that prompted this module: after we
removed the admin-only guard, every authenticated user could previously see
every other user's data because tenancy was never enforced below the HTTP
layer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import DatabaseManager
from app.main import app
from app.models import EventType, PersonCreate, PersonUpdate


# ---------------------------------------------------------------------------
# Fake Supabase client
# ---------------------------------------------------------------------------
class _Result:
    def __init__(self, data: Optional[List[Dict[str, Any]]] = None):
        self.data = list(data) if data is not None else []


class _Query:
    """
    Records filters and payloads so tests can assert on them.

    Only implements the chain methods DatabaseManager actually uses:
    ``select``, ``insert``, ``update``, ``eq``, ``order``, ``range``, ``limit``,
    ``execute``.
    """

    def __init__(self, table: "_Table", op: str, payload: Any = None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters: List[tuple] = []

    def select(self, *_args, **_kwargs):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def eq(self, column: str, value: Any):
        self.filters.append((column, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.table.queries.append(self)
        return self.table.next_result(self)


class _Table:
    def __init__(self, name: str, client: "FakeSupabase"):
        self.name = name
        self.client = client
        self.queries: List[_Query] = []

    def _new_query(self) -> _Query:
        return _Query(self, op="select")

    def select(self, *args, **kwargs):
        return self._new_query().select(*args, **kwargs)

    def insert(self, payload):
        return self._new_query().insert(payload)

    def update(self, payload):
        return self._new_query().update(payload)

    def next_result(self, query: _Query) -> _Result:
        key = (self.name, query.op)
        responses = self.client.responses.get(key)
        if responses:
            # Pop in order; if tests register fewer than calls made, reuse last.
            if len(responses) == 1:
                return _Result(responses[0])
            return _Result(responses.pop(0))
        return _Result([])


class FakeSupabase:
    def __init__(self):
        self.tables: Dict[str, _Table] = {}
        # Keyed by (table_name, op) -> list of data payloads, returned in order.
        self.responses: Dict[tuple, List[List[Dict[str, Any]]]] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name, self)
        return self.tables[name]

    def set_response(self, table: str, op: str, rows: List[Dict[str, Any]]) -> None:
        self.responses[(table, op)] = [rows]

    def queue_responses(self, table: str, op: str, rows_list: List[List[Dict[str, Any]]]) -> None:
        self.responses[(table, op)] = list(rows_list)

    def queries(self, table: str) -> List[_Query]:
        return self.tables[table].queries if table in self.tables else []


def _make_db() -> tuple[DatabaseManager, FakeSupabase]:
    db = DatabaseManager()
    fake = FakeSupabase()
    db.supabase = fake
    return db, fake


def _person_row(owner_user_id: int, person_id: int = 1, **overrides: Any) -> Dict[str, Any]:
    row = {
        "id": person_id,
        "owner_user_id": owner_user_id,
        "name": "Alice",
        "event_type": "birthday",
        "event_date": "03-15",
        "year": 1990,
        "spouse": None,
        "phone_number": None,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# DatabaseManager: people
# ---------------------------------------------------------------------------
class TestPeopleTenancy:
    @pytest.mark.asyncio
    async def test_get_all_people_filters_by_owner(self):
        db, fake = _make_db()
        fake.set_response("people", "select", [_person_row(7)])

        people = await db.get_all_people(owner_user_id=7)

        assert [p.owner_user_id for p in people] == [7]
        assert ("owner_user_id", 7) in fake.queries("people")[0].filters

    @pytest.mark.asyncio
    async def test_create_person_stamps_owner(self):
        db, fake = _make_db()
        fake.set_response("people", "insert", [_person_row(7)])

        person_data = PersonCreate(
            name="Alice",
            event_type=EventType.BIRTHDAY,
            event_date="03-15",
            year=1990,
        )
        person = await db.create_person(person_data, owner_user_id=7)

        assert person.owner_user_id == 7
        insert_query = fake.queries("people")[0]
        assert insert_query.op == "insert"
        assert insert_query.payload["owner_user_id"] == 7

    @pytest.mark.asyncio
    async def test_get_person_by_id_refuses_cross_tenant(self):
        db, fake = _make_db()
        # User 9 asks for id=1 which actually belongs to user 7: fake returns [].
        fake.set_response("people", "select", [])

        person = await db.get_person_by_id(1, owner_user_id=9)

        assert person is None
        select_query = fake.queries("people")[0]
        assert ("id", 1) in select_query.filters
        assert ("owner_user_id", 9) in select_query.filters

    @pytest.mark.asyncio
    async def test_update_person_requires_owner_match(self):
        db, fake = _make_db()
        # Update returns [] -> not this user's row; we never fetch.
        fake.set_response("people", "update", [])

        updated = await db.update_person(
            1,
            PersonUpdate(name="Hacker"),
            owner_user_id=9,
        )

        assert updated is None
        update_query = fake.queries("people")[0]
        assert update_query.op == "update"
        assert ("id", 1) in update_query.filters
        assert ("owner_user_id", 9) in update_query.filters

    @pytest.mark.asyncio
    async def test_delete_person_requires_owner_match(self):
        db, fake = _make_db()
        fake.set_response("people", "update", [])  # soft-delete via update

        success = await db.delete_person(1, owner_user_id=9)

        assert success is False
        assert ("owner_user_id", 9) in fake.queries("people")[0].filters

    @pytest.mark.asyncio
    async def test_upsert_person_is_scoped_per_owner(self):
        """
        Two users upserting "Alice / birthday" must not clobber each other.

        Verified by the existence check filtering on ``owner_user_id`` before
        falling through to insert.
        """
        db, fake = _make_db()
        # First call (existence check) returns nothing: we should fall through
        # to an insert, not an update of user 7's row.
        fake.queue_responses("people", "select", [[]])
        fake.queue_responses("people", "insert", [[_person_row(9)]])

        person_data = PersonCreate(
            name="Alice",
            event_type=EventType.BIRTHDAY,
            event_date="03-15",
            year=1990,
        )
        person = await db.upsert_person(person_data, owner_user_id=9)

        assert person.owner_user_id == 9
        select_query = fake.queries("people")[0]
        assert ("owner_user_id", 9) in select_query.filters
        assert ("name", "Alice") in select_query.filters


# ---------------------------------------------------------------------------
# DatabaseManager: message logs
# ---------------------------------------------------------------------------
class TestMessageLogTenancy:
    @pytest.mark.asyncio
    async def test_log_message_stamps_owner(self):
        from datetime import date as date_type

        db, fake = _make_db()
        fake.set_response("message_logs", "insert", [])

        await db.log_message(
            person_id=1,
            message_content="hi",
            sent_date=date_type(2026, 1, 1),
            success=True,
            owner_user_id=7,
        )

        insert_query = fake.queries("message_logs")[0]
        assert insert_query.op == "insert"
        assert insert_query.payload["owner_user_id"] == 7

    @pytest.mark.asyncio
    async def test_get_all_message_logs_filters_by_owner(self):
        db, fake = _make_db()
        fake.set_response("message_logs", "select", [])

        await db.get_all_message_logs(owner_user_id=7)

        assert ("owner_user_id", 7) in fake.queries("message_logs")[0].filters

    @pytest.mark.asyncio
    async def test_get_message_log_by_id_refuses_cross_tenant(self):
        db, fake = _make_db()
        fake.set_response("message_logs", "select", [])

        result = await db.get_message_log_by_id(42, owner_user_id=9)

        assert result is None
        q = fake.queries("message_logs")[0]
        assert ("id", 42) in q.filters
        assert ("owner_user_id", 9) in q.filters


# ---------------------------------------------------------------------------
# DatabaseManager: CSV upload history
# ---------------------------------------------------------------------------
class TestCSVUploadTenancy:
    @pytest.mark.asyncio
    async def test_log_csv_upload_stamps_owner(self):
        db, fake = _make_db()
        fake.set_response("csv_uploads", "insert", [])

        await db.log_csv_upload(
            filename="roster.csv",
            records_processed=10,
            records_added=5,
            records_updated=5,
            success=True,
            owner_user_id=7,
        )

        q = fake.queries("csv_uploads")[0]
        assert q.op == "insert"
        assert q.payload["owner_user_id"] == 7

    @pytest.mark.asyncio
    async def test_get_csv_upload_history_filters_by_owner(self):
        db, fake = _make_db()
        fake.set_response("csv_uploads", "select", [])

        await db.get_csv_upload_history(owner_user_id=7)

        assert ("owner_user_id", 7) in fake.queries("csv_uploads")[0].filters


# ---------------------------------------------------------------------------
# DatabaseManager: AI wish audit logs
# ---------------------------------------------------------------------------
class TestAIWishAuditLogTenancy:
    @pytest.mark.asyncio
    async def test_audit_log_listing_filters_by_owner(self):
        db, fake = _make_db()
        fake.set_response("ai_wish_audit_logs", "select", [])

        await db.get_ai_wish_audit_logs(limit=10, offset=0, owner_user_id=7)

        assert ("owner_user_id", 7) in fake.queries("ai_wish_audit_logs")[0].filters

    @pytest.mark.asyncio
    async def test_audit_log_by_request_id_scopes_to_owner_when_provided(self):
        db, fake = _make_db()
        fake.set_response("ai_wish_audit_logs", "select", [])

        await db.get_ai_wish_audit_log_by_request_id(
            "req-abc", owner_user_id=7
        )

        q = fake.queries("ai_wish_audit_logs")[0]
        assert ("request_id", "req-abc") in q.filters
        assert ("owner_user_id", 7) in q.filters

    @pytest.mark.asyncio
    async def test_audit_log_by_request_id_unscoped_when_owner_is_none(self):
        """
        The regenerate endpoint calls this with ``owner_user_id=None`` for
        anonymous callers; in that case we must NOT add an owner_user_id
        filter, otherwise anonymous regenerations silently fail.
        """
        db, fake = _make_db()
        fake.set_response("ai_wish_audit_logs", "select", [])

        await db.get_ai_wish_audit_log_by_request_id(
            "req-anon", owner_user_id=None
        )

        q = fake.queries("ai_wish_audit_logs")[0]
        filter_cols = {col for col, _ in q.filters}
        assert "request_id" in filter_cols
        assert "owner_user_id" not in filter_cols


# ---------------------------------------------------------------------------
# HTTP layer: caller id is forwarded to the data layer
# ---------------------------------------------------------------------------
class TestAPIForwardsCallerId:
    """
    Verify each tenant-bearing route forwards ``current_user["id"]`` as
    ``owner_user_id``, for two different callers, so we catch any route that
    accidentally hardcodes a user or forgets the kwarg.
    """

    def _override_user(self, user_id: int) -> None:
        app.dependency_overrides[get_current_user] = lambda: {
            "id": user_id,
            "username": f"user{user_id}",
            "email": f"user{user_id}@example.com",
            "role": "member",
            "account_type": "personal",
        }

    def setup_method(self) -> None:
        app.dependency_overrides = {}

    def teardown_method(self) -> None:
        app.dependency_overrides = {}

    @pytest.mark.parametrize("user_id", [7, 9])
    def test_get_people_forwards_owner(self, monkeypatch, user_id):
        captured: Dict[str, Any] = {}

        async def fake_get_all_people(*, owner_user_id: int):
            captured["owner"] = owner_user_id
            return []

        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.initialize_tables", AsyncMock(return_value=None))
        monkeypatch.setattr("app.main.db_manager.get_all_people", fake_get_all_people)

        self._override_user(user_id)
        with TestClient(app) as client:
            response = client.get("/people")

        assert response.status_code == 200
        assert captured["owner"] == user_id

    @pytest.mark.parametrize("user_id", [7, 9])
    def test_get_person_by_id_forwards_owner(self, monkeypatch, user_id):
        captured: Dict[str, Any] = {}

        async def fake_get_person_by_id(person_id, *, owner_user_id: int):
            captured["owner"] = owner_user_id
            captured["person_id"] = person_id
            return None  # triggers 404, which is the right answer for a cross-tenant id

        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.initialize_tables", AsyncMock(return_value=None))
        monkeypatch.setattr("app.main.db_manager.get_person_by_id", fake_get_person_by_id)

        self._override_user(user_id)
        with TestClient(app) as client:
            response = client.get("/people/123")

        assert response.status_code == 404
        assert captured == {"owner": user_id, "person_id": 123}

    @pytest.mark.parametrize("user_id", [7, 9])
    def test_messages_forward_owner(self, monkeypatch, user_id):
        captured: Dict[str, Any] = {}

        async def fake_get_all_message_logs(*, owner_user_id: int):
            captured["owner"] = owner_user_id
            return []

        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.initialize_tables", AsyncMock(return_value=None))
        monkeypatch.setattr("app.main.db_manager.get_all_message_logs", fake_get_all_message_logs)

        self._override_user(user_id)
        with TestClient(app) as client:
            response = client.get("/messages")

        assert response.status_code == 200
        assert captured["owner"] == user_id

    @pytest.mark.parametrize("user_id", [7, 9])
    def test_csv_uploads_forward_owner(self, monkeypatch, user_id):
        captured: Dict[str, Any] = {}

        async def fake_get_csv_upload_history(*, owner_user_id: int):
            captured["owner"] = owner_user_id
            return []

        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.initialize_tables", AsyncMock(return_value=None))
        monkeypatch.setattr("app.main.db_manager.get_csv_upload_history", fake_get_csv_upload_history)

        self._override_user(user_id)
        with TestClient(app) as client:
            response = client.get("/csv-uploads")

        assert response.status_code == 200
        assert captured["owner"] == user_id

    @pytest.mark.parametrize("user_id", [7, 9])
    def test_csv_files_listing_forwards_owner(self, monkeypatch, user_id):
        captured: Dict[str, Any] = {}

        async def fake_list_csv_files(*, owner_user_id: int):
            captured["owner"] = owner_user_id
            return []

        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.initialize_tables", AsyncMock(return_value=None))
        monkeypatch.setattr("app.main.storage_manager.list_csv_files", fake_list_csv_files)

        self._override_user(user_id)
        with TestClient(app) as client:
            response = client.get("/csv-files")

        assert response.status_code == 200
        assert captured["owner"] == user_id

    def test_csv_file_delete_rejects_cross_tenant_path(self, monkeypatch):
        """
        Even if a user guesses another user's storage path, storage_manager
        refuses and the endpoint returns 404.
        """
        captured: Dict[str, Any] = {}

        async def spy_delete(file_path: str, *, owner_user_id: int):
            captured["file_path"] = file_path
            captured["owner"] = owner_user_id
            # Mirror production behaviour: deny anything not under the user's
            # own prefix.
            return file_path.startswith(f"uploads/{owner_user_id}/")

        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.initialize_tables", AsyncMock(return_value=None))
        monkeypatch.setattr("app.main.storage_manager.delete_csv_file", spy_delete)

        self._override_user(7)
        with TestClient(app) as client:
            # This path belongs to user 9, not 7.
            response = client.delete("/csv-files/uploads/9/2025-01-01_roster.csv")

        assert response.status_code == 404
        assert captured["owner"] == 7

    @pytest.mark.parametrize("user_id", [7, 9])
    def test_admin_audit_logs_forward_owner(self, monkeypatch, user_id):
        captured: Dict[str, Any] = {}

        async def fake_get_ai_wish_audit_logs(limit, offset, *, owner_user_id: int):
            captured["owner"] = owner_user_id
            return []

        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.initialize_tables", AsyncMock(return_value=None))
        monkeypatch.setattr(
            "app.main.db_manager.get_ai_wish_audit_logs",
            fake_get_ai_wish_audit_logs,
        )

        self._override_user(user_id)
        with TestClient(app) as client:
            response = client.get("/admin/ai-wish-audit-logs")

        assert response.status_code == 200
        assert captured["owner"] == user_id
