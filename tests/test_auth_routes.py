"""
Tests for authentication API routes.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.models import Admin


class TestRegistrationRoute:
    """Test the registration endpoint."""

    def test_register_creates_account_and_returns_token(self, monkeypatch):
        async def mock_initialize_tables():
            return None

        async def mock_get_admin_by_username(username):
            assert username == "joshua+tunde@tabcommerce.com"
            return None

        async def mock_create_admin(admin_data, password_hash):
            assert admin_data.username == "joshua+tunde@tabcommerce.com"
            assert admin_data.is_active is True
            assert password_hash.startswith("$2b$")
            return Admin(
                id=1,
                username=admin_data.username,
                password_hash=password_hash,
                is_active=True,
                created_at="2026-04-21T00:00:00",
                updated_at="2026-04-21T00:00:00",
                last_login=None,
            )

        monkeypatch.setattr("app.main.db_manager.initialize_tables", mock_initialize_tables)
        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.get_admin_by_username", mock_get_admin_by_username)
        monkeypatch.setattr("app.main.db_manager.create_admin", mock_create_admin)

        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "full_name": "Tundizzy Acct",
                    "email": "joshua+tunde@tabcommerce.com",
                    "password": "Password12",
                    "account_type": "personal",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Registration successful"
        assert data["token_type"] == "bearer"
        assert isinstance(data["access_token"], str)
        assert data["access_token"]
        assert data["admin"]["username"] == "joshua+tunde@tabcommerce.com"
        assert data["admin"]["is_active"] is True

    def test_register_rejects_duplicate_email(self, monkeypatch):
        async def mock_initialize_tables():
            return None

        async def mock_get_admin_by_username(username):
            return Admin(
                id=1,
                username=username,
                password_hash="$2b$12$abcdefghijklmnopqrstuv123456789012345678901234567890",
                is_active=True,
                created_at="2026-04-21T00:00:00",
                updated_at="2026-04-21T00:00:00",
                last_login=None,
            )

        monkeypatch.setattr("app.main.db_manager.initialize_tables", mock_initialize_tables)
        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.get_admin_by_username", mock_get_admin_by_username)

        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "full_name": "Tundizzy Acct",
                    "email": "joshua+tunde@tabcommerce.com",
                    "password": "Password12",
                    "account_type": "personal",
                },
            )

        assert response.status_code == 409
        assert response.json()["detail"] == "An account with this email already exists"
