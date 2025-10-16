"""
AI-powered anniversary wish generator service.
"""
import logging
import random
import re
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from groq import Groq
import openai

from app.config import settings
from app.models import AnniversaryWishRequest, AnniversaryType, ToneType

logger = logging.getLogger(__name__)


class AIWishGenerator:
    """Generates personalized anniversary wishes using AI."""

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

    def get_anniversary_bible_verses(self) -> List[Dict[str, str]]:
        """Get Bible verses suitable for anniversary celebrations."""
        return [
            {
                "verse": "Love is patient, love is kind. It does not envy, it does not boast, it is not proud.",
                "reference": "1 Corinthians 13:4"
            },
            {
                "verse": "Two are better than one, because they have a good return for their labor.",
                "reference": "Ecclesiastes 4:9"
            },
            {
                "verse": "Therefore what God has joined together, let no one separate.",
                "reference": "Mark 10:9"
            },
            {
                "verse": "Above all, love each other deeply, because love covers over a multitude of sins.",
                "reference": "1 Peter 4:8"
            },
            {
                "verse": "And now these three remain: faith, hope and love. But the greatest of these is love.",
                "reference": "1 Corinthians 13:13"
            },
            {
                "verse": "Many waters cannot quench love; rivers cannot sweep it away.",
                "reference": "Song of Songs 8:7"
            },
            {
                "verse": "Let love and faithfulness never leave you; bind them around your neck, write them on the tablet of your heart.",
                "reference": "Proverbs 3:3"
            },
            {
                "verse": "Be completely humble and gentle; be patient, bearing with one another in love.",
                "reference": "Ephesians 4:2"
            },
            {
                "verse": "The Lord bless you and keep you; the Lord make his face shine on you and be gracious to you.",
                "reference": "Numbers 6:24-25"
            },
            {
                "verse": "For I know the plans I have for you, declares the Lord, plans to prosper you and not to harm you, to give you hope and a future.",
                "reference": "Jeremiah 29:11"
            }
        ]

    def get_relationship_context(self, relationship: str) -> str:
        """Get contextual information based on relationship type."""
        # Convert to lowercase for case-insensitive matching
        relationship_lower = relationship.lower().strip()
        
        # Common relationship mappings
        relationship_contexts = {
            "spouse": "as their loving spouse",
            "husband": "as their loving husband",
            "wife": "as their loving wife",
            "partner": "as their loving partner",
            "parent": "as their parent",
            "mother": "as their mother",
            "father": "as their father",
            "child": "as their child",
            "son": "as their son",
            "daughter": "as their daughter",
            "sibling": "as their sibling",
            "brother": "as their brother",
            "sister": "as their sister",
            "friend": "as their dear friend",
            "colleague": "as their colleague",
            "coworker": "as their coworker",
            "relative": "as their family member",
            "family": "as their family member",
            "mentor": "as their mentor",
            "teacher": "as their teacher",
            "boss": "as their boss",
            "manager": "as their manager",
            "neighbor": "as their neighbor",
            "pastor": "as their pastor",
            "minister": "as their minister"
        }
        
        # Check for exact matches first
        if relationship_lower in relationship_contexts:
            return relationship_contexts[relationship_lower]
        
        # Check for partial matches
        for key, value in relationship_contexts.items():
            if key in relationship_lower or relationship_lower in key:
                return value
        
        # Default fallback - use the relationship as provided
        return f"as their {relationship}"

    def get_anniversary_type_context(self, anniversary_type: AnniversaryType) -> str:
        """Get contextual information based on anniversary type."""
        type_contexts = {
            AnniversaryType.BIRTHDAY: "birthday",
            AnniversaryType.WORK_ANNIVERSARY: "work anniversary",
            AnniversaryType.WEDDING_ANNIVERSARY: "wedding anniversary",
            AnniversaryType.PROMOTION: "promotion celebration",
            AnniversaryType.RETIREMENT: "retirement celebration",
            AnniversaryType.FRIENDSHIP: "friendship anniversary",
            AnniversaryType.RELATIONSHIP: "relationship anniversary",
            AnniversaryType.MILESTONE: "milestone anniversary",
            AnniversaryType.CUSTOM: "special anniversary"
        }
        return type_contexts.get(anniversary_type, "anniversary")

    def get_tone_instructions(self, tone: ToneType) -> str:
        """Get tone-specific instructions for wish generation."""
        tone_instructions = {
            ToneType.PROFESSIONAL: "Use a professional, respectful tone appropriate for workplace relationships. Keep it formal but warm.",
            ToneType.FRIENDLY: "Use a friendly, approachable tone. Be warm and personable while maintaining respect.",
            ToneType.WARM: "Use a warm, heartfelt tone. Express genuine care and affection in your message.",
            ToneType.HUMOROUS: "Use a light, humorous tone with appropriate jokes or playful language. Keep it tasteful and respectful.",
            ToneType.FORMAL: "Use a formal, dignified tone. Be respectful and proper while still being celebratory."
        }
        return tone_instructions.get(tone, "Use a warm, heartfelt tone.")

    async def generate_wish_with_groq(self, request: AnniversaryWishRequest) -> Optional[str]:
        """Generate anniversary wish using Groq API."""
        if not self.groq_client:
            return None

        try:
            relationship_context = self.get_relationship_context(request.relationship)
            anniversary_context = self.get_anniversary_type_context(request.anniversary_type)
            tone_instructions = self.get_tone_instructions(request.tone)
            
            # Build the prompt
            prompt_parts = [
                f"Generate a Christian {anniversary_context} wish for {request.name}.",
                f"Write this {relationship_context}.",
                f"Tone: {tone_instructions}",
            ]
            
            if request.context:
                prompt_parts.append(f"Additional context: {request.context}")
            
            prompt_parts.extend([
                "The wish should:",
                "- Be heartfelt and godly",
                "- Include a relevant Bible verse appropriate for the occasion",
                "- Be appropriate for a Christian celebration",
                "- Be 2-4 sentences long",
                "- Express God's blessings and love",
                "",
                "Format: [Wish Message] - [Bible Verse] ([Reference])"
            ])
            
            prompt = "\n".join(prompt_parts)

            response = self.groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a Christian pastor writing personalized anniversary wishes. Your messages should be warm, godly, and include appropriate Bible verses. Return ONLY the wish content without any introductory or closing text."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )

            message = response.choices[0].message.content.strip()
            return self._clean_ai_message(message)

        except Exception as e:
            logger.error(f"Error generating wish with Groq: {e}")
            return None

    async def generate_wish_with_openai(self, request: AnniversaryWishRequest) -> Optional[str]:
        """Generate anniversary wish using OpenAI API as fallback."""
        if not self.openai_client:
            return None

        try:
            relationship_context = self.get_relationship_context(request.relationship)
            anniversary_context = self.get_anniversary_type_context(request.anniversary_type)
            tone_instructions = self.get_tone_instructions(request.tone)
            
            # Build the prompt
            prompt_parts = [
                f"Generate a Christian {anniversary_context} wish for {request.name}.",
                f"Write this {relationship_context}.",
                f"Tone: {tone_instructions}",
            ]
            
            if request.context:
                prompt_parts.append(f"Additional context: {request.context}")
            
            prompt_parts.extend([
                "The wish should be heartfelt, godly, include a Bible verse, and be appropriate for a Christian celebration.",
                "Keep it to 2-4 sentences. Format: [Wish Message] - [Bible Verse] ([Reference])"
            ])
            
            prompt = "\n".join(prompt_parts)

            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a Christian pastor writing personalized anniversary wishes. Return ONLY the wish content without any introductory or closing text."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )

            message = response.choices[0].message.content.strip()
            return self._clean_ai_message(message)

        except Exception as e:
            logger.error(f"Error generating wish with OpenAI: {e}")
            return None

    def generate_fallback_wish(self, request: AnniversaryWishRequest) -> str:
        """Generate a fallback wish when AI services are unavailable."""
        relationship_context = self.get_relationship_context(request.relationship)
        anniversary_context = self.get_anniversary_type_context(request.anniversary_type)
        
        # Select a random Bible verse
        bible_verses = self.get_anniversary_bible_verses()
        selected_verse = random.choice(bible_verses)

        # Generate base message based on anniversary type
        if request.anniversary_type == AnniversaryType.BIRTHDAY:
            message = f"🎂 Happy Birthday, {request.name}! May God's love and grace shine upon you today and always."
        elif request.anniversary_type == AnniversaryType.PROMOTION:
            message = f"🎉 Congratulations on your promotion, {request.name}! May God continue to bless your career and use your talents for His glory."
        elif request.anniversary_type == AnniversaryType.RETIREMENT:
            message = f"🎊 Congratulations on your retirement, {request.name}! May God bless this new chapter of your life with peace, joy, and new opportunities to serve Him."
        else:
            # For anniversaries, work anniversaries, etc.
            message = f"🎉 Happy {anniversary_context.title()}, {request.name}! May God's love and grace continue to strengthen your bond."

        # Add relationship-specific touch
        relationship_lower = request.relationship.lower().strip()
        if relationship_lower in ["spouse", "husband", "wife", "partner"]:
            message = message.replace("your journey together", "your beautiful marriage")
        elif relationship_lower in ["parent", "mother", "father"]:
            message = message.replace("your bond", "your loving relationship")
        elif relationship_lower in ["friend"]:
            message = message.replace("your bond", "your wonderful friendship")
        elif relationship_lower in ["colleague", "coworker", "boss", "manager"]:
            message = message.replace("your bond", "your professional relationship")

        # Add context if provided
        if request.context:
            message += f" {request.context}"

        return f"{message} - {selected_verse['verse']} ({selected_verse['reference']})"

    def _clean_ai_message(self, message: str) -> str:
        """Clean AI-generated message by removing unwanted introductory and closing text."""
        # Remove common introductory phrases
        intro_patterns = [
            r"Here is a warm, Christian anniversary wish for [^:]+:",
            r"Here's a warm, Christian anniversary wish for [^:]+:",
            r"Here is a Christian anniversary wish for [^:]+:",
            r"Here's a Christian anniversary wish for [^:]+:",
            r"Here is a personalized anniversary wish for [^:]+:",
            r"Here's a personalized anniversary wish for [^:]+:",
        ]

        for pattern in intro_patterns:
            message = re.sub(pattern, "", message, flags=re.IGNORECASE)

        # Remove common closing phrases
        closing_patterns = [
            r"May God bless you both\.",
            r"God bless\.",
            r"Blessings\.",
            r"Congratulations again\.",
        ]

        for pattern in closing_patterns:
            message = re.sub(pattern, "", message, flags=re.IGNORECASE)

        # Clean up extra whitespace and newlines
        message = re.sub(r'\n+', ' ', message)
        message = re.sub(r'\s+', ' ', message)
        message = message.strip()

        return message

    async def generate_anniversary_wish(self, request: AnniversaryWishRequest) -> str:
        """Generate an anniversary wish for the given request."""
        # Try Groq first
        wish = await self.generate_wish_with_groq(request)
        if wish:
            return wish

        # Try OpenAI as fallback
        wish = await self.generate_wish_with_openai(request)
        if wish:
            return wish

        # Use fallback message if AI services are unavailable
        logger.warning("AI services unavailable, using fallback wish generation")
        return self.generate_fallback_wish(request)

    async def regenerate_wish(self, original_request: AnniversaryWishRequest, additional_context: Optional[str] = None) -> str:
        """Regenerate an anniversary wish with additional context."""
        # Create a new request with additional context
        updated_request = AnniversaryWishRequest(
            name=original_request.name,
            anniversary_type=original_request.anniversary_type,
            relationship=original_request.relationship,
            context=original_request.context + f" {additional_context}" if original_request.context and additional_context else additional_context or original_request.context,
            years_together=original_request.years_together
        )

        return await self.generate_anniversary_wish(updated_request)


# Global AI wish generator instance
ai_wish_generator = AIWishGenerator()
