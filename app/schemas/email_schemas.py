from enum import Enum  
from pydantic import BaseModel
from typing import Optional

class EmailCategory(str, Enum):
    LEGITIMATE = "legitimate"
    SPAM = "spam"
    NEWSLETTER = "newsletter"
    REQUIRES_HUMAN = "requires_human"

class EmailClassification(BaseModel):
    category: EmailCategory
    confidence: float
    reason: Optional[str] = None 