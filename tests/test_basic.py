"""
Basic tests for the Church Anniversary & Birthday Helper application.
"""
import pytest
from datetime import date
from app.models import PersonCreate, EventType
from app.services import DateManager, AIMessageGenerator


class TestDateManager:
    """Test date-related functionality."""

    def test_get_today_date_string(self):
        """Test getting today's date in MM-DD format."""
        date_manager = DateManager()
        today_string = date_manager.get_today_date_string()

        # Should be in MM-DD format
        assert len(today_string) == 5
        assert today_string[2] == '-'

        # Should match today's date
        today = date.today()
        expected = today.strftime("%m-%d")
        assert today_string == expected

    def test_get_date_string(self):
        """Test converting date to MM-DD format."""
        date_manager = DateManager()
        test_date = date(2024, 3, 15)
        date_string = date_manager.get_date_string(test_date)

        assert date_string == "03-15"

    def test_calculate_age_or_years(self):
        """Test age/years calculation."""
        # Create a person with birth year
        person_data = {
            "id": 1,
            "name": "Test Person",
            "event_type": EventType.BIRTHDAY,
            "event_date": "03-15",
            "year": 1990,
            "spouse": None,
            "active": True,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }

        from app.models import Person
        person = Person(**person_data)

        age = DateManager.calculate_age_or_years(person)
        current_year = date.today().year
        expected_age = current_year - 1990

        assert age == expected_age


class TestAIMessageGenerator:
    """Test AI message generation functionality."""

    def test_get_bible_verses(self):
        """Test that Bible verses are available."""
        ai_generator = AIMessageGenerator()
        verses = ai_generator.get_bible_verses()

        assert len(verses) > 0
        assert all("verse" in v and "reference" in v for v in verses)

    def test_generate_fallback_message_birthday(self):
        """Test fallback message generation for birthdays."""
        ai_generator = AIMessageGenerator()

        celebration_info = {
            "name": "John Doe",
            "type": "birthday",
            "age_or_years": 30
        }

        message = ai_generator.generate_fallback_message(celebration_info)

        assert "John Doe" in message
        assert "Birthday" in message or "birthday" in message
        assert "30" in message
        assert "(" in message  # Should contain Bible verse reference

    def test_generate_fallback_message_anniversary(self):
        """Test fallback message generation for anniversaries."""
        ai_generator = AIMessageGenerator()

        celebration_info = {
            "name": "John and Jane Doe",
            "type": "anniversary",
            "age_or_years": 10
        }

        message = ai_generator.generate_fallback_message(celebration_info)

        assert "John and Jane Doe" in message
        assert "Anniversary" in message or "anniversary" in message
        assert "10" in message
        assert "(" in message  # Should contain Bible verse reference


class TestPersonModel:
    """Test person data models."""

    def test_person_create_birthday(self):
        """Test creating a birthday person."""
        person_data = PersonCreate(
            name="Test Person",
            event_type=EventType.BIRTHDAY,
            event_date="03-15",
            year=1990,
            spouse=None,
            active=True
        )

        assert person_data.name == "Test Person"
        assert person_data.event_type == EventType.BIRTHDAY
        assert person_data.event_date == "03-15"
        assert person_data.year == 1990
        assert person_data.spouse is None
        assert person_data.active is True

    def test_person_create_anniversary(self):
        """Test creating an anniversary person."""
        person_data = PersonCreate(
            name="John and Jane Doe",
            event_type=EventType.ANNIVERSARY,
            event_date="06-20",
            year=2010,
            spouse="Jane Doe",
            active=True
        )

        assert person_data.name == "John and Jane Doe"
        assert person_data.event_type == EventType.ANNIVERSARY
        assert person_data.event_date == "06-20"
        assert person_data.year == 2010
        assert person_data.spouse == "Jane Doe"
        assert person_data.active is True


if __name__ == "__main__":
    pytest.main([__file__])
