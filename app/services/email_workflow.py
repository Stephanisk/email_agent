from typing import Dict, List, Optional
from .classification.service import ClassificationService
from .email_client import EmailClient
from .classification.models import MainCategory, HumanAttentionCategory, Priority
import langdetect
from ..utils.logger import get_logger

logger = get_logger(__name__)

class EmailWorkflow:
    def __init__(self):
        self.classifier = ClassificationService()
        self.email_client = EmailClient()
        
    async def process_email(self, email: Dict) -> Dict:
        """Process a single email through the complete workflow."""
        try:
            logger.info(f"Processing email: {email.get('subject', 'No subject')}")
            
            # Extract metadata for classification
            metadata = {
                "subject": email.get("subject", ""),
                "from": email.get("from", ""),
                "to": email.get("to", ""),
                "body": email.get("body", ""),
                "has_attachments": bool(email.get("attachments")),
                "recipient_count": len(email.get("to", "").split(",")),
                "date": email.get("date", ""),
                "message_id": email.get("message_id", ""),
                "in_reply_to": email.get("in_reply_to", ""),
                "is_reply": email['subject'].lower().startswith('re:')
            }
            
            # Classify email
            logger.info("Classifying email using Ollama...")
            classification = await self.classifier.classify_email(metadata)
            logger.info(f"Classification result: {classification.main_category}")
            
            # Handle AI_RESPONSE differently
            if classification.main_category == MainCategory.AI_RESPONSE:
                # Generate AI response
                from app.services.ai_client import AIClient
                ai_client = AIClient()
                response = await ai_client.generate_response(email.get("body", ""), metadata)
                
                # Send response
                await self.email_client.send_response(
                    email_id=email["id"],
                    response=response.content,
                    to_address="stephane.kolijn@gmail.com"
                )
                
                # Clean up subject for thread search
                search_subject = email['subject']
                if search_subject.lower().startswith('re:'):
                    search_subject = search_subject[3:].strip()
                if search_subject.lower().startswith('fwd:'):
                    search_subject = search_subject[4:].strip()
                
                # Create combined content
                combined_content = (
                    f"AI Response:\n{response.content}\n\n"
                    f"{'-' * 60}\n"
                    f"Original Message:\n"
                    f"From: {email['from']}\n"
                    f"Subject: {email['subject']}\n"
                    f"Date: {email['date']}\n\n"
                    f"{email['body']}"
                )
                
                # First backup original
                await self.email_client.store_original(email["id"], email)
                
                # Delete existing thread if any
                await self.email_client.delete_existing_thread("AI_Processed/Responded", search_subject)
                
                # Store new combined content
                success = await self.email_client.store_with_content(
                    email_id=email["id"],
                    target_folder="AI_Processed/Responded",
                    content=combined_content,
                    email_data=email,
                    flags=['\\Seen']  # Mark as read
                )
                
            else:
                # Handle other categories normally
                if classification.main_category == MainCategory.REQUIRES_HUMAN:
                    target_folder = f"AI_Processed/Requires_Human/{classification.sub_category.value}"
                else:
                    category_name = classification.main_category.value.capitalize()
                    target_folder = f"AI_Processed/{category_name}"
                
                success = await self.email_client.process_email(
                    email_id=email["id"],
                    email_data=email,
                    target_folder=target_folder
                )
            
            if not success:
                raise Exception("Failed to process email")
            
            return {
                "email_id": email["id"],
                "classification": classification.dict(),
                "language": langdetect.detect(email.get("body", "")),
                "processed": True,
                "is_reply": metadata["is_reply"]
            }
            
        except Exception as e:
            logger.error(f"Error processing email: {str(e)}")
            return {
                "email_id": email.get("id"),
                "error": str(e),
                "processed": False
            }
    
    async def process_batch(self, limit: int = 10) -> List[Dict]:
        """Process a batch of emails."""
        emails = await self.email_client.process_latest_emails(limit)
        results = []
        
        for email in emails:
            result = await self.process_email(email)
            results.append(result)
            
        return results
    
    async def generate_ai_response(self, email: Dict, language: str) -> str:
        """Generate AI response in the detected language."""
        # Placeholder for actual implementation
        return f"Auto-response in {language}"