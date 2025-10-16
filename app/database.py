"""
Database connection and operations using Supabase.
"""
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from supabase import create_client, Client
from app.config import settings
from app.models import Person, PersonCreate, PersonUpdate, MessageLog, CSVUpload, Admin, AdminCreate, RateLimitRecord

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database operations with Supabase."""

    def __init__(self):
        """Initialize Supabase client."""
        try:
            # Only initialize if we have valid settings
            if hasattr(settings, 'supabase_url') and hasattr(settings, 'supabase_key'):
                if settings.supabase_url and settings.supabase_key:
                    self.supabase: Client = create_client(
                        settings.supabase_url,
                        settings.supabase_key
                    )
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
                name VARCHAR(255) NOT NULL,
                event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('birthday', 'anniversary')),
                event_date VARCHAR(5) NOT NULL,
                year INTEGER,
                spouse VARCHAR(255),
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """

            # Create message_logs table
            message_logs_table = """
            CREATE TABLE IF NOT EXISTS message_logs (
                id SERIAL PRIMARY KEY,
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
                filename VARCHAR(255) NOT NULL,
                upload_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                records_processed INTEGER NOT NULL,
                records_added INTEGER NOT NULL,
                records_updated INTEGER NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT
            );
            """

            # Create admins table
            admins_table = """
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_login TIMESTAMP WITH TIME ZONE
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

            # Create index for efficient lookups
            rate_limiting_index = """
            CREATE INDEX IF NOT EXISTS idx_rate_limiting_ip_address ON rate_limiting(ip_address);
            CREATE INDEX IF NOT EXISTS idx_rate_limiting_window_start ON rate_limiting(window_start);
            """

            # Execute table creation (Note: Supabase handles this via SQL editor)
            logger.info("Database tables initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing database tables: {e}")
            raise

    async def create_person(self, person_data: PersonCreate) -> Person:
        """Create a new person in the database."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            data = {
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

    async def get_people_by_date(self, target_date: str) -> List[Person]:
        """Get all active people with events on the specified date (MM-DD format)."""
        try:
            result = self.supabase.table("people").select("*").eq("event_date", target_date).eq("active", True).execute()

            return [Person(**person) for person in result.data]

        except Exception as e:
            logger.error(f"Error getting people by date: {e}")
            raise

    async def get_all_people(self) -> List[Person]:
        """Get all people from the database."""
        try:
            result = self.supabase.table("people").select("*").execute()
            return [Person(**person) for person in result.data]

        except Exception as e:
            logger.error(f"Error getting all people: {e}")
            raise

    async def upsert_person(self, person_data: PersonCreate) -> Person:
        """Insert or update a person based on name and event_type."""
        try:
            # Check if person already exists
            existing = self.supabase.table("people").select("*").eq("name", person_data.name).eq("event_type", person_data.event_type.value).execute()

            if existing.data:
                # Update existing person
                person_id = existing.data[0]["id"]
                update_data = {
                    "event_date": person_data.event_date,
                    "year": person_data.year,
                    "spouse": person_data.spouse,
                    "phone_number": person_data.phone_number,
                    "active": person_data.active,
                    "updated_at": datetime.now().isoformat()
                }

                result = self.supabase.table("people").update(update_data).eq("id", person_id).execute()
                return Person(**result.data[0])
            else:
                # Create new person
                return await self.create_person(person_data)

        except Exception as e:
            logger.error(f"Error upserting person: {e}")
            raise

    async def log_message(self, person_id: int, message_content: str, sent_date: date, success: bool, error_message: Optional[str] = None):
        """Log a sent message."""
        try:
            data = {
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

    async def get_all_message_logs(self):
        """Get all message logs with person information."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            # Get message logs with person information
            result = self.supabase.table("message_logs").select(
                "*, people(name, event_type, phone_number)"
            ).order("created_at", desc=True).execute()

            if result.data:
                # Transform the data to include person info at the top level
                messages = []
                for log in result.data:
                    message_data = {
                        "id": log["id"],
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

    async def get_message_log_by_id(self, message_id: int):
        """Get a specific message log by ID."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("message_logs").select(
                "*, people(name, event_type, phone_number)"
            ).eq("id", message_id).execute()

            if result.data and len(result.data) > 0:
                log = result.data[0]
                return {
                    "id": log["id"],
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

    async def get_person_by_id(self, person_id: int) -> Person:
        """Get a specific person by ID."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("people").select("*").eq("id", person_id).execute()

            if result.data and len(result.data) > 0:
                return Person(**result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting person {person_id}: {e}")
            raise

    async def update_person(self, person_id: int, person_data: PersonUpdate) -> Person:
        """Update a person's information."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            # Build update data from non-None fields
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

                # Perform the update
                update_result = self.supabase.table("people").update(update_data).eq("id", person_id).execute()
                
                # Fetch the updated record
                if update_result.data:
                    fetch_result = self.supabase.table("people").select("*").eq("id", person_id).execute()
                    if fetch_result.data and len(fetch_result.data) > 0:
                        return Person(**fetch_result.data[0])

            return None

        except Exception as e:
            logger.error(f"Error updating person {person_id}: {e}")
            raise

    async def delete_person(self, person_id: int) -> bool:
        """Soft delete a person by setting active=False."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("people").update({
                "active": False,
                "updated_at": datetime.now().isoformat()
            }).eq("id", person_id).execute()

            return result.data and len(result.data) > 0

        except Exception as e:
            logger.error(f"Error deleting person {person_id}: {e}")
            raise

    async def log_csv_upload(self, filename: str, records_processed: int, records_added: int, 
                            records_updated: int, success: bool, error_message: Optional[str] = None, 
                            storage_path: Optional[str] = None) -> None:
        """Log a CSV upload operation."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            data = {
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

    async def get_csv_upload_history(self) -> List[Dict[str, Any]]:
        """Get all CSV upload history."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("csv_uploads").select("*").order("upload_date", desc=True).execute()
            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error getting CSV upload history: {e}")
            raise

    # Admin Management Methods

    async def create_admin(self, admin_data: AdminCreate, password_hash: str) -> Admin:
        """Create a new admin user."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            data = {
                "username": admin_data.username,
                "password_hash": password_hash,
                "is_active": admin_data.is_active
            }

            result = self.supabase.table("admins").insert(data).execute()

            if result.data:
                return Admin(**result.data[0])
            else:
                raise Exception("Failed to create admin")

        except Exception as e:
            logger.error(f"Error creating admin: {e}")
            raise

    async def get_admin_by_username(self, username: str) -> Optional[Admin]:
        """Get an admin by username."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("admins").select("*").eq("username", username).execute()

            if result.data and len(result.data) > 0:
                return Admin(**result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting admin by username {username}: {e}")
            raise

    async def get_admin_by_id(self, admin_id: int) -> Optional[Admin]:
        """Get an admin by ID."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("admins").select("*").eq("id", admin_id).execute()

            if result.data and len(result.data) > 0:
                return Admin(**result.data[0])
            return None

        except Exception as e:
            logger.error(f"Error getting admin by ID {admin_id}: {e}")
            raise

    async def update_admin_last_login(self, admin_id: int) -> bool:
        """Update admin's last login timestamp."""
        if not self.supabase:
            raise Exception("Database not initialized")

        try:
            result = self.supabase.table("admins").update({
                "last_login": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).eq("id", admin_id).execute()

            return result.data and len(result.data) > 0

        except Exception as e:
            logger.error(f"Error updating admin last login {admin_id}: {e}")
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




# Global database manager instance
db_manager = DatabaseManager()
