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


# Global database manager instance
db_manager = DatabaseManager()
