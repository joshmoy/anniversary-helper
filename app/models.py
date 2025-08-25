"""
Database models for the Church Anniversary & Birthday Helper app.
"""
from datetime import datetime, date
from typing import Optional
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

    class Config:
        from_attributes = True
