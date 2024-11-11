import asyncio
from app.services.email_client import EmailClient
from app.utils.logger import get_logger
import os
from dotenv import load_dotenv

logger = get_logger(__name__)

async def test_email_connection():
    """Simple test to verify email connection and inbox access."""
    load_dotenv()
    
    # Create email client instance using existing configuration
    email_client = EmailClient()
    
    logger.info("\n" + "="*80)
    logger.info("Testing Email Connection")
    logger.info("="*80)
    
    # Log the actual connection details we're using
    logger.info(f"Testing connection to {os.getenv('EMAIL_HOST')} as {os.getenv('EMAIL_ADDRESS')}")
    
    # Try to get unprocessed emails
    emails = await email_client.get_unprocessed_emails(limit=5)
    
    if not emails:
        logger.info("No emails found in inbox")
        return
        
    logger.info(f"Found {len(emails)} emails in inbox")
    
    # Print details of found emails
    for i, email in enumerate(emails, 1):
        logger.info(f"\nEmail #{i}:")
        logger.info(f"Subject: {email.get('subject', 'No subject')}")
        logger.info(f"From: {email.get('from', 'No sender')}")
        logger.info(f"Date: {email.get('date', 'No date')}")
        logger.info("-"*50)

if __name__ == "__main__":
    asyncio.run(test_email_connection()) 