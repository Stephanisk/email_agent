from typing import Optional, Dict
import re
from .patterns import OTA_RULES, OTARule
from ...utils.logger import get_logger

logger = get_logger(__name__)

class OTAService:
    def __init__(self):
        self.rules = OTA_RULES

    def check_email(self, email: Dict) -> Optional[OTARule]:
        """Check if email matches any OTA patterns."""
        subject = email.get('subject', '').strip()
        from_address = email.get('from', '').lower()
        body = email.get('body', '').strip()

        for ota_name, rule in self.rules.items():
            # First check domain
            if rule.domain not in from_address:
                continue

            # Then check subject patterns
            for pattern in rule.subject_patterns:
                if pattern.lower() in subject.lower():
                    logger.info(f"Found OTA match: {ota_name} - {pattern}")
                    return rule

            # Check content patterns if defined
            for pattern in rule.content_patterns:
                if pattern.lower() in body.lower():
                    logger.info(f"Found OTA content match: {ota_name} - {pattern}")
                    return rule

        return None 