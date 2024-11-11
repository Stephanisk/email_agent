import asyncio
import pytest
from app.services.classification.service import ClassificationService
from app.services.classification.models import MainCategory, HumanAttentionCategory, Priority
import logging
import os
from datetime import datetime

# Set up logging to both file and console
def setup_test_logging():
    log_dir = "test_logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"classification_test_{timestamp}.log")
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file

@pytest.mark.asyncio
async def test_classification_service():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = setup_test_logging()
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting classification tests - logging to {log_file}")
    service = ClassificationService()
    
    test_cases = [
        # Regular booking inquiry (should be AI_RESPONSE)
        {
            "subject": "Room availability check",
            "from": "john@example.com",
            "to": "hotel@example.com",
            "body": "Hello, I would like to check availability for a double room from April 15-20, 2024. What are your rates? Best regards, John",
            "has_attachments": False,
            "recipient_count": 1,
            "date": "2024-03-20"
        },
        # Spam with normal subject but spam content
        {
            "subject": "Question about your hotel",
            "from": "marketing@super-deals-xyz.com",
            "to": "hotel@example.com",
            "body": """CONGRATULATIONS! You've been selected to receive our AMAZING OFFER! 
            Increase your hotel bookings by 500%! Buy our premium marketing package now! 
            Limited time offer! Act fast! Click here! Guaranteed results!""",
            "has_attachments": False,
            "recipient_count": 1,
            "date": "2024-03-20"
        },
        # Dutch government inspection
        {
            "subject": "Dringende kennisgeving: Brandveiligheid inspectie",
            "from": "inspectie@brandweer.be",
            "to": "hotel@example.com",
            "body": """Geachte heer/mevrouw,

            Bij deze delen wij u mede dat er op 25 maart 2024 een inspectie zal plaatsvinden
            van de brandveiligheid in uw hotel. Aanwezigheid van de bedrijfsleiding is vereist.

            Met vriendelijke groet,
            Brandweerinspectie België""",
            "has_attachments": True,
            "recipient_count": 1,
            "date": "2024-03-20"
        },
        # Group reservation (should always require human attention)
        {
            "subject": "Groepsreservering voor 30 personen - Mei 2024",
            "from": "groep@bedrijf.nl",
            "to": "hotel@example.com",
            "body": """Beste hoteleigenaar,

            Wij willen graag een groepsreservering maken voor 30 personen van onze sportclub.
            Periode: 15-17 mei 2024
            Benodigde kamers: 15 tweepersoonskamers
            Inclusief ontbijt en diner.

            Kunt u een offerte maken?

            Met vriendelijke groet,
            Jan Sportclub""",
            "has_attachments": False,
            "recipient_count": 1,
            "date": "2024-03-20"
        },
        # Newsletter with multiple recipients
        {
            "subject": "Horeca Nederland Nieuwsbrief Maart 2024",
            "from": "news@horecafed.nl",
            "to": "subscribers@horecafed.nl",
            "body": """Maart Nieuwsbrief - Horeca Nederland

            1. Nieuwe regelgeving voor hotels
            2. Trends in de hotelbranche
            3. Upcoming events
            4. Netwerkmogelijkheden

            Uitschrijven kan via de link onderaan.""",
            "has_attachments": False,
            "recipient_count": 500,
            "date": "2024-03-20"
        },
        # Phishing attempt
        {
            "subject": "Urgent: Update Your Hotel Listing",
            "from": "support@booking-verify-account.com",
            "to": "hotel@example.com",
            "body": """URGENT ACTION REQUIRED

            Your hotel listing needs immediate verification to prevent removal.
            Click here to verify: http://fake-booking-site.com/verify
            
            This requires your immediate attention and login credentials.

            Booking.com Support Team""",
            "has_attachments": True,
            "recipient_count": 1,
            "date": "2024-03-20"
        }
    ]
    
    logger.info("\n" + "="*80)
    logger.info("Starting Comprehensive Email Classification Tests")
    logger.info("="*80)
    
    results_summary = {
        "ai_response": 0,
        "requires_human": 0,
        "spam": 0,
        "phishing": 0,
        "newsletter": 0
    }
    
    detailed_results = []
    
    for i, email_metadata in enumerate(test_cases, 1):
        logger.info(f"\nTest Case #{i}")
        logger.info("="*50)
        logger.info(f"Subject: {email_metadata['subject']}")
        logger.info(f"From: {email_metadata['from']}")
        logger.info(f"Recipients: {email_metadata['recipient_count']}")
        logger.info(f"Has Attachments: {email_metadata['has_attachments']}")
        logger.info("\nEmail Body Preview:")
        logger.info("-"*30)
        logger.info(email_metadata['body'][:150] + "..." if len(email_metadata['body']) > 150 else email_metadata['body'])
        logger.info("-"*30)
        
        result = await service.classify_email(email_metadata)
        
        classification_result = {
            "test_case": i,
            "subject": email_metadata['subject'],
            "classification": {
                "main_category": result.main_category.value,
                "sub_category": result.sub_category.value if result.sub_category else 'N/A',
                "priority": result.priority.value if result.priority else 'N/A',
                "confidence": f"{result.confidence:.2f}",
                "language": result.detected_language,
                "requires_human": result.requires_human,
                "reason": result.reason
            }
        }
        detailed_results.append(classification_result)
        
        logger.info("\nClassification Results:")
        logger.info(f"Main Category: {result.main_category.value}")
        logger.info(f"Sub-category: {result.sub_category.value if result.sub_category else 'N/A'}")
        logger.info(f"Priority: {result.priority.value if result.priority else 'N/A'}")
        logger.info(f"Confidence: {result.confidence:.2f}")
        logger.info(f"Language: {result.detected_language}")
        logger.info(f"Requires Human: {result.requires_human}")
        logger.info(f"Reason: {result.reason}")
        logger.info("="*50)
        
        # Update summary
        results_summary[result.main_category.value] += 1
        
        # Assertions for specific cases
        if "groepsreservering" in email_metadata['subject'].lower():
            assert result.main_category == MainCategory.REQUIRES_HUMAN
            assert result.sub_category == HumanAttentionCategory.GROUP_RESERVATION
            
        if "@brandweer.be" in email_metadata['from'].lower():
            assert result.main_category == MainCategory.REQUIRES_HUMAN
            assert result.sub_category == HumanAttentionCategory.GOVERNMENT
            assert result.priority == Priority.URGENT
            
        if email_metadata['recipient_count'] > 100:
            assert result.main_category == MainCategory.NEWSLETTER
            
        if "fake-booking-site.com" in email_metadata['body']:
            assert result.main_category == MainCategory.PHISHING
    
    # Print and log summary
    summary = "\n" + "="*80 + "\n"
    summary += "Classification Summary\n"
    summary += "="*80 + "\n"
    summary += f"Total emails processed: {len(test_cases)}\n"
    for category, count in results_summary.items():
        summary += f"{category.upper()}: {count}\n"
    summary += "="*80 + "\n"
    
    logger.info(summary)
    
    # Save detailed results to a separate file
    results_file = os.path.join("test_logs", f"detailed_results_{timestamp}.txt")
    with open(results_file, 'w') as f:
        f.write("Detailed Classification Results\n")
        f.write("="*80 + "\n\n")
        for result in detailed_results:
            f.write(f"Test Case #{result['test_case']}\n")
            f.write(f"Subject: {result['subject']}\n")
            f.write("Classification:\n")
            for key, value in result['classification'].items():
                f.write(f"  {key}: {value}\n")
            f.write("\n" + "-"*50 + "\n\n")
    
    logger.info(f"\nDetailed results saved to: {results_file}")

if __name__ == "__main__":
    asyncio.run(test_classification_service())