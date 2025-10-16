"""
Database models for the Church Anniversary & Birthday Helper app.
"""
from datetime import datetime, date
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    """Types of events we track."""
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"


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


class AdminBase(BaseModel):
    """Base model for admin data."""
    username: str = Field(..., description="Admin username")
    is_active: bool = Field(True, description="Whether this admin account is active")


class AdminCreate(AdminBase):
    """Model for creating a new admin."""
    password: str = Field(..., description="Plain text password (will be hashed)")


class Admin(AdminBase):
    """Complete admin model with database fields."""
    id: int
    password_hash: str = Field(..., description="Hashed password")
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    """Model for login requests."""
    username: str = Field(..., description="Admin username")
    password: str = Field(..., description="Admin password")


class LoginResponse(BaseModel):
    """Model for login responses."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    admin: AdminBase = Field(..., description="Admin user information")


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
