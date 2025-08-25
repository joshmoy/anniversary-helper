"""
Database connection and operations using Supabase.
"""
import logging
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from supabase import create_client, Client
from app.config import settings
from app.models import Person, PersonCreate, PersonUpdate, MessageLog, CSVUpload

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


# Global database manager instance
db_manager = DatabaseManager()
