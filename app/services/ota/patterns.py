from typing import Dict, List
from pydantic import BaseModel

class OTARule(BaseModel):
    subject_patterns: List[str]
    content_patterns: List[str]
    domain: str
    target_folder: str
    requires_backup: bool = False
    requires_response: bool = False

# Can be loaded from JSON/YAML in the future for UI management
OTA_RULES = {
    "hostelworld": OTARule(
        subject_patterns=[
            "Hostelworld Confirmed Booking - Lybeer Travellers' Hostel",
            "HostelWorld Cancelled Booking"
        ],
        content_patterns=[],
        domain="hostelworld.com",
        target_folder="AI_Processed/OTA/Hostelworld",
        requires_backup=False,
        requires_response=False
    ),
    "booking": OTARule(
        subject_patterns=[
            "guest messages waiting for you",
            "We received this message from",
            "Uw gast heeft iets nodig",
            "Je gast wil graag gratis annuleren"
        ],
        content_patterns=[],
        domain="booking.com",
        target_folder="AI_Processed/OTA/Booking",
        requires_backup=False,
        requires_response=False
    ),
    # Add more OTAs as needed
} 