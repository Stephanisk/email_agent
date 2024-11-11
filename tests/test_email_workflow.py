import asyncio
from app.services.email_workflow import EmailWorkflow
from app.services.classification.models import MainCategory
from app.utils.logger import get_logger
from dotenv import load_dotenv
import os

logger = get_logger(__name__)

async def test_single_email_workflow():
    """Test complete workflow with real email: fetch, classify with Ollama, process."""
    logger.info("\n" + "="*80)
    logger.info("STEP 1: Initializing Test")
    logger.info("="*80)
    
    load_dotenv()
    logger.info(f"Email Configuration:")
    logger.info(f"Host: {os.getenv('EMAIL_HOST')}")
    logger.info(f"Email: {os.getenv('EMAIL_ADDRESS')}")
    logger.info(f"IMAP Port: {os.getenv('IMAP_PORT')}")
    
    logger.info("\n" + "="*80)
    logger.info("STEP 2: Creating Workflow Instance")
    logger.info("="*80)
    workflow = EmailWorkflow()
    logger.info("Workflow instance created")
    logger.info(f"Using classifier: {workflow.classifier.model_name}")
    
    # First set up the folders
    logger.info("\nSetting up folders...")
    await workflow.email_client.setup_folders()
    logger.info("Folders setup completed")
    
    logger.info("\n" + "="*80)
    logger.info("STEP 3: Fetching Latest Email")
    logger.info("="*80)
    
    # Get latest emails using the working method
    logger.info("Fetching latest email from inbox...")
    emails = await workflow.email_client.process_latest_emails(limit=1)
    
    if not emails:
        logger.error("No emails found in inbox")
        return
    
    email = emails[0]
    logger.info(f"Successfully retrieved email: {email.get('subject', 'No subject')}")
    
    # Check if it's a reply and look for thread history
    is_reply = email['subject'].lower().startswith('re:')
    if is_reply:
        logger.info("\nChecking for existing thread history...")
        thread_history = await workflow.email_client.get_thread_history(email)
        if thread_history:
            logger.info("Found existing thread:")
            logger.info("-"*50)
            logger.info(thread_history[:200] + "..." if len(thread_history) > 200 else thread_history)
            logger.info("-"*50)
            email['thread_history'] = thread_history
        else:
            logger.info("No existing thread found")
    
    logger.info("\n" + "="*80)
    logger.info("STEP 4: Email Details")
    logger.info("="*80)
    logger.info(f"Subject: {email.get('subject', 'No subject')}")
    logger.info(f"From: {email.get('from', 'No sender')}")
    logger.info(f"Date: {email.get('date', 'No date')}")
    logger.info(f"Message-ID: {email.get('message_id', 'No ID')}")
    logger.info(f"In-Reply-To: {email.get('in_reply_to', 'N/A')}")
    logger.info("\nPreview of body:")
    logger.info("-"*50)
    logger.info(email.get('body', 'No body')[:200] + "..." if len(email.get('body', '')) > 200 else email.get('body', 'No body'))
    logger.info("-"*50)
    
    logger.info("\n" + "="*80)
    logger.info("STEP 5: Starting Classification")
    logger.info("="*80)
    logger.info("Sending to Ollama classifier...")
    
    # Process the email through the workflow
    result = await workflow.process_email(email)
    
    logger.info("\n" + "="*80)
    logger.info("STEP 6: Processing Results")
    logger.info("="*80)
    
    if result["processed"]:
        logger.info("Email successfully processed!")
        logger.info("\nClassification Details:")
        logger.info(f"Main Category: {result['classification']['main_category']}")
        logger.info(f"Sub-category: {result['classification'].get('sub_category', 'N/A')}")
        logger.info(f"Priority: {result['classification'].get('priority', 'N/A')}")
        logger.info(f"Confidence: {result['classification'].get('confidence', 'N/A')}")
        logger.info(f"Language: {result.get('language', 'unknown')}")
        logger.info(f"Reason: {result['classification'].get('reason', 'N/A')}")
        
        logger.info("\nActions Taken:")
        if result['classification']['main_category'] == MainCategory.AI_RESPONSE.value:
            logger.info("✓ Original email backed up")
            logger.info("✓ Generated and sent AI response")
            if is_reply:
                logger.info("✓ Updated existing thread in AI_Processed/Responded")
            else:
                logger.info("✓ Created new thread in AI_Processed/Responded")
        elif result['classification']['main_category'] == MainCategory.REQUIRES_HUMAN.value:
            logger.info("✓ Original email backed up")
            logger.info(f"✓ Moved to human attention folder: {result['classification'].get('sub_category', 'general')}")
            if result['classification'].get('priority') == "URGENT":
                logger.info("✓ Added urgent flag")
        elif result['classification']['main_category'] == MainCategory.SPAM.value:
            logger.info("✓ Original email backed up")
            logger.info("✓ Moved to spam folder")
        elif result['classification']['main_category'] == MainCategory.PHISHING.value:
            logger.info("✓ Original email backed up")
            logger.info("✓ Moved to phishing folder")
        elif result['classification']['main_category'] == MainCategory.NEWSLETTER.value:
            logger.info("✓ Original email backed up")
            logger.info("✓ Moved to newsletter folder")
    else:
        logger.error("Email processing failed!")
        logger.error(f"Error: {result.get('error', 'Unknown error')}")
    
    logger.info("\n" + "="*80)
    logger.info("Test Complete")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(test_single_email_workflow())