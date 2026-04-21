"""
Database models for the Church Anniversary & Birthday Helper app.
"""
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    """Types of events we track."""
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"


class UserRole(str, Enum):
    """Authorization roles for authenticated users."""
    ADMIN = "admin"
    MEMBER = "member"


class AccountType(str, Enum):
    """Supported account types for users."""
    PERSONAL = "personal"
    ORGANIZATION = "organization"


class NotificationPreference(str, Enum):
    """Supported daily delivery behaviors for a user."""
    PERSONAL_REMINDER = "personal_reminder"
    DIRECT_TO_CONTACTS = "direct_to_contacts"


class NotificationChannel(str, Enum):
    """Supported delivery channels."""
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


class PersonBase(BaseModel):
    """Base model for person data."""
    name: str = Field(..., description="Full name of the person")
    event_type: EventType = Field(..., description="Type of event (birthday or anniversary)")
    event_date: str = Field(..., description="Date in MM-DD format (e.g., '03-15')")
    year: Optional[int] = Field(None, description="Year of birth/marriage for age calculation")
    spouse: Optional[str] = Field(None, description="Spouse name for anniversaries")
    phone_number: Optional[str] = Field(None, description="Phone number for WhatsApp/SMS")
    active: bool = Field(True, description="Whether this person is active in the system")


class PersonCreate(PersonBase):
    """Model for creating a new person."""
    pass


class PersonUpdate(BaseModel):
    """Model for updating person data."""
    name: Optional[str] = None
    event_type: Optional[EventType] = None
    event_date: Optional[str] = None
    year: Optional[int] = None
    spouse: Optional[str] = None
    phone_number: Optional[str] = None
    active: Optional[bool] = None


class Person(PersonBase):
    """Complete person model with database fields."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageLog(BaseModel):
    """Model for tracking sent messages."""
    id: int
    person_id: int
    message_content: str
    sent_date: date
    success: bool
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CSVUpload(BaseModel):
    """Model for tracking CSV uploads."""
    id: int
    filename: str
    upload_date: datetime
    records_processed: int
    records_added: int
    records_updated: int
    success: bool
    error_message: Optional[str] = None
    storage_path: Optional[str] = None

    class Config:
        from_attributes = True


def _default_notification_channels() -> List["NotificationChannel"]:
    """Default set of channels for a personal daily reminder."""
    return [NotificationChannel.SMS, NotificationChannel.EMAIL]


class NotificationPreferencesBase(BaseModel):
    """Delivery/reminder configuration owned by a single user.

    These settings live on the dedicated `user_notification_preferences` table
    rather than the `users` table, so identity data stays separate from
    delivery behavior.
    """
    notification_preference: NotificationPreference = Field(
        NotificationPreference.PERSONAL_REMINDER,
        description="Whether the user wants a personal daily digest or direct delivery to contacts",
    )
    notification_channels: List[NotificationChannel] = Field(
        default_factory=_default_notification_channels,
        description="Channels used for personal daily reminders",
    )
    direct_message_channel: NotificationChannel = Field(
        NotificationChannel.SMS,
        description="Channel used when sending celebration messages directly to contacts",
    )


class NotificationPreferencesCreate(NotificationPreferencesBase):
    """Payload used to create a notification-preferences row for a user."""
    user_id: int = Field(..., description="Owner user id")


class NotificationPreferencesUpdate(BaseModel):
    """Partial update payload for a user's notification preferences."""
    notification_preference: Optional[NotificationPreference] = None
    notification_channels: Optional[List[NotificationChannel]] = None
    direct_message_channel: Optional[NotificationChannel] = None


class NotificationPreferences(NotificationPreferencesBase):
    """Complete notification-preferences row with database fields."""
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    """Base model for authenticated user data.

    Delivery preferences (``notification_preference``, ``notification_channels``,
    ``direct_message_channel``) are surfaced here for API convenience but are
    persisted in the dedicated ``user_notification_preferences`` table.
    """
    username: str = Field(..., description="Unique username", min_length=3, max_length=50)
    email: Optional[str] = Field(
        None,
        description="Unique email address",
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    full_name: str = Field(..., description="User's full name", min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, description="User phone number in E.164 format")
    account_type: AccountType = Field(AccountType.PERSONAL, description="Type of account")
    role: UserRole = Field(UserRole.MEMBER, description="Authorization role")
    notification_preference: NotificationPreference = Field(
        NotificationPreference.PERSONAL_REMINDER,
        description="Whether the user wants a personal daily digest or direct delivery to contacts"
    )
    notification_channels: List[NotificationChannel] = Field(
        default_factory=_default_notification_channels,
        description="Channels used for personal daily reminders"
    )
    direct_message_channel: NotificationChannel = Field(
        NotificationChannel.SMS,
        description="Channel used when sending celebration messages directly to contacts"
    )
    is_active: bool = Field(True, description="Whether this user account is active")


class UserCreate(UserBase):
    """Model for creating a new user."""
    password: str = Field(..., description="Plain text password (will be hashed)")


class User(UserBase):
    """Complete user model with database fields."""
    id: int
    password_hash: str = Field(..., description="Hashed password")
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    """Model for login requests."""
    email: str = Field(
        ...,
        description="Email address for login",
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(..., description="Account password")


class LoginResponse(BaseModel):
    """Model for login responses."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: UserBase = Field(..., description="Authenticated user information")


class RegisterRequest(BaseModel):
    """Model for registration requests."""
    full_name: str = Field(..., description="Full name of the registering user", min_length=1, max_length=255)
    username: str = Field(..., description="Unique username", min_length=3, max_length=50)
    email: str = Field(
        ...,
        description="Email address for the account",
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    phone_number: Optional[str] = Field(None, description="Phone number for reminder delivery", max_length=30)
    password: str = Field(..., description="Password for the new account", min_length=8, max_length=128)
    account_type: AccountType = Field(AccountType.PERSONAL, description="Account type requested by the client")
    notification_preference: NotificationPreference = Field(
        NotificationPreference.PERSONAL_REMINDER,
        description="Daily delivery behavior for this user"
    )
    notification_channels: List[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.SMS, NotificationChannel.EMAIL],
        description="Channels used for personal daily reminders"
    )
    direct_message_channel: NotificationChannel = Field(
        NotificationChannel.SMS,
        description="Channel used when sending celebration messages directly to contacts"
    )


class RegisterResponse(BaseModel):
    """Model for registration responses."""
    message: str = Field(..., description="Registration result message")
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: UserBase = Field(..., description="Registered user information")


class UserProfileUpdate(BaseModel):
    """Model for updating a user's profile and notification preferences."""
    full_name: Optional[str] = Field(None, description="User's full name", min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, description="Phone number for reminder delivery", max_length=30)
    notification_preference: Optional[NotificationPreference] = Field(
        None,
        description="Whether the user wants a personal daily digest or direct delivery to contacts"
    )
    notification_channels: Optional[List[NotificationChannel]] = Field(
        None,
        description="Channels used for personal daily reminders"
    )
    direct_message_channel: Optional[NotificationChannel] = Field(
        None,
        description="Channel used when sending celebration messages directly to contacts"
    )


# Rate Limiting Models
class RateLimitRecord(BaseModel):
    """Model for tracking API rate limits."""
    id: int
    ip_address: str = Field(..., description="Client IP address")
    request_count: int = Field(..., description="Number of requests in current window")
    window_start: datetime = Field(..., description="Start time of current rate limit window")
    last_request_time: datetime = Field(..., description="Timestamp of last request")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Anniversary Wish API Models
class AnniversaryType(str, Enum):
    """Types of anniversaries for wish generation."""
    BIRTHDAY = "birthday"
    WORK_ANNIVERSARY = "work-anniversary"
    WEDDING_ANNIVERSARY = "wedding-anniversary"
    PROMOTION = "promotion"
    RETIREMENT = "retirement"
    FRIENDSHIP = "friendship"
    RELATIONSHIP = "relationship"
    MILESTONE = "milestone"
    CUSTOM = "custom"


class ToneType(str, Enum):
    """Tone options for wish generation."""
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    WARM = "warm"
    HUMOROUS = "humorous"
    FORMAL = "formal"


class AnniversaryWishRequest(BaseModel):
    """Model for anniversary wish generation requests."""
    name: str = Field(..., description="Name of the person celebrating the anniversary", min_length=1, max_length=100)
    anniversary_type: AnniversaryType = Field(..., description="Type of anniversary")
    relationship: str = Field(..., description="Your relationship to the person (e.g., 'friend', 'colleague', 'spouse', 'mentor')", min_length=1, max_length=50)
    tone: ToneType = Field(ToneType.WARM, description="Tone of the wish message")
    context: Optional[str] = Field(None, description="Additional context for personalization", max_length=500)


class AnniversaryWishResponse(BaseModel):
    """Model for anniversary wish generation responses."""
    generated_wish: str = Field(..., description="The AI-generated anniversary wish")
    request_id: str = Field(..., description="Unique identifier for this request")
    remaining_requests: int = Field(..., description="Number of requests remaining in current window")
    window_reset_time: Optional[datetime] = Field(None, description="When the rate limit window resets")


class RegenerateWishRequest(BaseModel):
    """Model for regenerating anniversary wishes."""
    request_id: str = Field(..., description="ID of the original request to regenerate")
    additional_context: Optional[str] = Field(None, description="Additional context for regeneration", max_length=500)


class CoordinatorDeliveryTestRequest(BaseModel):
    """Model for sending a test coordinator notification."""
    subject: Optional[str] = Field(None, description="Optional subject override for email delivery", max_length=200)
    message: Optional[str] = Field(None, description="Optional message body override", max_length=4000)


# AI Wish Generation Audit Trail Models
class AIWishAuditLog(BaseModel):
    """Model for tracking AI wish generation requests and responses."""
    id: int
    request_id: str = Field(..., description="Unique identifier for this request")
    original_request_id: Optional[str] = Field(None, description="ID of original request if this is a regeneration")
    ip_address: str = Field(..., description="Client IP address (hashed)")
    request_data: Dict[str, Any] = Field(..., description="JSON data of the original request")
    response_data: Dict[str, Any] = Field(..., description="JSON data of the generated response")
    ai_service_used: str = Field(..., description="AI service used: groq, openai, or fallback")
    created_at: datetime

    class Config:
        from_attributes = True


class AIWishAuditLogCreate(BaseModel):
    """Model for creating new AI wish audit log entries."""
    request_id: str = Field(..., description="Unique identifier for this request")
    original_request_id: Optional[str] = Field(None, description="ID of original request if this is a regeneration")
    ip_address: str = Field(..., description="Client IP address (hashed)")
    request_data: Dict[str, Any] = Field(..., description="JSON data of the original request")
    response_data: Dict[str, Any] = Field(..., description="JSON data of the generated response")
    ai_service_used: str = Field(..., description="AI service used: groq, openai, or fallback")
