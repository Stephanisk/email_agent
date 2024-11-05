import re
from typing import Dict, List, Set
from app.schemas.email_schemas import EmailClassification, EmailCategory

SPAM_KEYWORDS = {
    'viagra', 'cialis', 'winner', 'lottery', 'prince', 'inheritance',
    'bitcoin', 'investment opportunity', 'make money fast'
}

NEWSLETTER_INDICATORS = {
    'unsubscribe', 'newsletter', 'subscription', 'marketing',
    'weekly update', 'monthly update'
}

URGENT_KEYWORDS = {
    'urgent', 'immediate attention', 'asap', 'emergency',
    'important', 'priority', 'confidential'
}

async def classify_email(email_data: Dict) -> EmailClassification:
    """Classify email based on content and metadata."""
    text = f"{email_data['subject']} {email_data['body']}".lower()
    
    # Check for spam indicators
    spam_count = sum(1 for keyword in SPAM_KEYWORDS if keyword in text)
    if spam_count >= 2:
        return EmailClassification(
            category=EmailCategory.SPAM,
            confidence=min(spam_count * 0.2, 0.9),
            reason="Multiple spam keywords detected"
        )
    
    # Check for newsletter indicators
    newsletter_count = sum(1 for indicator in NEWSLETTER_INDICATORS if indicator in text)
    if newsletter_count >= 1:
        return EmailClassification(
            category=EmailCategory.NEWSLETTER,
            confidence=0.8,
            reason="Newsletter indicators found"
        )
    
    # Check for urgent/human attention required
    urgent_count = sum(1 for keyword in URGENT_KEYWORDS if keyword in text)
    if urgent_count >= 1:
        return EmailClassification(
            category=EmailCategory.REQUIRES_HUMAN,
            confidence=0.7,
            reason="Urgent or important matter detected"
        )
    
    # Default to legitimate
    return EmailClassification(
        category=EmailCategory.LEGITIMATE,
        confidence=0.6,
        reason="No spam or newsletter indicators found"
    ) 