"""
Tests for authentication API routes.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.models import AccountType, User, UserRole, NotificationPreference, NotificationChannel
from app.auth import get_current_user


class TestRegistrationRoute:
    """Test the registration endpoint."""

    def test_register_creates_user_and_returns_token(self, monkeypatch):
        async def mock_initialize_tables():
            return None

        async def mock_get_user_by_username(username):
            assert username == "tundizzy"
            return None

        async def mock_get_user_by_email(email):
            assert email == "joshua+tunde@tabcommerce.com"
            return None

        async def mock_create_user(user_data, password_hash):
            assert user_data.username == "tundizzy"
            assert user_data.email == "joshua+tunde@tabcommerce.com"
            assert user_data.full_name == "Tundizzy Acct"
            assert user_data.phone_number == "+447700900123"
            assert user_data.account_type == AccountType.PERSONAL
            assert user_data.role == UserRole.MEMBER
            assert user_data.notification_preference == NotificationPreference.PERSONAL_REMINDER
            assert user_data.notification_channels == [NotificationChannel.SMS, NotificationChannel.EMAIL]
            assert user_data.direct_message_channel == NotificationChannel.SMS
            assert password_hash.startswith("$2b$")
            return User(
                id=1,
                username=user_data.username,
                email=user_data.email,
                full_name=user_data.full_name,
                phone_number=user_data.phone_number,
                account_type=user_data.account_type,
                role=user_data.role,
                password_hash=password_hash,
                notification_preference=user_data.notification_preference,
                notification_channels=user_data.notification_channels,
                direct_message_channel=user_data.direct_message_channel,
                is_active=True,
                created_at="2026-04-21T00:00:00",
                updated_at="2026-04-21T00:00:00",
                last_login=None,
            )

        monkeypatch.setattr("app.main.db_manager.initialize_tables", mock_initialize_tables)
        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.get_user_by_username", mock_get_user_by_username)
        monkeypatch.setattr("app.main.db_manager.get_user_by_email", mock_get_user_by_email)
        monkeypatch.setattr("app.main.db_manager.create_user", mock_create_user)

        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "full_name": "Tundizzy Acct",
                    "username": "tundizzy",
                    "email": "joshua+tunde@tabcommerce.com",
                    "phone_number": "+447700900123",
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
        assert data["user"]["username"] == "tundizzy"
        assert data["user"]["email"] == "joshua+tunde@tabcommerce.com"
        assert data["user"]["phone_number"] == "+447700900123"
        assert data["user"]["account_type"] == "personal"
        assert data["user"]["role"] == "member"

    def test_register_rejects_duplicate_email(self, monkeypatch):
        async def mock_initialize_tables():
            return None

        async def mock_get_user_by_username(username):
            return None

        async def mock_get_user_by_email(email):
            return User(
                id=1,
                username="existing-user",
                email=email,
                full_name="Existing User",
                phone_number=None,
                account_type=AccountType.PERSONAL,
                role=UserRole.MEMBER,
                password_hash="$2b$12$abcdefghijklmnopqrstuv123456789012345678901234567890",
                notification_preference=NotificationPreference.PERSONAL_REMINDER,
                notification_channels=[NotificationChannel.SMS, NotificationChannel.EMAIL],
                direct_message_channel=NotificationChannel.SMS,
                is_active=True,
                created_at="2026-04-21T00:00:00",
                updated_at="2026-04-21T00:00:00",
                last_login=None,
            )

        monkeypatch.setattr("app.main.db_manager.initialize_tables", mock_initialize_tables)
        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.get_user_by_username", mock_get_user_by_username)
        monkeypatch.setattr("app.main.db_manager.get_user_by_email", mock_get_user_by_email)

        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "full_name": "Tundizzy Acct",
                    "username": "tundizzy",
                    "email": "joshua+tunde@tabcommerce.com",
                    "password": "Password12",
                    "account_type": "personal",
                },
            )

        assert response.status_code == 409
        assert response.json()["detail"] == "An account with this email already exists"


class TestLoginRoute:
    """Test the login endpoint."""

    def test_login_accepts_email(self, monkeypatch):
        async def mock_initialize_tables():
            return None

        async def mock_get_user_by_email(email):
            assert email == "joshua+tunde@tabcommerce.com"
            return User(
                id=1,
                username="tundizzy",
                email="joshua+tunde@tabcommerce.com",
                full_name="Tundizzy Acct",
                phone_number="+447700900123",
                account_type=AccountType.PERSONAL,
                role=UserRole.MEMBER,
                password_hash="$2b$12$4.zpL89npv1MSz.4N2k6w.JVqTSOM2nI8w8uEq7sS1xvVQ6tLhA2e",
                notification_preference=NotificationPreference.PERSONAL_REMINDER,
                notification_channels=[NotificationChannel.SMS, NotificationChannel.EMAIL],
                direct_message_channel=NotificationChannel.SMS,
                is_active=True,
                created_at="2026-04-21T00:00:00",
                updated_at="2026-04-21T00:00:00",
                last_login=None,
            )

        async def mock_update_user_last_login(user_id):
            assert user_id == 1
            return True

        monkeypatch.setattr("app.main.db_manager.initialize_tables", mock_initialize_tables)
        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.get_user_by_email", mock_get_user_by_email)
        monkeypatch.setattr("app.main.db_manager.update_user_last_login", mock_update_user_last_login)
        monkeypatch.setattr("app.main.auth_service.verify_password", lambda plain, hashed: plain == "Password12")

        with TestClient(app) as client:
            response = client.post(
                "/auth/login",
                json={"email": "joshua+tunde@tabcommerce.com", "password": "Password12"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["username"] == "tundizzy"
        assert data["user"]["email"] == "joshua+tunde@tabcommerce.com"

    def test_login_rejects_username_payload(self, monkeypatch):
        async def mock_initialize_tables():
            return None

        monkeypatch.setattr("app.main.db_manager.initialize_tables", mock_initialize_tables)
        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)

        with TestClient(app) as client:
            response = client.post(
                "/auth/login",
                json={"login": "tundizzy", "password": "Password12"},
            )

        assert response.status_code == 422


class TestCurrentUserProfileRoute:
    """Test the current-user profile update endpoint."""

    def test_update_current_user_profile(self, monkeypatch):
        async def mock_initialize_tables():
            return None

        async def mock_update_user_profile(user_id, profile_data):
            assert user_id == 1
            assert profile_data.phone_number == "+447700900123"
            assert profile_data.notification_preference == NotificationPreference.PERSONAL_REMINDER
            assert profile_data.notification_channels == [NotificationChannel.SMS, NotificationChannel.EMAIL]
            return User(
                id=1,
                username="tundizzy",
                email="joshua+tunde@tabcommerce.com",
                full_name="Tundizzy Acct",
                phone_number=profile_data.phone_number,
                account_type=AccountType.PERSONAL,
                role=UserRole.MEMBER,
                password_hash="$2b$12$4.zpL89npv1MSz.4N2k6w.JVqTSOM2nI8w8uEq7sS1xvVQ6tLhA2e",
                notification_preference=profile_data.notification_preference,
                notification_channels=profile_data.notification_channels,
                direct_message_channel=NotificationChannel.SMS,
                is_active=True,
                created_at="2026-04-21T00:00:00",
                updated_at="2026-04-21T00:00:00",
                last_login=None,
            )

        monkeypatch.setattr("app.main.db_manager.initialize_tables", mock_initialize_tables)
        monkeypatch.setattr("app.main.celebration_scheduler.start", lambda: None)
        monkeypatch.setattr("app.main.celebration_scheduler.stop", lambda: None)
        monkeypatch.setattr("app.main.db_manager.update_user_profile", mock_update_user_profile)

        app.dependency_overrides = {
            get_current_user: lambda: {
                "id": 1,
                "username": "tundizzy",
                "email": "joshua+tunde@tabcommerce.com",
                "role": "member",
                "account_type": "personal",
            }
        }

        try:
            with TestClient(app) as client:
                response = client.put(
                    "/auth/me",
                    json={
                        "phone_number": "+447700900123",
                        "notification_preference": "personal_reminder",
                        "notification_channels": ["sms", "email"],
                    },
                )
        finally:
            app.dependency_overrides = {}

        assert response.status_code == 200
        data = response.json()
        assert data["phone_number"] == "+447700900123"
        assert data["notification_preference"] == "personal_reminder"
        assert data["notification_channels"] == ["sms", "email"]
