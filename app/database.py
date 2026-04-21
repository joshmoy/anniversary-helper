"""
Database connection and operations using Supabase.
"""
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from supabase import create_client, Client
from app.config import settings
from app.models import (
    Person,
    PersonCreate,
    PersonUpdate,
    MessageLog,
    CSVUpload,
    User,
    UserCreate,
    UserProfileUpdate,
    RateLimitRecord,
    AIWishAuditLog,
    AIWishAuditLogCreate,
    NotificationChannel,
    NotificationPreference,
    NotificationPreferencesUpdate,
)

DEFAULT_NOTIFICATION_PREFERENCE = NotificationPreference.PERSONAL_REMINDER.value
DEFAULT_NOTIFICATION_CHANNELS = [NotificationChannel.SMS.value, NotificationChannel.EMAIL.value]
DEFAULT_DIRECT_MESSAGE_CHANNEL = NotificationChannel.SMS.value

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database operations with Supabase."""

    @staticmethod
    def _serialize_notification_channels(channels: List[NotificationChannel | str]) -> str:
        """Serialize a list of notification channels for database storage."""
        return ",".join(
            channel.value if isinstance(channel, NotificationChannel) else str(channel)
            for channel in channels
        )

    @staticmethod
    def _parse_notification_channels(value: Any) -> List[str]:
        """Parse notification_channels from a DB value into a list of strings."""
        if isinstance(value, list):
            return [str(channel) for channel in value if channel]
        if isinstance(value, str) and value:
            return [channel for channel in value.split(",") if channel]
        return list(DEFAULT_NOTIFICATION_CHANNELS)

    @classmethod
    def _merge_preferences(
        cls,
        user_record: Dict[str, Any],
        preferences_record: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Combine a raw users row with its notification preferences row.

        The API's ``User`` model expects preference fields alongside identity
        fields, but they are stored in the separate
        ``user_notification_preferences`` table. This merges them for model
        construction, defaulting when no preferences row exists yet.
        """
        merged = dict(user_record)
        if preferences_record:
            merged["notification_preference"] = (
                preferences_record.get("notification_preference")
                or DEFAULT_NOTIFICATION_PREFERENCE
            )
            merged["notification_channels"] = cls._parse_notification_channels(
                preferences_record.get("notification_channels")
            )
            merged["direct_message_channel"] = (
                preferences_record.get("direct_message_channel")
                or DEFAULT_DIRECT_MESSAGE_CHANNEL
            )
        else:
            merged["notification_preference"] = DEFAULT_NOTIFICATION_PREFERENCE
            merged["notification_channels"] = list(DEFAULT_NOTIFICATION_CHANNELS)
            merged["direct_message_channel"] = DEFAULT_DIRECT_MESSAGE_CHANNEL
        return merged

    def __init__(self):
        """Initialize Supabase client."""
        try:
            # Only initialize if we have valid settings
            if hasattr(settings, 'supabase_url') and hasattr(settings, 'supabase_key'):
                supabase_token = settings.supabase_service_key or settings.supabase_key

                if settings.supabase_url and supabase_token:
                    self.supabase: Client = create_client(
                        settings.supabase_url,
                        supabase_token
                    )
                    if settings.supabase_service_key:
                        logger.info("Initialized Supabase client with service role key for server-side operations")
                    else:
                        logger.warning("Supabase service role key not configured; falling back to SUPABASE_KEY")
                else:
                    logger.warning("Supabase credentials not configured. Database operations will be disabled.")
                    self.supabase = None
            else:
                logger.warning("Supabase settings not found. Database operations will be disabled.")
                self.supabase = None
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.supabase = None

    async def initialize_tables(self):
        """Create tables if they don't exist."""
        try:
            # Create people table
            people_table = """
            CREATE TABLE IF NOT EXISTS people (
                id SERIAL PRIMARY KEY,
                owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('birthday', 'anniversary')),
                event_date VARCHAR(5) NOT NULL,
                year INTEGER,
                spouse VARCHAR(255),
                phone_number VARCHAR(30),
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """

            # Create message_logs table
            message_logs_table = """
            CREATE TABLE IF NOT EXISTS message_logs (
                id SERIAL PRIMARY KEY,
                owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                person_id INTEGER REFERENCES people(id),
                message_content TEXT NOT NULL,
                sent_date DATE NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """

            # Create csv_uploads table
            csv_uploads_table = """
            CREATE TABLE IF NOT EXISTS csv_uploads (
                id SERIAL PRIMARY KEY,
                owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                upload_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                records_processed INTEGER NOT NULL,
                records_added INTEGER NOT NULL,
                records_updated INTEGER NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT
            );
            """

            # Create users table (identity only; delivery prefs live in
            # user_notification_preferences).
            users_table = """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                full_name VARCHAR(255) NOT NULL,
                phone_number VARCHAR(30),
                password_hash VARCHAR(255) NOT NULL,
                account_type VARCHAR(50) NOT NULL DEFAULT 'personal',
                role VARCHAR(20) NOT NULL DEFAULT 'member',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_login TIMESTAMP WITH TIME ZONE
            );
            """

            # Create user_notification_preferences table
            user_notification_preferences_table = """
            CREATE TABLE IF NOT EXISTS user_notification_preferences (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                notification_preference VARCHAR(50) NOT NULL DEFAULT 'personal_reminder',
                notification_channels VARCHAR(255) NOT NULL DEFAULT 'sms,email',
                direct_message_channel VARCHAR(50) NOT NULL DEFAULT 'sms',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """

            # Create rate_limiting table
            rate_limiting_table = """
            CREATE TABLE IF NOT EXISTS rate_limiting (
                id SERIAL PRIMARY KEY,
                ip_address VARCHAR(45) NOT NULL,
                request_count INTEGER DEFAULT 1,
                window_start TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_request_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(ip_address)
            );
            """

            # Create ai_wish_audit_logs table. owner_user_id is nullable because
            # unauthenticated callers can generate wishes; those rows have no owner
            # and are never surfaced through the per-user audit log endpoints.
            ai_wish_audit_logs_table = """
            CREATE TABLE IF NOT EXISTS ai_wish_audit_logs (
                id SERIAL PRIMARY KEY,
                owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                request_id VARCHAR(255) NOT NULL,
                original_request_id VARCHAR(255),
                ip_address VARCHAR(255) NOT NULL,
                request_data JSONB NOT NULL,
                response_data JSONB NOT NULL,
                ai_service_used VARCHAR(50) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """

            # Create index for efficient lookups
            rate_limiting_index = """
            CREATE INDEX IF NOT EXISTS idx_rate_limiting_ip_address ON rate_limiting(ip_address);
            CREATE INDEX IF NOT EXISTS idx_rate_limiting_window_start ON rate_limiting(window_start);
            """
            
            # Create indexes for AI wish audit logs
            ai_wish_audit_indexes = """
            CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_request_id ON ai_wish_audit_logs(request_id);
            CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_original_request_id ON ai_wish_audit_logs(original_request_id);
            CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_created_at ON ai_wish_audit_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_ai_service ON ai_wish_audit_logs(ai_service_used);
            """

            # Execute table creation (Note: Supabase handles this via SQL editor)
            logger.info("Database tables initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing database tables: {e}")
            raise

    async def create_person(self, person_data: PersonCreate, *, owner_user_id: int) -> Person:
        """Create a new person owned by ``owner_user_id``."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            data = {
                "owner_user_id": owner_user_id,
                "name": person_data.name,
                "event_type": person_data.event_type.value,
                "event_date": person_data.event_date,
                "year": person_data.year,
                "spouse": person_data.spouse,
                "phone_number": person_data.phone_number,
                "active": person_data.active
            }

            result = self.supabase.table("people").insert(data).execute()

            if result.data:
                return Person(**result.data[0])
            else:
                raise Exception("Failed to create person")

        except Exception as e:
            logger.error(f"Error creating person: {e}")
            raise

    async def get_people_by_date(self, target_date: str, *, owner_user_id: int) -> List[Person]:
        """Get active people with events on a date, scoped to a single owner."""
        try:
            result = (
                self.supabase.table("people")
                .select("*")
                .eq("owner_user_id", owner_user_id)
                .eq("event_date", target_date)
                .eq("active", True)
                .execute()
            )

            return [Person(**person) for person in result.data]

        except Exception as e:
            logger.error(f"Error getting people by date: {e}")
            raise

    async def get_all_people(self, *, owner_user_id: int) -> List[Person]:
        """Get all people owned by ``owner_user_id``."""
        try:
            result = (
                self.supabase.table("people")
                .select("*")
                .eq("owner_user_id", owner_user_id)
                .execute()
            )
            return [Person(**person) for person in result.data]

        except Exception as e:
            logger.error(f"Error getting all people: {e}")
            raise

    async def upsert_person(self, person_data: PersonCreate, *, owner_user_id: int) -> Person:
        """Insert or update a person keyed on (owner_user_id, name, event_type).

        The upsert key is scoped to the owner so two different users can each
        have a "John Smith birthday" without colliding.
        """
        try:
            existing = (
                self.supabase.table("people")
                .select("*")
                .eq("owner_user_id", owner_user_id)
                .eq("name", person_data.name)
                .eq("event_type", person_data.event_type.value)
                .execute()
            )

            if existing.data:
                person_id = existing.data[0]["id"]
                update_data = {
                    "event_date": person_data.event_date,
                    "year": person_data.year,
                    "spouse": person_data.spouse,
                    "phone_number": person_data.phone_number,
                    "active": person_data.active,
                    "updated_at": datetime.now().isoformat()
                }

                result = (
                    self.supabase.table("people")
                    .update(update_data)
                    .eq("id", person_id)
                    .eq("owner_user_id", owner_user_id)
                    .execute()
                )
                return Person(**result.data[0])
            return await self.create_person(person_data, owner_user_id=owner_user_id)

        except Exception as e:
            logger.error(f"Error upserting person: {e}")
            raise

    async def log_message(
        self,
        person_id: int,
        message_content: str,
        sent_date: date,
        success: bool,
        error_message: Optional[str] = None,
        *,
        owner_user_id: int,
    ):
        """Log a sent message under ``owner_user_id``."""
        try:
            data = {
                "owner_user_id": owner_user_id,
                "person_id": person_id,
                "message_content": message_content,
                "sent_date": sent_date.isoformat(),
                "success": success,
                "error_message": error_message
            }

            self.supabase.table("message_logs").insert(data).execute()
            logger.info(f"Message log created for person {person_id}")

        except Exception as e:
            logger.error(f"Error logging message: {e}")
            raise

    async def get_all_message_logs(self, *, owner_user_id: int):
        """Get message logs owned by ``owner_user_id``, with person info joined."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = (
                self.supabase.table("message_logs")
                .select("*, people(name, event_type, phone_number)")
                .eq("owner_user_id", owner_user_id)
                .order("created_at", desc=True)
                .execute()
            )

            if result.data:
                messages = []
                for log in result.data:
                    message_data = {
                        "id": log["id"],
                        "owner_user_id": log["owner_user_id"],
                        "person_id": log["person_id"],
                        "message_content": log["message_content"],
                        "sent_date": log["sent_date"],
                        "success": log["success"],
                        "error_message": log["error_message"],
                        "created_at": log["created_at"],
                        "person_name": log["people"]["name"] if log["people"] else None,
                        "person_event_type": log["people"]["event_type"] if log["people"] else None,
                        "person_phone": log["people"]["phone_number"] if log["people"] else None
                    }
                    messages.append(message_data)
                return messages
            return []

        except Exception as e:
            logger.error(f"Error getting message logs: {e}")
            raise

    async def get_message_log_by_id(self, message_id: int, *, owner_user_id: int):
        """Get a specific message log if it belongs to ``owner_user_id``.

        Returns ``None`` both when the log does not exist and when it exists
        but is owned by someone else; callers translate that into a 404 so we
        don't leak the existence of cross-tenant rows.
        """
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = (
                self.supabase.table("message_logs")
                .select("*, people(name, event_type, phone_number)")
                .eq("id", message_id)
                .eq("owner_user_id", owner_user_id)
                .execute()
            )

            if result.data and len(result.data) > 0:
                log = result.data[0]
                return {
                    "id": log["id"],
                    "owner_user_id": log["owner_user_id"],
                    "person_id": log["person_id"],
                    "message_content": log["message_content"],
                    "sent_date": log["sent_date"],
                    "success": log["success"],
                    "error_message": log["error_message"],
                    "created_at": log["created_at"],
                    "person_name": log["people"]["name"] if log["people"] else None,
                    "person_event_type": log["people"]["event_type"] if log["people"] else None,
                    "person_phone": log["people"]["phone_number"] if log["people"] else None
                }
            return None

        except Exception as e:
            logger.error(f"Error getting message log {message_id}: {e}")
            raise

    async def get_person_by_id(self, person_id: int, *, owner_user_id: int) -> Optional[Person]:
        """Get a person if owned by ``owner_user_id``; otherwise return None."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = (
                self.supabase.table("people")
                .select("*")
                .eq("id", person_id)
                .eq("owner_user_id", owner_user_id)
                .execute()
            )

            if result.data and len(result.data) > 0:
                return Person(**result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting person {person_id}: {e}")
            raise

    async def update_person(
        self,
        person_id: int,
        person_data: PersonUpdate,
        *,
        owner_user_id: int,
    ) -> Optional[Person]:
        """Update a person only if it belongs to ``owner_user_id``."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            update_data = {}
            if person_data.name is not None:
                update_data["name"] = person_data.name
            if person_data.event_type is not None:
                update_data["event_type"] = person_data.event_type.value
            if person_data.event_date is not None:
                update_data["event_date"] = person_data.event_date
            if person_data.year is not None:
                update_data["year"] = person_data.year
            if person_data.spouse is not None:
                update_data["spouse"] = person_data.spouse
            if person_data.phone_number is not None:
                update_data["phone_number"] = person_data.phone_number
            if person_data.active is not None:
                update_data["active"] = person_data.active

            if update_data:
                update_data["updated_at"] = datetime.now().isoformat()

                update_result = (
                    self.supabase.table("people")
                    .update(update_data)
                    .eq("id", person_id)
                    .eq("owner_user_id", owner_user_id)
                    .execute()
                )

                if update_result.data:
                    fetch_result = (
                        self.supabase.table("people")
                        .select("*")
                        .eq("id", person_id)
                        .eq("owner_user_id", owner_user_id)
                        .execute()
                    )
                    if fetch_result.data and len(fetch_result.data) > 0:
                        return Person(**fetch_result.data[0])

            return None

        except Exception as e:
            logger.error(f"Error updating person {person_id}: {e}")
            raise

    async def delete_person(self, person_id: int, *, owner_user_id: int) -> bool:
        """Soft delete (active=False) if the person belongs to ``owner_user_id``."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = (
                self.supabase.table("people")
                .update(
                    {
                        "active": False,
                        "updated_at": datetime.now().isoformat(),
                    }
                )
                .eq("id", person_id)
                .eq("owner_user_id", owner_user_id)
                .execute()
            )

            return bool(result.data)

        except Exception as e:
            logger.error(f"Error deleting person {person_id}: {e}")
            raise

    async def log_csv_upload(
        self,
        filename: str,
        records_processed: int,
        records_added: int,
        records_updated: int,
        success: bool,
        error_message: Optional[str] = None,
        storage_path: Optional[str] = None,
        *,
        owner_user_id: int,
    ) -> None:
        """Log a CSV upload owned by ``owner_user_id``."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            data = {
                "owner_user_id": owner_user_id,
                "filename": filename,
                "upload_date": datetime.now().isoformat(),
                "records_processed": records_processed,
                "records_added": records_added,
                "records_updated": records_updated,
                "success": success,
                "error_message": error_message,
                "storage_path": storage_path
            }

            self.supabase.table("csv_uploads").insert(data).execute()
            logger.info(f"CSV upload log created for file {filename}")

        except Exception as e:
            logger.error(f"Error logging CSV upload: {e}")
            raise

    async def get_csv_upload_history(self, *, owner_user_id: int) -> List[Dict[str, Any]]:
        """Get CSV upload history for ``owner_user_id``."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = (
                self.supabase.table("csv_uploads")
                .select("*")
                .eq("owner_user_id", owner_user_id)
                .order("upload_date", desc=True)
                .execute()
            )
            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error getting CSV upload history: {e}")
            raise

    # User Management Methods

    async def _get_notification_preferences(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch the raw notification preferences row for a user, if any."""
        if not self.supabase:
            raise Exception("Database not initialized")

        result = (
            self.supabase.table("user_notification_preferences")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    async def _upsert_notification_preferences(
        self,
        user_id: int,
        *,
        notification_preference: Optional[str] = None,
        notification_channels: Optional[str] = None,
        direct_message_channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert or update a user's notification preferences row.

        Unspecified fields use table defaults on insert and are left alone on
        update.
        """
        if not self.supabase:
            raise Exception("Database not initialized")

        existing = await self._get_notification_preferences(user_id)
        now_iso = datetime.now().isoformat()

        if existing:
            update_data: Dict[str, Any] = {"updated_at": now_iso}
            if notification_preference is not None:
                update_data["notification_preference"] = notification_preference
            if notification_channels is not None:
                update_data["notification_channels"] = notification_channels
            if direct_message_channel is not None:
                update_data["direct_message_channel"] = direct_message_channel
            if len(update_data) == 1:  # only updated_at changed
                return existing
            result = (
                self.supabase.table("user_notification_preferences")
                .update(update_data)
                .eq("user_id", user_id)
                .execute()
            )
            if result.data:
                return result.data[0]
            return {**existing, **update_data}

        insert_data: Dict[str, Any] = {
            "user_id": user_id,
            "notification_preference": notification_preference or DEFAULT_NOTIFICATION_PREFERENCE,
            "notification_channels": notification_channels or ",".join(DEFAULT_NOTIFICATION_CHANNELS),
            "direct_message_channel": direct_message_channel or DEFAULT_DIRECT_MESSAGE_CHANNEL,
        }
        result = (
            self.supabase.table("user_notification_preferences")
            .insert(insert_data)
            .execute()
        )
        if result.data:
            return result.data[0]
        raise Exception("Failed to create user notification preferences")

    async def _build_user(self, user_record: Dict[str, Any]) -> User:
        """Load notification preferences and construct a User model."""
        preferences = await self._get_notification_preferences(user_record["id"])
        return User(**self._merge_preferences(user_record, preferences))

    async def create_user(self, user_data: UserCreate, password_hash: str) -> User:
        """Create a new user and its notification preferences row."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            data = {
                "username": user_data.username,
                "email": user_data.email,
                "full_name": user_data.full_name,
                "phone_number": user_data.phone_number,
                "password_hash": password_hash,
                "account_type": user_data.account_type.value,
                "role": user_data.role.value,
                "is_active": user_data.is_active,
            }

            result = self.supabase.table("users").insert(data).execute()

            if not result.data:
                raise Exception("Failed to create user")

            user_record = result.data[0]

            await self._upsert_notification_preferences(
                user_record["id"],
                notification_preference=user_data.notification_preference.value,
                notification_channels=self._serialize_notification_channels(user_data.notification_channels),
                direct_message_channel=user_data.direct_message_channel.value,
            )

            return await self._build_user(user_record)

        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("users").select("*").eq("username", username).execute()

            if result.data and len(result.data) > 0:
                return await self._build_user(result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting user by username {username}: {e}")
            raise

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("users").select("*").eq("email", email).execute()

            if result.data and len(result.data) > 0:
                return await self._build_user(result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting user by email {email}: {e}")
            raise

    async def get_user_by_login_identifier(self, login: str) -> Optional[User]:
        """Get a user by username or email."""
        user = await self.get_user_by_username(login)
        if user:
            return user

        return await self.get_user_by_email(login)

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("users").select("*").eq("id", user_id).execute()

            if result.data and len(result.data) > 0:
                return await self._build_user(result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {e}")
            raise

    async def update_user_last_login(self, user_id: int) -> bool:
        """Update user's last login timestamp."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("users").update({
                "last_login": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).eq("id", user_id).execute()

            return result.data and len(result.data) > 0

        except Exception as e:
            logger.error(f"Error updating user last login {user_id}: {e}")
            raise

    async def update_user_profile(self, user_id: int, user_data: UserProfileUpdate) -> Optional[User]:
        """Update user profile and notification preference fields.

        Identity fields (``full_name``, ``phone_number``) live on the users
        table while delivery preferences live on
        ``user_notification_preferences``.
        """
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            identity_update: Dict[str, Any] = {}
            if user_data.full_name is not None:
                identity_update["full_name"] = user_data.full_name
            if user_data.phone_number is not None:
                identity_update["phone_number"] = user_data.phone_number

            if identity_update:
                identity_update["updated_at"] = datetime.now().isoformat()
                self.supabase.table("users").update(identity_update).eq("id", user_id).execute()

            touches_preferences = (
                user_data.notification_preference is not None
                or user_data.notification_channels is not None
                or user_data.direct_message_channel is not None
            )
            if touches_preferences:
                await self._upsert_notification_preferences(
                    user_id,
                    notification_preference=(
                        user_data.notification_preference.value
                        if user_data.notification_preference is not None
                        else None
                    ),
                    notification_channels=(
                        self._serialize_notification_channels(user_data.notification_channels)
                        if user_data.notification_channels is not None
                        else None
                    ),
                    direct_message_channel=(
                        user_data.direct_message_channel.value
                        if user_data.direct_message_channel is not None
                        else None
                    ),
                )

            return await self.get_user_by_id(user_id)

        except Exception as e:
            logger.error(f"Error updating user profile {user_id}: {e}")
            raise

    async def update_user_notification_preferences(
        self,
        user_id: int,
        preferences: NotificationPreferencesUpdate,
    ) -> Optional[User]:
        """Update only the notification preference fields for a user."""
        profile_update = UserProfileUpdate(
            notification_preference=preferences.notification_preference,
            notification_channels=preferences.notification_channels,
            direct_message_channel=preferences.direct_message_channel,
        )
        return await self.update_user_profile(user_id, profile_update)

    async def get_active_users(self) -> List[User]:
        """Get all active users."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("users").select("*").eq("is_active", True).execute()
            users: List[User] = []
            for record in result.data or []:
                users.append(await self._build_user(record))
            return users
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            raise

    # Rate Limiting Methods
    async def get_rate_limit_record(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Get rate limit record for an IP address."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("rate_limiting").select("*").eq("ip_address", ip_address).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting rate limit record for IP {ip_address}: {e}")
            raise

    async def create_rate_limit_record(self, ip_address: str) -> Dict[str, Any]:
        """Create a new rate limit record for an IP address."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            now = datetime.now().isoformat()
            data = {
                "ip_address": ip_address,
                "request_count": 1,
                "window_start": now,
                "last_request_time": now
            }

            result = self.supabase.table("rate_limiting").insert(data).execute()

            if result.data:
                return result.data[0]
            else:
                raise Exception("Failed to create rate limit record")

        except Exception as e:
            logger.error(f"Error creating rate limit record for IP {ip_address}: {e}")
            raise

    async def update_rate_limit_record(self, ip_address: str, request_count: int, window_start: datetime, last_request_time: datetime) -> bool:
        """Update an existing rate limit record."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("rate_limiting").update({
                "request_count": request_count,
                "window_start": window_start.isoformat(),
                "last_request_time": last_request_time.isoformat(),
                "updated_at": datetime.now().isoformat()
            }).eq("ip_address", ip_address).execute()

            return result.data and len(result.data) > 0

        except Exception as e:
            logger.error(f"Error updating rate limit record for IP {ip_address}: {e}")
            raise

    async def reset_rate_limit_window(self, ip_address: str) -> bool:
        """Reset the rate limit window for an IP address."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            now = datetime.now()
            result = self.supabase.table("rate_limiting").update({
                "request_count": 1,
                "window_start": now.isoformat(),
                "last_request_time": now.isoformat(),
                "updated_at": now.isoformat()
            }).eq("ip_address", ip_address).execute()

            return result.data and len(result.data) > 0

        except Exception as e:
            logger.error(f"Error resetting rate limit window for IP {ip_address}: {e}")
            raise

    async def cleanup_expired_rate_limits(self, hours_old: int = 24) -> int:
        """Clean up rate limit records older than specified hours."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_old)
            result = self.supabase.table("rate_limiting").delete().lt("created_at", cutoff_time.isoformat()).execute()

            return len(result.data) if result.data else 0

        except Exception as e:
            logger.error(f"Error cleaning up expired rate limits: {e}")
            raise

    # AI Wish Generation Audit Trail Methods
    async def log_ai_wish_request(self, audit_data: AIWishAuditLogCreate) -> AIWishAuditLog:
        """Log an AI wish generation request and response.

        ``audit_data.owner_user_id`` may be ``None`` for anonymous callers; those
        rows remain invisible to the per-user audit log endpoints.
        """
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            data = {
                "owner_user_id": audit_data.owner_user_id,
                "request_id": audit_data.request_id,
                "original_request_id": audit_data.original_request_id,
                "ip_address": audit_data.ip_address,
                "request_data": audit_data.request_data,
                "response_data": audit_data.response_data,
                "ai_service_used": audit_data.ai_service_used
            }

            result = self.supabase.table("ai_wish_audit_logs").insert(data).execute()

            if result.data:
                return AIWishAuditLog(**result.data[0])
            else:
                raise Exception("Failed to create AI wish audit log")

        except Exception as e:
            logger.error(f"Error logging AI wish request: {e}")
            raise

    async def get_ai_wish_audit_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        owner_user_id: int,
    ) -> List[AIWishAuditLog]:
        """Return audit logs for ``owner_user_id``. Anonymous rows are excluded."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = (
                self.supabase.table("ai_wish_audit_logs")
                .select("*")
                .eq("owner_user_id", owner_user_id)
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

            return [AIWishAuditLog(**log) for log in result.data] if result.data else []

        except Exception as e:
            logger.error(f"Error getting AI wish audit logs: {e}")
            raise

    async def get_ai_wish_audit_log_by_request_id(
        self,
        request_id: str,
        *,
        owner_user_id: Optional[int] = None,
    ) -> Optional[AIWishAuditLog]:
        """Get an audit log by request id.

        When ``owner_user_id`` is provided the lookup is scoped to that user
        (used by the per-user audit endpoints). When it's ``None`` the lookup
        is unscoped — this is only used internally by
        ``/api/anniversary-wish/regenerate`` so public callers can regenerate
        their own anonymous wishes by request id.
        """
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            query = (
                self.supabase.table("ai_wish_audit_logs")
                .select("*")
                .eq("request_id", request_id)
            )
            if owner_user_id is not None:
                query = query.eq("owner_user_id", owner_user_id)
            result = query.execute()

            if result.data and len(result.data) > 0:
                return AIWishAuditLog(**result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting AI wish audit log for request {request_id}: {e}")
            raise

    async def get_ai_wish_regeneration_chain(
        self,
        original_request_id: str,
        *,
        owner_user_id: int,
    ) -> List[AIWishAuditLog]:
        """Get regenerations of a request, scoped to ``owner_user_id``."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = (
                self.supabase.table("ai_wish_audit_logs")
                .select("*")
                .eq("original_request_id", original_request_id)
                .eq("owner_user_id", owner_user_id)
                .order("created_at", desc=True)
                .execute()
            )

            return [AIWishAuditLog(**log) for log in result.data] if result.data else []

        except Exception as e:
            logger.error(f"Error getting regeneration chain for request {original_request_id}: {e}")
            raise


# Global database manager instance
db_manager = DatabaseManager()
