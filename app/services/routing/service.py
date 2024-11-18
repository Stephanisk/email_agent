from typing import Dict, Optional
from ..ota.service import OTAService
from ...utils.logger import get_logger

logger = get_logger(__name__)

class RoutingService:
    def __init__(self):
        self.ota_service = OTAService()

    async def check_special_routing(self, email: Dict) -> Optional[str]:
        """Check if email needs special routing before classification."""
        # Check OTA patterns first
        ota_rule = self.ota_service.check_email(email)
        if ota_rule:
            return ota_rule.target_folder

        return None 