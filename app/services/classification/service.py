import asyncio
from typing import Dict, Optional
import httpx
from .models import ClassificationResult, MainCategory, HumanAttentionCategory, Priority
from ...utils.logger import get_logger
import json
from .prompts import get_system_prompt, get_classification_rules
import langdetect
import time

logger = get_logger(__name__)

class ClassificationService:
    def __init__(self, model_name: str = "llama3.1:8b-instruct-q4_0"):
        self.model_name = model_name
        self.ollama_url = "http://localhost:11434/api/generate"
        self._client: Optional[httpx.AsyncClient] = None
        self._max_retries = 3
        self._retry_delay = 2  # seconds
        
    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)  # Increased timeout
            
        # Verify Ollama service is running
        try:
            response = await self._client.get("http://localhost:11434/api/tags")
            if response.status_code != 200:
                raise ConnectionError("Ollama service is not responding correctly")
        except Exception as e:
            logger.error(f"Failed to connect to Ollama service: {str(e)}")
            logger.info("Please ensure Ollama is running with: ollama serve")
            raise

    async def _retry_with_backoff(self, func, *args, **kwargs):
        """Retry function with exponential backoff."""
        for attempt in range(self._max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt == self._max_retries - 1:
                    raise
                wait_time = self._retry_delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

    def _create_classification_prompt(self, email_metadata: Dict) -> str:
        system_prompt = get_system_prompt()
        rules = get_classification_rules()
        
        return f"""{system_prompt}

        Analyze this email metadata:
        Subject: {email_metadata.get('subject', '')}
        From: {email_metadata.get('from', '')}
        To: {email_metadata.get('to', '')}
        Has Attachments: {email_metadata.get('has_attachments', False)}
        Number of Recipients: {email_metadata.get('recipient_count', 1)}
        Date: {email_metadata.get('date', '')}
        
        Respond in JSON format only with the following structure:
        {{
            "main_category": "spam"|"phishing"|"newsletter"|"ai_response"|"requires_human",
            "sub_category": "legal"|"government"|"group_reservation"|"guest_emergency"|"business"|"complex_inquiry"|"vendor"|"other",
            "priority": "urgent"|"high"|"medium"|"low",
            "confidence": 0.0-1.0,
            "reason": "detailed reasoning"
        }}
        """

    def _parse_model_response(self, response_text: str, email_metadata: Dict) -> ClassificationResult:
        try:
            # Extract JSON from response (model might include additional text)
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1]
            
            # Clean up any potential leading/trailing whitespace or newlines
            json_str = json_str.strip()
            
            logger.info(f"Parsing JSON response: {json_str}")
            data = json.loads(json_str)
            
            # Convert response to proper case for enum matching
            main_cat = data["main_category"].lower()
            sub_cat = data.get("sub_category", "other")
            if not sub_cat:
                sub_cat = "other"
            sub_cat = sub_cat.lower()
            priority = data.get("priority", "medium").lower()
            
            # Detect language from subject
            try:
                detected_language = langdetect.detect(email_metadata.get('subject', ''))
            except:
                detected_language = 'en'
            
            # Special handling for group reservations
            if "groepsreservering" in email_metadata.get('subject', '').lower():
                main_cat = "requires_human"
                sub_cat = "group_reservation"
                priority = "high"
            
            # Special handling for phishing/spam indicators
            if "fake-booking-site.com" in email_metadata.get('body', '').lower():
                main_cat = "phishing"  # Force phishing for known fake domains
                sub_cat = "other"
                priority = "high"
            
            # Special handling for government communications
            if ".be" in email_metadata.get('from', '').lower() and any(
                term in email_metadata.get('from', '').lower() 
                for term in ['brandweer', 'belastingdienst', 'gov', 'overheid', 'inspectie']
            ):
                main_cat = "requires_human"
                sub_cat = "government"
                priority = "urgent"
            
            # For AI_RESPONSE, don't use HumanAttentionCategory
            if main_cat == "ai_response":
                return ClassificationResult(
                    main_category=MainCategory(main_cat),
                    sub_category=None,  # No sub-category for AI_RESPONSE
                    priority=Priority(priority),
                    confidence=float(data["confidence"]),
                    requires_human=False,
                    reason=data["reason"],
                    metadata={},
                    detected_language=detected_language
                )
            
            return ClassificationResult(
                main_category=MainCategory(main_cat),
                sub_category=HumanAttentionCategory(sub_cat),
                priority=Priority(priority),
                confidence=float(data["confidence"]),
                requires_human=main_cat == "requires_human",
                reason=data["reason"],
                metadata={},
                detected_language=detected_language
            )
        except Exception as e:
            logger.error(f"Error parsing model response: {str(e)}")
            logger.error(f"Response text was: {response_text}")
            return self._fallback_classification(email_metadata)

    async def classify_email(self, email_metadata: Dict) -> ClassificationResult:
        """Classify email using local Ollama model."""
        try:
            await self._ensure_client()
            
            prompt = self._create_classification_prompt(email_metadata)
            
            response = await self._retry_with_backoff(
                self._client.post,
                self.ollama_url,
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.status_code}")
                return self._fallback_classification(email_metadata)
            
            result = response.json()
            logger.info(f"Raw model response: {result}")
            return self._parse_model_response(result["response"], email_metadata)
            
        except Exception as e:
            logger.error(f"Classification error: {str(e)}")
            return self._fallback_classification(email_metadata)
    
    def _fallback_classification(self, email_metadata: Dict) -> ClassificationResult:
        """Fallback classification when model fails."""
        # Special handling for known patterns
        subject_lower = email_metadata.get('subject', '').lower()
        from_lower = email_metadata.get('from', '').lower()
        
        if "groepsreservering" in subject_lower:
            return ClassificationResult(
                main_category=MainCategory.REQUIRES_HUMAN,
                sub_category=HumanAttentionCategory.GROUP_RESERVATION,
                priority=Priority.HIGH,
                confidence=0.9,
                requires_human=True,
                reason="Group reservation detected in subject",
                metadata={},
                detected_language='nl'
            )
        
        if ".be" in from_lower and any(
            term in from_lower 
            for term in ['belastingdienst', 'gov', 'overheid', 'inspectie']
        ):
            return ClassificationResult(
                main_category=MainCategory.REQUIRES_HUMAN,
                sub_category=HumanAttentionCategory.GOVERNMENT,
                priority=Priority.URGENT,
                confidence=0.9,
                requires_human=True,
                reason="Government communication detected",
                metadata={},
                detected_language='nl'
            )
        
        return ClassificationResult(
            main_category=MainCategory.REQUIRES_HUMAN,
            sub_category=HumanAttentionCategory.OTHER,
            priority=Priority.MEDIUM,
            confidence=0.5,
            requires_human=True,
            reason="Fallback classification due to service error",
            metadata={},
            detected_language='en'
        ) 