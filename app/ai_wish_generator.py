"""
AI-powered anniversary wish generator service.
"""
import logging
import random
import re
import uuid
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from groq import Groq
import openai

from app.config import settings
from app.models import AnniversaryWishRequest, AnniversaryType, ToneType, AIWishAuditLogCreate
from app.database import db_manager

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

    def _hash_ip_address(self, ip_address: str) -> str:
        """Hash IP address for privacy while maintaining uniqueness."""
        return hashlib.sha256(ip_address.encode()).hexdigest()[:16]

    async def _log_audit_trail(self, request_id: str, original_request_id: Optional[str], 
                              ip_address: str, request: AnniversaryWishRequest, 
                              response: str, ai_service_used: str):
        """Log audit trail for AI wish generation."""
        try:
            # Hash IP address for privacy
            hashed_ip = self._hash_ip_address(ip_address)
            
            # Prepare audit data
            audit_data = AIWishAuditLogCreate(
                request_id=request_id,
                original_request_id=original_request_id,
                ip_address=hashed_ip,
                request_data=request.dict(),
                response_data={"generated_wish": response},
                ai_service_used=ai_service_used
            )
            
            # Log to database
            await db_manager.log_ai_wish_request(audit_data)
            logger.info(f"Audit trail logged for request {request_id}")
            
        except Exception as e:
            logger.error(f"Failed to log audit trail for request {request_id}: {e}")
            # Don't raise exception - audit logging failure shouldn't break the main flow

    def get_inspirational_lines(self) -> List[str]:
        """Short inspirational lines you can optionally append to a wish."""
        return [
        "Here’s to many more moments worth celebrating.",
        "Wishing you continued joy, growth, and laughter together.",
        "May the years ahead be full of memorable adventures.",
        "Cheers to milestones behind you and the ones still to come.",
        "Your dedication and care for each other truly shine.",
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
                f"Generate a {anniversary_context} wish for {request.name}.",
                f"Write this {relationship_context}.",
                f"Tone: {tone_instructions}",
            ]
            
            if request.context:
                prompt_parts.append(f"Additional context: {request.context}")
            
            prompt_parts.extend([
                "The wish should:",
                "- Be heartfelt and genuine",
                "- Be appropriate for the occasion",
                "- Be 2-4 sentences long",
                "Format: [Wish Message]"
            ])
            
            prompt = "\n".join(prompt_parts)

            response = self.groq_client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You write personalized anniversary wishes. Your messages should be warm and appropriate for the occasion. Return ONLY the wish content without any introductory or closing text."
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
                f"Generate a {anniversary_context} wish for {request.name}.",
                f"Write this {relationship_context}.",
                f"Tone: {tone_instructions}",
            ]
            
            if request.context:
                prompt_parts.append(f"Additional context: {request.context}")
            
            prompt_parts.extend([
                "The wish should be heartfelt, and be appropriate for the occasion.",
                "Keep it to 2-4 sentences. Format: [Wish Message]"
            ])
            
            prompt = "\n".join(prompt_parts)

            response = self.openai_client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You write personalized anniversary wishes. Return ONLY the wish content without any introductory or closing text."
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
        
        # Generate base message based on anniversary type
        # Build a simple, tasteful, non‑religious message per type
        if request.anniversary_type == AnniversaryType.BIRTHDAY:
            base = f"🎂 Happy Birthday, {request.name}! Wishing you a year filled with good health, happiness, and moments that make you smile."
        elif request.anniversary_type == AnniversaryType.PROMOTION:
            base = f"🎉 Congratulations on your promotion, {request.name}! Your hard work and dedication truly stand out—here's to new challenges and continued success."
        elif request.anniversary_type == AnniversaryType.RETIREMENT:
            base = f"🎊 Congratulations on your retirement, {request.name}! May this new chapter bring you relaxation, discovery, and time for everything you enjoy."
        elif request.anniversary_type in {AnniversaryType.WEDDING_ANNIVERSARY, AnniversaryType.RELATIONSHIP, AnniversaryType.FRIENDSHIP, AnniversaryType.MILESTONE, AnniversaryType.CUSTOM}:
            base = f"🎉 Happy {anniversary_context.title()}, {request.name}! Cheers to all the moments ahead."
        elif request.anniversary_type == AnniversaryType.WORK_ANNIVERSARY:
            base = f"🎉 Happy work anniversary, {request.name}! Thank you for your contributions and collaboration—here's to another year of impact."
        else:
            base = f"🎉 Happy {anniversary_context.title()}, {request.name}! Wishing you continued joy and meaningful moments."

        # Add a random inspirational line
        inspirational_line = random.choice(self.get_inspirational_lines())
        message = f"{base} {inspirational_line}"

        return message

    def _clean_ai_message(self, message: str) -> str:
        """Clean AI‑generated message by removing boilerplate."""
        intro_patterns = [
        r"here(?:'| i)s (?:a|one) (?:warm|personal(?:ized)?) anniversary wish for [^:]+:\s*",
        r"here(?:'| i)s (?:a|one) (?:non\-religious )?anniversary wish:\s*",
        ]
        
        for pattern in intro_patterns:
            message = re.sub(pattern, "", message, flags=re.IGNORECASE).strip()


        closing_patterns = [
        r"congratulations again\.?$",
        r"best wishes\.?$",
        r"cheers\.?$",
        ]
        for pattern in closing_patterns:
            message = re.sub(pattern, "", message, flags=re.IGNORECASE).strip()


        message = re.sub(r"\n+", " ", message)
        message = re.sub(r"\s+", " ", message)
        
        return message.strip()

    async def generate_anniversary_wish(self, request: AnniversaryWishRequest, 
                                       request_id: str, ip_address: str, 
                                       original_request_id: Optional[str] = None) -> str:
        """Generate an anniversary wish for the given request."""
        ai_service_used = "unknown"
        
        # Try Groq first
        wish = await self.generate_wish_with_groq(request)
        if wish:
            ai_service_used = "groq"
            # Log audit trail
            await self._log_audit_trail(request_id, original_request_id, ip_address, request, wish, ai_service_used)
            return wish

        # Try OpenAI as fallback
        wish = await self.generate_wish_with_openai(request)
        if wish:
            ai_service_used = "openai"
            # Log audit trail
            await self._log_audit_trail(request_id, original_request_id, ip_address, request, wish, ai_service_used)
            return wish

        # Use fallback message if AI services are unavailable
        logger.warning("AI services unavailable, using fallback wish generation")
        wish = self.generate_fallback_wish(request)
        ai_service_used = "fallback"
        # Log audit trail
        await self._log_audit_trail(request_id, original_request_id, ip_address, request, wish, ai_service_used)
        return wish

    async def regenerate_wish(self, original_request: AnniversaryWishRequest, 
                             original_request_id: str, new_request_id: str, 
                             ip_address: str, additional_context: Optional[str] = None) -> str:
        """Regenerate an anniversary wish with additional context."""
        # Create a new request with additional context
        updated_request = AnniversaryWishRequest(
            name=original_request.name,
            anniversary_type=original_request.anniversary_type,
            relationship=original_request.relationship,
            tone=original_request.tone,
            context=original_request.context + f" {additional_context}" if original_request.context and additional_context else additional_context or original_request.context,
        )

        return await self.generate_anniversary_wish(updated_request, new_request_id, ip_address, original_request_id)


# Global AI wish generator instance
ai_wish_generator = AIWishGenerator()
