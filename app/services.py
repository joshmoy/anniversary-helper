"""
Service layer for business logic and external integrations.
"""
import logging
import pandas as pd
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import re
import random
import io
import tempfile
import smtplib
from email.message import EmailMessage

from groq import Groq
import openai
import requests
from twilio.rest import Client as TwilioClient

from app.database import db_manager
from app.models import PersonCreate, EventType, Person, User, NotificationPreference
from app.config import settings

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages file operations with Supabase Storage."""
    
    def __init__(self):
        """Initialize storage manager with Supabase client."""
        self.bucket_name = settings.supabase_storage_bucket
        
        # Use service role client for storage operations (more permissions)
        from supabase import create_client
        if settings.supabase_service_key:
            self.storage_client = create_client(
                settings.supabase_url, 
                settings.supabase_service_key
            )
        else:
            # Fallback to regular client
            self.storage_client = db_manager.supabase
        
    async def upload_csv_file(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Upload a CSV file to Supabase Storage."""
        try:
            # Generate a unique file path with timestamp
            timestamp = datetime.now().isoformat()
            file_path = f"uploads/{timestamp}_{filename}"
            
            # Upload to Supabase Storage
            response = self.storage_client.storage.from_(self.bucket_name).upload(
                path=file_path,
                file=file_content,
                file_options={"content-type": "text/csv"}
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "file_path": file_path,
                    "url": self.get_public_url(file_path),
                    "message": "File uploaded successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"Upload failed with status {response.status_code}",
                    "details": response.json() if hasattr(response, 'json') else str(response)
                }
                
        except Exception as e:
            logger.error(f"Error uploading file to storage: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_public_url(self, file_path: str) -> str:
        """Get the public URL for a file in Supabase Storage."""
        try:
            response = self.storage_client.storage.from_(self.bucket_name).get_public_url(file_path)
            # In newer versions of supabase-py, get_public_url returns a string directly
            if isinstance(response, str):
                return response
            elif isinstance(response, dict):
                return response.get('publicURL', '')
            else:
                return str(response)
        except Exception as e:
            logger.error(f"Error getting public URL: {e}")
            return ""
    
    async def download_csv_file(self, file_path: str) -> bytes:
        """Download a CSV file from Supabase Storage."""
        try:
            response = self.storage_client.storage.from_(self.bucket_name).download(file_path)
            return response
        except Exception as e:
            logger.error(f"Error downloading file from storage: {e}")
            raise
    
    async def delete_csv_file(self, file_path: str) -> bool:
        """Delete a CSV file from Supabase Storage."""
        try:
            response = self.storage_client.storage.from_(self.bucket_name).remove([file_path])
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting file from storage: {e}")
            return False
    
    async def list_csv_files(self) -> List[Dict]:
        """List all CSV files in the storage bucket."""
        try:
            response = self.storage_client.storage.from_(self.bucket_name).list("uploads/")
            return response if response else []
        except Exception as e:
            logger.error(f"Error listing files from storage: {e}")
            return []


class CSVManager:
    """Handles CSV file processing and data import from Supabase Storage."""

    def __init__(self):
        pass  # No local file handling needed

    def validate_csv_format(self, df: pd.DataFrame) -> List[str]:
        """Validate CSV format and return list of errors."""
        errors = []

        required_columns = ['name', 'type', 'date']
        optional_columns = ['year', 'spouse', 'phone_number']
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
        """Process a CSV file from Supabase Storage and import data to database."""
        try:
            # Download file from Supabase Storage
            file_content = await storage_manager.download_csv_file(file_path)
            # Read CSV from bytes
            df = pd.read_csv(io.BytesIO(file_content))

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
                    phone_number = str(row['phone_number']).strip() if pd.notna(row.get('phone_number')) and row.get('phone_number') != '' else None

                    # Create person data
                    person_data = PersonCreate(
                        name=name,
                        event_type=event_type,
                        event_date=event_date,
                        year=year,
                        spouse=spouse,
                        phone_number=phone_number,
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

            # Log the CSV upload to database
            try:
                await db_manager.log_csv_upload(
                    filename=file_path.split('/')[-1] if '/' in file_path else file_path,
                    records_processed=records_processed,
                    records_added=records_added,
                    records_updated=records_updated,
                    success=True,
                    storage_path=file_path
                )
            except Exception as log_error:
                logger.error(f"Failed to log CSV upload: {log_error}")

            return {
                "success": True,
                "records_processed": records_processed,
                "records_added": records_added,
                "records_updated": records_updated
            }

        except Exception as e:
            logger.error(f"Error processing CSV file: {e}")
            
            # Log the failed upload to database
            try:
                await db_manager.log_csv_upload(
                    filename=file_path.split('/')[-1] if '/' in file_path else file_path,
                    records_processed=0,
                    records_added=0,
                    records_updated=0,
                    success=False,
                    error_message=str(e),
                    storage_path=file_path
                )
            except Exception as log_error:
                logger.error(f"Failed to log CSV upload error: {log_error}")
            
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
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": "You are a Christian pastor writing celebration messages for church members. Your messages should be warm, godly, and include appropriate Bible verses. Return ONLY the message content without any introductory or closing text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )

            message = response.choices[0].message.content.strip()
            return self._clean_ai_message(message)

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
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are a Christian pastor writing celebration messages for church members. Return ONLY the message content without any introductory or closing text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )

            message = response.choices[0].message.content.strip()
            return self._clean_ai_message(message)

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

    def _clean_ai_message(self, message: str) -> str:
        """Clean AI-generated message by removing unwanted introductory and closing text."""
        # Remove common introductory phrases
        intro_patterns = [
            r"Here is a warm, Christian birthday message for [^:]+:",
            r"Here is a warm, Christian anniversary message for [^:]+:",
            r"Here is a Christian birthday message for [^:]+:",
            r"Here is a Christian anniversary message for [^:]+:",
            r"Here's a warm, Christian birthday message for [^:]+:",
            r"Here's a warm, Christian anniversary message for [^:]+:",
            r"Here's a Christian birthday message for [^:]+:",
            r"Here's a Christian anniversary message for [^:]+:",
        ]

        # Remove common closing phrases
        closing_patterns = [
            r"I hope this message meets your requirements[^!]*!?",
            r"Please let me know if you have any further requests[^!]*!?",
            r"I hope this helps[^!]*!?",
            r"Let me know if you need anything else[^!]*!?",
        ]

        import re

        # Clean introductory text
        for pattern in intro_patterns:
            message = re.sub(pattern, "", message, flags=re.IGNORECASE).strip()

        # Clean closing text
        for pattern in closing_patterns:
            message = re.sub(pattern, "", message, flags=re.IGNORECASE).strip()

        # Remove extra whitespace and newlines
        message = re.sub(r'\n\s*\n', '\n', message)  # Remove multiple newlines
        message = re.sub(r'^\s+|\s+$', '', message)  # Remove leading/trailing whitespace

        return message

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


class CoordinatorNotifier:
    """Sends generated celebration messages based on a user's delivery preferences."""

    def __init__(self):
        """Initialize Twilio client."""
        self.client = None

        try:
            if settings.twilio_account_sid and settings.twilio_auth_token:
                self.client = TwilioClient(
                    settings.twilio_account_sid,
                    settings.twilio_auth_token
                )
                logger.info("Twilio client initialized successfully")
            else:
                logger.info("Twilio credentials not configured; SMS and WhatsApp delivery will be unavailable")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")

    def _get_user_channels(self, user: User) -> List[str]:
        """Return enabled personal reminder channels for a user."""
        channels = [channel.value if hasattr(channel, "value") else str(channel) for channel in user.notification_channels]
        unique_channels: List[str] = []
        for channel in channels:
            if channel not in unique_channels:
                unique_channels.append(channel)
        if not unique_channels:
            raise ValueError("User must configure at least one notification channel")
        return unique_channels

    def _resolve_twilio_routing(self, channel: str, recipient: str) -> Dict[str, str]:
        """Resolve Twilio sender/recipient settings for SMS or WhatsApp delivery."""
        to_value = recipient

        if channel == "whatsapp":
            if not settings.whatsapp_from:
                raise ValueError("WHATSAPP_FROM must be set when using WhatsApp delivery")

            if not to_value.startswith("whatsapp:"):
                to_value = f"whatsapp:{to_value}"

            return {"channel": channel, "from": settings.whatsapp_from, "to": to_value}

        if channel == "sms":
            if not settings.sms_from:
                raise ValueError("SMS_FROM must be set when using SMS delivery")

            return {"channel": channel, "from": settings.sms_from, "to": to_value}

        raise ValueError(f"Unsupported Twilio channel: {channel}")

    def _send_via_twilio(self, channel: str, recipient: str, message: str) -> Dict[str, Any]:
        """Send a message through Twilio."""
        routing = self._resolve_twilio_routing(channel, recipient)
        message_instance = self.client.messages.create(
            body=message,
            from_=routing["from"],
            to=routing["to"]
        )

        logger.info(
            "Coordinator message sent successfully via %s. SID: %s",
            routing["channel"],
            message_instance.sid
        )

        return {
            "success": True,
            "channel": routing["channel"],
            "message_sid": message_instance.sid,
            "status": message_instance.status,
        }

    def _send_via_email(self, recipient_email: str, subject: str, message: str) -> Dict[str, Any]:
        """Send a message by email using SMTP."""
        if not settings.smtp_host:
            raise ValueError("SMTP_HOST must be set when using email delivery")
        if not settings.smtp_from_email:
            raise ValueError("SMTP_FROM_EMAIL must be set when using email delivery")

        email_message = EmailMessage()
        email_message["Subject"] = subject
        email_message["From"] = settings.smtp_from_email
        email_message["To"] = recipient_email
        email_message.set_content(message)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(email_message)

        logger.info("Coordinator message sent successfully via email to %s", recipient_email)
        return {
            "success": True,
            "channel": "email",
            "to": recipient_email,
        }

    def _send_via_telegram(self, message: str) -> Dict[str, Any]:
        """Send a message to Telegram using a bot."""
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must be set when using telegram delivery")
        if not settings.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID must be set when using telegram delivery")

        response = requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        logger.info("Coordinator message sent successfully via telegram to %s", settings.telegram_chat_id)
        return {
            "success": True,
            "channel": "telegram",
            "message_id": payload.get("result", {}).get("message_id"),
        }

    def _send_to_channel(self, channel: str, recipient: Optional[str], subject: str, message: str) -> Dict[str, Any]:
        """Send the message to a single channel."""
        if channel in {"sms", "whatsapp"}:
            if not self.client:
                raise ValueError("Twilio client not initialized")
            if not recipient:
                raise ValueError(f"A recipient phone number is required for {channel} delivery")
            return self._send_via_twilio(channel, recipient, message)
        if channel == "email":
            if not recipient:
                raise ValueError("A recipient email is required for email delivery")
            return self._send_via_email(recipient, subject, message)
        if channel == "telegram":
            return self._send_via_telegram(message)
        raise ValueError(f"Unsupported coordinator channel: {channel}")

    async def send_message_to_user(self, user: User, message: str, subject: Optional[str] = None) -> Dict[str, Any]:
        """Send a message to a user's configured personal reminder channels."""
        channels = self._get_user_channels(user)
        if not self.client and any(channel in {"sms", "whatsapp"} for channel in channels):
            return {
                "success": False,
                "error": "Twilio client not initialized"
            }

        try:
            delivery_subject = subject or "Daily celebration message"
            results = []
            failed_channels = []

            for channel in channels:
                recipient = None
                if channel in {"sms", "whatsapp"}:
                    recipient = user.phone_number
                elif channel == "email":
                    recipient = user.email

                try:
                    results.append(self._send_to_channel(channel, recipient, delivery_subject, message))
                except Exception as channel_error:
                    logger.error("Error sending user message via %s for user %s: %s", channel, user.id, channel_error)
                    results.append({
                        "success": False,
                        "channel": channel,
                        "error": str(channel_error),
                    })
                    failed_channels.append(channel)

            successful_channels = [result["channel"] for result in results if result.get("success")]

            return {
                "success": len(successful_channels) > 0,
                "channels": [result["channel"] for result in results],
                "successful_channels": successful_channels,
                "failed_channels": failed_channels,
                "results": results,
            }

        except Exception as e:
            logger.error(f"Error sending coordinator message: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def send_test_message_to_user(self, user: User, message: str, subject: Optional[str] = None) -> Dict[str, Any]:
        """Send a test message to the current user."""
        return await self.send_message_to_user(user, message, subject=subject)

    async def send_message_to_contact(self, person: Person, channel: str, message: str) -> Dict[str, Any]:
        """Send a message directly to a person's configured contact details."""
        try:
            if channel in {"sms", "whatsapp"}:
                if not person.phone_number:
                    raise ValueError(f"{person.name} does not have a phone number configured")
                result = self._send_to_channel(channel, person.phone_number, f"Celebrating {person.name}", message)
            else:
                raise ValueError(f"Direct delivery channel {channel} is not supported for contacts yet")

            await db_manager.log_message(
                person_id=person.id,
                message_content=message,
                sent_date=date.today(),
                success=result["success"],
                error_message=result.get("error")
            )
            return result

        except Exception as e:
            await db_manager.log_message(
                person_id=person.id,
                message_content=message,
                sent_date=date.today(),
                success=False,
                error_message=str(e)
            )
            return {
                "success": False,
                "channel": channel,
                "error": str(e)
            }

    async def send_direct_celebration_message(self, user: User, person: Person) -> Dict[str, Any]:
        """Generate and send a celebration message directly to a contact."""
        try:
            message = await ai_generator.generate_celebration_message(person)
            channel = user.direct_message_channel.value if hasattr(user.direct_message_channel, "value") else str(user.direct_message_channel)
            return await self.send_message_to_contact(person, channel, message)
        except Exception as e:
            logger.error("Error sending direct celebration message for %s: %s", person.name, e)
            return {
                "success": False,
                "error": str(e)
            }

    async def send_daily_celebrations_for_user(self, user: User) -> Dict[str, Any]:
        """Send daily celebrations according to a single user's preference."""
        try:
            celebrations = await date_manager.get_todays_celebrations()
            if not celebrations:
                logger.info("No celebrations today")
                return {
                    "success": True,
                    "message": "No celebrations today",
                    "sent_count": 0
                }

            if user.notification_preference == NotificationPreference.DIRECT_TO_CONTACTS:
                results = []
                for person in celebrations:
                    results.append(await self.send_direct_celebration_message(user, person))

                success_count = sum(1 for result in results if result.get("success"))
                return {
                    "success": success_count > 0,
                    "sent_count": success_count,
                    "failed_count": len(results) - success_count,
                    "errors": [result.get("error", "Unknown error") for result in results if not result.get("success")],
                    "total_celebrations": len(celebrations),
                    "message": "Direct celebration delivery completed",
                    "channels": [user.direct_message_channel.value if hasattr(user.direct_message_channel, "value") else str(user.direct_message_channel)]
                }

            consolidated_message = await self.generate_consolidated_celebration_message(celebrations)
            subject = f"Daily celebration message for {date.today().isoformat()}"
            result = await self.send_message_to_user(user, consolidated_message, subject=subject)

            for person in celebrations:
                await db_manager.log_message(
                    person_id=person.id,
                    message_content=consolidated_message,
                    sent_date=date.today(),
                    success=result["success"],
                    error_message=result.get("error")
                )

            if result["success"]:
                return {
                    "success": True,
                    "sent_count": 1,
                    "failed_count": 0,
                    "errors": [],
                    "total_celebrations": len(celebrations),
                    "message": "Personal daily reminder sent successfully",
                    "channels": result.get("successful_channels", [])
                }

            logger.error(f"Failed to send consolidated message: {result}")
            return {
                "success": False,
                "sent_count": 0,
                "failed_count": len(result.get("failed_channels", [])) or 1,
                "errors": [
                    delivery_result.get("error", "Unknown error")
                    for delivery_result in result.get("results", [])
                    if not delivery_result.get("success")
                ] or ["Unknown error"],
                "total_celebrations": len(celebrations)
            }

        except Exception as e:
            logger.error(f"Error in daily celebrations: {e}")
            return {
                "success": False,
                "error": str(e),
                "sent_count": 0
            }

    async def send_daily_celebrations(self) -> Dict[str, Any]:
        """Run daily celebration delivery for all active users."""
        users = await db_manager.get_active_users()
        if not users:
            return {
                "success": True,
                "message": "No active users configured for reminders",
                "sent_count": 0,
            }

        direct_delivery_users = [
            user for user in users
            if user.notification_preference == NotificationPreference.DIRECT_TO_CONTACTS
        ]
        personal_reminder_users = [
            user for user in users
            if user.notification_preference == NotificationPreference.PERSONAL_REMINDER
        ]

        results = []

        for user in personal_reminder_users:
            results.append({
                "user_id": user.id,
                "username": user.username,
                "result": await self.send_daily_celebrations_for_user(user),
            })

        if direct_delivery_users:
            selected_user = direct_delivery_users[0]
            if len(direct_delivery_users) > 1:
                logger.warning(
                    "Multiple users are configured for direct-to-contacts delivery; using user %s only",
                    selected_user.id
                )
            results.append({
                "user_id": selected_user.id,
                "username": selected_user.username,
                "result": await self.send_daily_celebrations_for_user(selected_user),
            })

        return {
            "success": any(item["result"].get("success") for item in results),
            "sent_count": sum(item["result"].get("sent_count", 0) for item in results),
            "failed_count": sum(item["result"].get("failed_count", 0) for item in results),
            "results": results,
        }

    async def generate_consolidated_celebration_message(self, celebrations: List[Person]) -> str:
        """Generate a single consolidated message for all today's celebrations."""
        try:
            logger.info(f"Generating consolidated message for {len(celebrations)} celebrations")

            # Separate birthdays and anniversaries
            birthdays = [p for p in celebrations if p.event_type == EventType.BIRTHDAY]
            anniversaries = [p for p in celebrations if p.event_type == EventType.ANNIVERSARY]

            logger.info(f"Found {len(birthdays)} birthdays and {len(anniversaries)} anniversaries")

            # Start with greeting
            message_parts = ["Good morning, beloved! 🌅✨"]
            message_parts.append("")  # Empty line

            # Add birthday celebrations
            if birthdays:
                for person in birthdays:
                    phone_text = f" ({person.phone_number})" if person.phone_number else " (insert phone number)"
                    message_parts.append(f"Today is {person.name}'s birthday{phone_text}! 🥳🎉")
                message_parts.append("")  # Empty line

            # Add anniversary celebrations
            if anniversaries:
                for person in anniversaries:
                    phone_text = f" ({person.phone_number})" if person.phone_number else " (insert phone number)"
                    message_parts.append(f"Today is {person.name}'s anniversary{phone_text}! 💕🎊")
                message_parts.append("")  # Empty line

            # Add celebration instructions
            message_parts.append("Please let's celebrate with them via text, WhatsApp call, or WhatsApp message! 📱💝")
            message_parts.append("")
            message_parts.append("You can send your wishes on this platform for 24 hours.")
            message_parts.append("")
            message_parts.append("You are next to be celebrated in Jesus' name, Amen! 🙏")
            message_parts.append("")

            # Add Bible verse
            bible_verses = ai_generator.get_bible_verses()
            selected_verse = random.choice(bible_verses)
            message_parts.append(f'"{selected_verse["verse"]}" - {selected_verse["reference"]}')
            message_parts.append("")

            # Add closing
            message_parts.append("God bless! 🙌")
            message_parts.append("🥳🎉🎈🎁🎊❤️🍰🥧🎵")

            return "\n".join(message_parts)

        except Exception as e:
            logger.error(f"Error generating consolidated message: {e}")
            logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
            # Fallback to detailed message with occasions
            message_parts = ["Good morning, beloved! 🌅✨", ""]

            for person in celebrations:
                occasion = "birthday" if person.event_type == EventType.BIRTHDAY else "anniversary"
                emoji = "🥳🎉" if person.event_type == EventType.BIRTHDAY else "💕🎊"
                phone_text = f" ({person.phone_number})" if person.phone_number else " (insert phone number)"
                message_parts.append(f"Today is {person.name}'s {occasion}{phone_text}! {emoji}")

            message_parts.extend([
                "",
                "Please let's celebrate with them via text, WhatsApp call, or WhatsApp message! 📱�",
                "",
                "You can send your wishes on this platform for 24 hours.",
                "",
                "You are next to be celebrated in Jesus' name, Amen! 🙏",
                "",
                "God bless! 🙌",
                "🥳🎉🎈🎁🎊❤️🍰🥧🎵"
            ])

            return "\n".join(message_parts)


# Global service instances
storage_manager = StorageManager()
csv_manager = CSVManager()
date_manager = DateManager()
ai_generator = AIMessageGenerator()
coordinator_notifier = CoordinatorNotifier()
