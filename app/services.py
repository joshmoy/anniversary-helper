"""
Service layer for business logic and external integrations.
"""
import logging
import pandas as pd
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from pathlib import Path
import re
import random

from groq import Groq
import openai
from twilio.rest import Client as TwilioClient

from app.database import db_manager
from app.models import PersonCreate, EventType, Person
from app.config import settings

logger = logging.getLogger(__name__)


class CSVManager:
    """Handles CSV file processing and data import."""

    def __init__(self):
        self.upload_path = Path(settings.csv_upload_path)
        self.upload_path.mkdir(exist_ok=True)

    def validate_csv_format(self, df: pd.DataFrame) -> List[str]:
        """Validate CSV format and return list of errors."""
        errors = []

        required_columns = ['name', 'type', 'date']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            errors.append(f"Missing required columns: {', '.join(missing_columns)}")

        # Validate date format (MM-DD)
        if 'date' in df.columns:
            date_pattern = re.compile(r'^\d{2}-\d{2}$')
            invalid_dates = df[~df['date'].astype(str).str.match(date_pattern, na=False)]
            if not invalid_dates.empty:
                errors.append(f"Invalid date format in rows: {invalid_dates.index.tolist()}. Expected MM-DD format.")

        # Validate event type
        if 'type' in df.columns:
            valid_types = ['birthday', 'anniversary']
            invalid_types = df[~df['type'].isin(valid_types)]
            if not invalid_types.empty:
                errors.append(f"Invalid event types in rows: {invalid_types.index.tolist()}. Must be 'birthday' or 'anniversary'.")

        return errors

    async def process_csv_file(self, file_path: str) -> Dict[str, Any]:
        """Process a CSV file and import data to database."""
        try:
            # Read CSV file
            df = pd.read_csv(file_path)

            # Validate format
            validation_errors = self.validate_csv_format(df)
            if validation_errors:
                return {
                    "success": False,
                    "error": "CSV validation failed: " + "; ".join(validation_errors),
                    "records_processed": 0,
                    "records_added": 0,
                    "records_updated": 0
                }

            records_processed = len(df)
            records_added = 0
            records_updated = 0

            # Process each row
            for index, row in df.iterrows():
                try:
                    # Clean and prepare data
                    name = str(row['name']).strip()
                    event_type = EventType(row['type'].lower().strip())
                    event_date = str(row['date']).strip()
                    year = int(row['year']) if pd.notna(row.get('year')) and row.get('year') != '' else None
                    spouse = str(row['spouse']).strip() if pd.notna(row.get('spouse')) and row.get('spouse') != '' else None

                    # Create person data
                    person_data = PersonCreate(
                        name=name,
                        event_type=event_type,
                        event_date=event_date,
                        year=year,
                        spouse=spouse,
                        active=True
                    )

                    # Check if this is an update or new record
                    existing_people = await db_manager.get_all_people()
                    existing_person = next(
                        (p for p in existing_people if p.name == name and p.event_type == event_type),
                        None
                    )

                    # Upsert person
                    await db_manager.upsert_person(person_data)

                    if existing_person:
                        records_updated += 1
                    else:
                        records_added += 1

                except Exception as e:
                    logger.error(f"Error processing row {index}: {e}")
                    continue

            return {
                "success": True,
                "records_processed": records_processed,
                "records_added": records_added,
                "records_updated": records_updated
            }

        except Exception as e:
            logger.error(f"Error processing CSV file: {e}")
            return {
                "success": False,
                "error": str(e),
                "records_processed": 0,
                "records_added": 0,
                "records_updated": 0
            }


class DateManager:
    """Handles date-related operations for birthday and anniversary detection."""

    @staticmethod
    def get_today_date_string() -> str:
        """Get today's date in MM-DD format."""
        today = date.today()
        return today.strftime("%m-%d")

    @staticmethod
    def get_date_string(target_date: date) -> str:
        """Convert a date object to MM-DD format."""
        return target_date.strftime("%m-%d")

    async def get_todays_celebrations(self) -> List[Person]:
        """Get all people who have birthdays or anniversaries today."""
        today_string = self.get_today_date_string()
        return await db_manager.get_people_by_date(today_string)

    async def get_celebrations_for_date(self, target_date: date) -> List[Person]:
        """Get all people who have birthdays or anniversaries on a specific date."""
        date_string = self.get_date_string(target_date)
        return await db_manager.get_people_by_date(date_string)

    @staticmethod
    def calculate_age_or_years(person: Person) -> Optional[int]:
        """Calculate age for birthdays or years married for anniversaries."""
        if not person.year:
            return None

        current_year = date.today().year
        return current_year - person.year

    @staticmethod
    def format_celebration_info(person: Person) -> Dict[str, Any]:
        """Format celebration information for message generation."""
        age_or_years = DateManager.calculate_age_or_years(person)

        celebration_info = {
            "name": person.name,
            "type": person.event_type.value,
            "date": person.event_date,
            "spouse": person.spouse,
            "age_or_years": age_or_years
        }

        if person.event_type == EventType.BIRTHDAY:
            celebration_info["age"] = age_or_years
            celebration_info["celebration_text"] = f"{person.name}'s birthday"
            if age_or_years:
                celebration_info["celebration_text"] += f" (turning {age_or_years})"
        else:  # anniversary
            celebration_info["years_married"] = age_or_years
            celebration_info["celebration_text"] = f"{person.name}'s anniversary"
            if age_or_years:
                celebration_info["celebration_text"] += f" ({age_or_years} years)"

        return celebration_info


class AIMessageGenerator:
    """Generates Christian-themed celebration messages using AI."""

    def __init__(self):
        """Initialize AI clients."""
        self.groq_client = None
        self.openai_client = None

        # Initialize Groq client
        if settings.groq_api_key:
            try:
                self.groq_client = Groq(api_key=settings.groq_api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client: {e}")

        # Initialize OpenAI client as fallback
        if settings.openai_api_key:
            try:
                self.openai_client = openai.OpenAI(api_key=settings.openai_api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")

    def get_bible_verses(self) -> List[Dict[str, str]]:
        """Get a collection of Bible verses suitable for celebrations."""
        return [
            {
                "verse": "For I know the plans I have for you, declares the Lord, plans to prosper you and not to harm you, to give you hope and a future.",
                "reference": "Jeremiah 29:11"
            },
            {
                "verse": "The Lord bless you and keep you; the Lord make his face shine on you and be gracious to you.",
                "reference": "Numbers 6:24-25"
            },
            {
                "verse": "This is the day the Lord has made; let us rejoice and be glad in it.",
                "reference": "Psalm 118:24"
            },
            {
                "verse": "Every good and perfect gift is from above, coming down from the Father of the heavenly lights.",
                "reference": "James 1:17"
            },
            {
                "verse": "The Lord your God is with you, the Mighty Warrior who saves. He will take great delight in you; in his love he will no longer rebuke you, but will rejoice over you with singing.",
                "reference": "Zephaniah 3:17"
            },
            {
                "verse": "Love is patient, love is kind. It does not envy, it does not boast, it is not proud.",
                "reference": "1 Corinthians 13:4"
            },
            {
                "verse": "Two are better than one, because they have a good return for their labor.",
                "reference": "Ecclesiastes 4:9"
            },
            {
                "verse": "Above all else, guard your heart, for everything you do flows from it.",
                "reference": "Proverbs 4:23"
            },
            {
                "verse": "Delight yourself in the Lord, and he will give you the desires of your heart.",
                "reference": "Psalm 37:4"
            },
            {
                "verse": "And we know that in all things God works for the good of those who love him.",
                "reference": "Romans 8:28"
            }
        ]

    async def generate_message_with_groq(self, celebration_info: Dict[str, Any]) -> Optional[str]:
        """Generate message using Groq API."""
        if not self.groq_client:
            return None

        try:
            event_type = celebration_info["type"]
            name = celebration_info["name"]
            age_or_years = celebration_info.get("age_or_years")

            # Create prompt based on event type
            if event_type == "birthday":
                prompt = f"""
                Generate a warm, Christian birthday message for {name}.
                {"They are turning " + str(age_or_years) + " years old. " if age_or_years else ""}
                The message should:
                - Be heartfelt and godly
                - Include a relevant Bible verse
                - Be appropriate for a church group
                - Be 2-3 sentences long
                - Express God's blessings and love

                Format: [Message] - [Bible Verse] ([Reference])
                """
            else:  # anniversary
                prompt = f"""
                Generate a warm, Christian anniversary message for {name}.
                {"They are celebrating " + str(age_or_years) + " years of marriage. " if age_or_years else ""}
                The message should:
                - Be heartfelt and godly
                - Include a relevant Bible verse about love or marriage
                - Be appropriate for a church group
                - Be 2-3 sentences long
                - Celebrate their union and God's blessing on their marriage

                Format: [Message] - [Bible Verse] ([Reference])
                """

            response = self.groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are a Christian pastor writing celebration messages for church members. Your messages should be warm, godly, and include appropriate Bible verses."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating message with Groq: {e}")
            return None

    async def generate_message_with_openai(self, celebration_info: Dict[str, Any]) -> Optional[str]:
        """Generate message using OpenAI API as fallback."""
        if not self.openai_client:
            return None

        try:
            event_type = celebration_info["type"]
            name = celebration_info["name"]
            age_or_years = celebration_info.get("age_or_years")

            # Create prompt based on event type
            if event_type == "birthday":
                prompt = f"""
                Generate a warm, Christian birthday message for {name}.
                {"They are turning " + str(age_or_years) + " years old. " if age_or_years else ""}
                The message should be heartfelt, godly, include a Bible verse, and be appropriate for a church group.
                Keep it to 2-3 sentences. Format: [Message] - [Bible Verse] ([Reference])
                """
            else:  # anniversary
                prompt = f"""
                Generate a warm, Christian anniversary message for {name}.
                {"They are celebrating " + str(age_or_years) + " years of marriage. " if age_or_years else ""}
                The message should celebrate their union, include a Bible verse about love/marriage, and be appropriate for a church group.
                Keep it to 2-3 sentences. Format: [Message] - [Bible Verse] ([Reference])
                """

            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a Christian pastor writing celebration messages for church members."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating message with OpenAI: {e}")
            return None

    def generate_fallback_message(self, celebration_info: Dict[str, Any]) -> str:
        """Generate a fallback message when AI services are unavailable."""
        event_type = celebration_info["type"]
        name = celebration_info["name"]
        age_or_years = celebration_info.get("age_or_years")

        # Select a random Bible verse
        bible_verses = self.get_bible_verses()
        selected_verse = random.choice(bible_verses)

        if event_type == "birthday":
            if age_or_years:
                message = f"🎉 Happy {age_or_years}th Birthday, {name}! May God continue to bless you abundantly in this new year of life."
            else:
                message = f"🎉 Happy Birthday, {name}! May God's love and grace shine upon you today and always."
        else:  # anniversary
            if age_or_years:
                message = f"💕 Congratulations on {age_or_years} wonderful years of marriage, {name}! May God continue to bless your union."
            else:
                message = f"💕 Happy Anniversary, {name}! May God's love continue to strengthen your marriage."

        return f"{message} - {selected_verse['verse']} ({selected_verse['reference']})"

    async def generate_celebration_message(self, person: Person) -> str:
        """Generate a celebration message for a person."""
        celebration_info = DateManager.format_celebration_info(person)

        # Try Groq first
        message = await self.generate_message_with_groq(celebration_info)
        if message:
            return message

        # Try OpenAI as fallback
        message = await self.generate_message_with_openai(celebration_info)
        if message:
            return message

        # Use fallback message
        logger.warning("AI services unavailable, using fallback message")
        return self.generate_fallback_message(celebration_info)


class WhatsAppMessenger:
    """Handles WhatsApp messaging via Twilio."""

    def __init__(self):
        """Initialize Twilio client."""
        self.client = None

        try:
            self.client = TwilioClient(
                settings.twilio_account_sid,
                settings.twilio_auth_token
            )
            logger.info("Twilio client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")

    async def send_message(self, message: str) -> Dict[str, Any]:
        """Send a message to the configured WhatsApp group."""
        if not self.client:
            return {
                "success": False,
                "error": "Twilio client not initialized"
            }

        try:
            message_instance = self.client.messages.create(
                body=message,
                from_=settings.whatsapp_from,
                to=settings.whatsapp_to
            )

            logger.info(f"WhatsApp message sent successfully. SID: {message_instance.sid}")

            return {
                "success": True,
                "message_sid": message_instance.sid,
                "status": message_instance.status
            }

        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def send_celebration_message(self, person: Person) -> Dict[str, Any]:
        """Generate and send a celebration message for a person."""
        try:
            # Generate the message
            message = await ai_generator.generate_celebration_message(person)

            # Send the message
            result = await self.send_message(message)

            # Log the message attempt
            await db_manager.log_message(
                person_id=person.id,
                message_content=message,
                sent_date=date.today(),
                success=result["success"],
                error_message=result.get("error")
            )

            return result

        except Exception as e:
            logger.error(f"Error sending celebration message for {person.name}: {e}")

            # Log the failed attempt
            await db_manager.log_message(
                person_id=person.id,
                message_content="",
                sent_date=date.today(),
                success=False,
                error_message=str(e)
            )

            return {
                "success": False,
                "error": str(e)
            }

    async def send_daily_celebrations(self) -> Dict[str, Any]:
        """Send celebration messages for all people with events today."""
        try:
            # Get today's celebrations
            celebrations = await date_manager.get_todays_celebrations()

            if not celebrations:
                logger.info("No celebrations today")
                return {
                    "success": True,
                    "message": "No celebrations today",
                    "sent_count": 0
                }

            sent_count = 0
            failed_count = 0
            errors = []

            # Send message for each celebration
            for person in celebrations:
                result = await self.send_celebration_message(person)

                if result["success"]:
                    sent_count += 1
                    logger.info(f"Sent celebration message for {person.name}")
                else:
                    failed_count += 1
                    errors.append(f"{person.name}: {result.get('error', 'Unknown error')}")
                    logger.error(f"Failed to send message for {person.name}: {result.get('error')}")

            return {
                "success": failed_count == 0,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "errors": errors,
                "total_celebrations": len(celebrations)
            }

        except Exception as e:
            logger.error(f"Error in daily celebrations: {e}")
            return {
                "success": False,
                "error": str(e),
                "sent_count": 0
            }


# Global service instances
csv_manager = CSVManager()
date_manager = DateManager()
ai_generator = AIMessageGenerator()
whatsapp_messenger = WhatsAppMessenger()
