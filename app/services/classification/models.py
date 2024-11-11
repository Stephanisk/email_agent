from enum import Enum
from pydantic import BaseModel
from typing import Optional, List, Dict

class Priority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class MainCategory(str, Enum):
    SPAM = "spam"
    PHISHING = "phishing"
    NEWSLETTER = "newsletter"
    AI_RESPONSE = "ai_response"
    REQUIRES_HUMAN = "requires_human"

class HumanAttentionCategory(str, Enum):
    LEGAL = "legal"
    GOVERNMENT = "government"
    GROUP_RESERVATION = "group_reservation"
    GUEST_EMERGENCY = "guest_emergency"
    BUSINESS = "business"
    COMPLEX_INQUIRY = "complex_inquiry"
    VENDOR = "vendor"
    OTHER = "other"

class ClassificationResult(BaseModel):
    main_category: MainCategory
    sub_category: Optional[HumanAttentionCategory] = None
    priority: Optional[Priority] = None
    confidence: float
    requires_human: bool
    reason: str
    metadata: Dict[str, str] = {}
    detected_language: Optional[str] = None 