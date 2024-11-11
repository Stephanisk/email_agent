import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
import os
from typing import List, Dict, Optional
from datetime import datetime
import ssl
from dotenv import load_dotenv
import re

from .ai_client import AIClient, AIResponse
from app.services.email_classifier import classify_email
from app.schemas.email_schemas import EmailCategory, EmailClassification
from ..utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

class EmailClient:
    FOLDER_STRUCTURE = {
        'root_folders': [
            'Original_Received',
            'AI_Processed'
        ],
        'ai_processed_folders': {
            'Responded': None,
            'Spam': None,
            'Newsletter': None,
            'Phishing': None,
            'Requires_Human': {
                'business': None,
                'government': None,
                'group_reservation': None,
                'other': None
            }
        }
    }

    def __init__(self):
        self.host = os.getenv('EMAIL_HOST')
        self.imap_port = int(os.getenv('IMAP_PORT', 993))
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.email = os.getenv('EMAIL_ADDRESS')
        self.password = os.getenv('EMAIL_PASSWORD')
        self.ai_client = AIClient()

    async def connect_imap(self) -> imaplib.IMAP4_SSL:
        """Establish a secure IMAP connection."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        mail = imaplib.IMAP4_SSL(
            host=self.host,
            port=self.imap_port,
            ssl_context=context
        )
        mail.login(self.email, self.password)
        return mail

    async def fetch_latest_emails(self, limit: int = 5) -> List[Dict]:
        """Fetch the latest emails from the inbox."""
        try:
            mail = await self.connect_imap()
            
            print("Selecting INBOX...")
            mail.select("INBOX")
            
            print("Searching for emails...")
            # Search for all emails that are not deleted
            _, messages = mail.search(None, 'NOT', 'DELETED')
            email_ids = messages[0].split()
            
            if not email_ids:
                print("No emails found in INBOX")
                mail.logout()
                return []
            
            print(f"Found {len(email_ids)} emails in INBOX")
            
            latest_emails = []
            for i in range(min(limit, len(email_ids))):
                email_id = email_ids[-(i+1)]
                print(f"Fetching email ID: {email_id.decode()}")
                email_data = await self.fetch_email_by_id(mail, email_id)
                if email_data:
                    print(f"Successfully fetched email: {email_data['subject']}")
                    latest_emails.append(email_data)
                else:
                    print(f"Failed to fetch email ID: {email_id.decode()}")
            
            mail.logout()
            print(f"Retrieved {len(latest_emails)} emails")
            return latest_emails
        
        except Exception as e:
            print(f"Error fetching emails: {str(e)}")
            raise

    async def fetch_email_by_id(self, mail: imaplib.IMAP4_SSL, email_id: bytes) -> Optional[Dict]:
        """Fetch and parse a single email by its ID."""
        try:
            _, msg_data = mail.fetch(email_id, "(RFC822 FLAGS)")
            email_body = msg_data[0][1]
            message = email.message_from_bytes(email_body)
            
            # Get message ID for threading
            message_id = message.get('Message-ID', '')
            references = message.get('References', '').split()
            in_reply_to = message.get('In-Reply-To', '')
            
            # Extract email content with better encoding handling
            body = ""
            if message.is_multipart():
                for part in message.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        try:
                            body = payload.decode(charset, errors='replace')
                        except (UnicodeDecodeError, LookupError):
                            body = payload.decode('utf-8', errors='replace')
                        break
            else:
                payload = message.get_payload(decode=True)
                charset = message.get_content_charset() or 'utf-8'
                try:
                    body = payload.decode(charset, errors='replace')
                except (UnicodeDecodeError, LookupError):
                    body = payload.decode('utf-8', errors='replace')
            
            # Decode headers with better error handling
            def decode_header_safe(header):
                decoded = decode_header(header or "")
                parts = []
                for part, charset in decoded:
                    if isinstance(part, bytes):
                        try:
                            parts.append(part.decode(charset or 'utf-8', errors='replace'))
                        except (UnicodeDecodeError, LookupError):
                            parts.append(part.decode('utf-8', errors='replace'))
                    else:
                        parts.append(part)
                return " ".join(parts)
            
            subject = decode_header_safe(message["subject"])
            from_ = decode_header_safe(message.get("from", ""))
            
            return {
                "id": email_id.decode(),
                "message_id": message_id,
                "references": references,
                "in_reply_to": in_reply_to,
                "subject": subject,
                "from": from_,
                "date": message.get("date", ""),
                "body": body
            }
            
        except Exception as e:
            print(f"Error parsing email {email_id}: {str(e)}")
            return None

    async def send_response(self, email_id: str, response: str, to_address: str) -> bool:
        """Send response email."""
        try:
            mail = await self.connect_imap()
            mail.select('INBOX')
            
            # Get original message to get subject and other details
            _, msg_data = mail.fetch(str(email_id), '(RFC822)')
            original_email = email.message_from_bytes(msg_data[0][1])
            original_subject = original_email['Subject']
            
            # Extract original message body
            original_body = ""
            if original_email.is_multipart():
                for part in original_email.walk():
                    if part.get_content_type() == "text/plain":
                        original_body = part.get_payload(decode=True).decode()
                        break
            else:
                original_body = original_email.get_payload(decode=True).decode()
            
            # Create response message
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = to_address
            msg['Subject'] = f"Re: {original_subject}" if not original_subject.lower().startswith('re:') else original_subject
            msg['In-Reply-To'] = original_email.get('Message-ID', '')
            msg['References'] = original_email.get('References', '')
            
            # Compose full response with original message
            full_response = (
                f"{response}\n\n"
                f"{'-' * 60}\n"
                f"On {original_email['Date']}, {original_email['From']} wrote:\n\n"
                f"{original_body}"
            )
            
            # Add response content
            msg.attach(MIMEText(full_response, 'plain'))
            
            # Send response
            with smtplib.SMTP(self.host, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
                
            logger.info(f"Response sent to {to_address}")
            logger.info(f"Subject: {msg['Subject']}")
            
            # Store sent email in Sent folder
            await self.store_sent_email(msg)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}")
            return False

    async def process_and_respond(self, limit: int = 5):
        """Process latest emails and generate responses."""
        try:
            emails = await self.fetch_latest_emails(limit)
            
            for email_data in emails:
                # Skip if it's already a reply
                if email_data['subject'].lower().startswith('re:'):
                    continue
                
                # Generate and send response
                success = await self.send_response(
                    to_email=email_data['from'],
                    subject=email_data['subject'],
                    original_content=email_data['body'],
                    email_metadata=email_data
                )
                
                if success:
                    print(f"Successfully responded to: {email_data['subject']}")
                else:
                    print(f"Failed to respond to: {email_data['subject']}")
                
        except Exception as e:
            print(f"Error in process_and_respond: {str(e)}")
            raise

    async def fetch_and_classify_emails(self, limit: int = 5) -> List[Dict]:
        """Fetch emails and classify them."""
        emails = await self.fetch_latest_emails(limit)
        classified_emails = []
        
        for email_data in emails:
            classification = await classify_email(email_data)
            email_data['classification'] = classification.dict()
            classified_emails.append(email_data)
            
            # Move email to appropriate folder based on classification
            if classification.category != EmailCategory.LEGITIMATE:
                await self.move_email_to_folder(
                    email_id=email_data['id'],
                    folder=classification.category.value
                )
        
        return classified_emails

    async def setup_folders(self) -> None:
        """Create required folders if they don't exist."""
        try:
            mail = await self.connect_imap()
            
            # First list existing folders
            _, list_response = mail.list()
            existing_folders = [f.decode().split('"')[-1].strip() for f in list_response if f]
            logger.info("Existing folders:")
            for folder in existing_folders:
                logger.info(f"- {folder}")
            
            # Get delimiter
            delimiter = '/'
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break

            # Create and subscribe to root folders
            for folder in self.FOLDER_STRUCTURE['root_folders']:
                if folder not in existing_folders:
                    try:
                        mail.create(f'"{folder}"')
                        logger.info(f"Created root folder: {folder}")
                    except Exception as e:
                        logger.info(f"Folder exists or error: {folder} ({str(e)})")
                # Subscribe regardless of whether we just created it
                try:
                    mail.subscribe(f'"{folder}"')
                    logger.info(f"Subscribed to root folder: {folder}")
                except Exception as e:
                    if "already subscribed" not in str(e).lower():
                        logger.error(f"Error subscribing to folder {folder}: {str(e)}")

            # Create and subscribe to AI_Processed subfolders
            for folder, subfolders in self.FOLDER_STRUCTURE['ai_processed_folders'].items():
                folder_path = f"AI_Processed{delimiter}{folder}"
                try:
                    mail.create(f'"{folder_path}"')
                    logger.info(f"Created folder: {folder_path}")
                except Exception as e:
                    logger.info(f"Folder exists or error: {folder_path} ({str(e)})")
                # Subscribe to the folder
                try:
                    mail.subscribe(f'"{folder_path}"')
                    logger.info(f"Subscribed to folder: {folder_path}")
                except Exception as e:
                    if "already subscribed" not in str(e).lower():
                        logger.error(f"Error subscribing to folder {folder_path}: {str(e)}")
                
                # Create and subscribe to subfolders if any
                if subfolders:
                    for subfolder in subfolders:
                        subfolder_path = f"{folder_path}{delimiter}{subfolder}"
                        try:
                            mail.create(f'"{subfolder_path}"')
                            logger.info(f"Created subfolder: {subfolder_path}")
                        except Exception as e:
                            logger.info(f"Subfolder exists or error: {subfolder_path} ({str(e)})")
                        # Subscribe to the subfolder
                        try:
                            mail.subscribe(f'"{subfolder_path}"')
                            logger.info(f"Subscribed to subfolder: {subfolder_path}")
                        except Exception as e:
                            if "already subscribed" not in str(e).lower():
                                logger.error(f"Error subscribing to subfolder {subfolder_path}: {str(e)}")
                            
        except Exception as e:
            logger.error(f"Error setting up folders: {str(e)}")
            raise

    async def move_email_to_folder(self, email_id: str, folder: str) -> bool:
        """Move email to appropriate AI folder and mark it."""
        try:
            print(f"\nMoving email {email_id} to folder {folder}")
            mail = await self.connect_imap()
            
            print("Selecting INBOX...")
            mail.select('"INBOX"')
            
            # Get the delimiter
            print("Getting folder delimiter...")
            _, list_response = mail.list()
            delimiter = '/'
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break
            
            # Capitalize folder name to match existing structure
            folder = folder.capitalize()
            
            # Construct full folder path with proper quoting
            full_folder = f'"AI_Processed{delimiter}{folder}"'
            print(f"Target folder: {full_folder}")
            
            # Try to create the folder if it doesn't exist
            try:
                print(f"Attempting to create/verify folder: {full_folder}")
                create_result = mail.create(full_folder)
                print(f"Create result: {create_result}")
            except imaplib.IMAP4.error as e:
                print(f"Folder exists or creation note: {str(e)}")
            
            # Try to subscribe to the folder
            try:
                mail.subscribe(full_folder)
            except imaplib.IMAP4.error as e:
                print(f"Subscribe note: {str(e)}")
            
            # Verify folder exists by trying to select it
            try:
                mail.select(full_folder)
                mail.select('"INBOX"')  # Switch back to INBOX
            except imaplib.IMAP4.error as e:
                print(f"Error verifying folder: {str(e)}")
                mail.logout()
                return False
            
            # Copy email to appropriate folder
            print("Copying email to target folder...")
            result = mail.copy(email_id, full_folder)
            print(f"Copy result: {result}")
            
            if result[0] == 'OK':
                # Mark original email as processed and delete from inbox
                print("Marking original email as processed and deleted...")
                mail.store(email_id, '+FLAGS', '(\\Seen \\Deleted)')
                mail.expunge()
                
                print(f"Successfully moved email {email_id} to {full_folder}")
                mail.logout()
                return True
            
            mail.logout()
            print(f"Failed to copy email {email_id} to {full_folder}")
            return False
            
        except Exception as e:
            print(f"Error moving email to folder: {str(e)}")
            return False

    async def store_original_mail(self, email_id: str, original_email: Dict) -> bool:
        """Store a copy of the original email in the Original_Received folder."""
        try:
            mail = await self.connect_imap()
            
            # Get the delimiter and construct folder path
            _, list_response = mail.list()
            delimiter = '/'
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break
            
            original_folder = f'"Original_Received"'
            print(f"\n=== Storing original mail in {original_folder} ===")
            
            try:
                # Select INBOX to get original message
                mail.select('"INBOX"')
                
                # Get the complete original message
                _, msg_data = mail.fetch(email_id, '(RFC822)')
                if not msg_data or not msg_data[0]:
                    print("Failed to fetch original message")
                    return False
                
                # Ensure the Original_Received folder exists
                try:
                    mail.create(original_folder)
                    print("Created Original_Received folder")
                except imaplib.IMAP4.error:
                    print("Original_Received folder already exists")
                
                # Store the original message
                append_result = mail.append(original_folder, '(\\Seen)', None, msg_data[0][1])
                print(f"Original mail storage result: {append_result[0]}")
                
                mail.logout()
                return append_result[0] == 'OK'
                
            except Exception as e:
                print(f"Error storing original mail: {str(e)}")
                return False
                
        except Exception as e:
            print(f"Error in store_original_mail: {str(e)}")
            return False

    async def process_and_store_response(self, email_data: Dict, classification: EmailClassification, is_reply: bool = False) -> bool:
        """Generate AI response, send it, and store the thread in the appropriate folder."""
        try:
            if classification.category == EmailCategory.REQUIRES_HUMAN:
                return await self.flag_for_human_attention(
                    email_id=email_data['id'],
                    reason=classification.reason
                )
            
            if classification.category != EmailCategory.LEGITIMATE:
                return await self.move_email_to_folder(
                    email_id=email_data['id'],
                    folder=classification.category.value
                )

            # For legitimate emails, first store the original
            print("\n=== Storing backup of original email ===")
            backup_success = await self.store_original_mail(
                email_id=email_data['id'],
                original_email=email_data
            )
            if not backup_success:
                print("Warning: Failed to store original mail backup")

            # Continue with normal processing...
            print(f"\n=== Generating response for: {email_data['subject']} ===")
            
            # Extract latest content for AI context
            if is_reply and 'thread_history' in email_data:
                print("Using thread history for context...")
                thread_content = (
                    f"Previous conversation:\n{email_data['thread_history']}\n\n"
                    f"New message:\n{email_data['body']}"
                )
            else:
                thread_content = email_data['body']
            
            # Generate AI response
            ai_response = await self.ai_client.generate_response(
                email_content=thread_content,
                email_metadata=email_data
            )
            
            # Create email message for sending
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = "stephane.kolijn@gmail.com"  # Override recipient for testing
            msg['Subject'] = f"Re: {email_data['subject']}"
            msg['In-Reply-To'] = email_data.get('message_id', '')
            msg['References'] = email_data.get('message_id', '')
            
            # Combine content for email sending (without thread history)
            email_content = (
                f"AI Response:\n{ai_response.content}\n\n"
                f"{'-' * 60}\n"
                f"Original Message:\n"
                f"From: {email_data['from']}\n"
                f"Subject: {email_data['subject']}\n"
                f"Date: {email_data['date']}\n\n"
                f"{email_data['body']}"
            )
            
            msg.attach(MIMEText(email_content, 'plain'))
            
            # Send the response
            print("\n=== Sending response email ===")
            try:
                with smtplib.SMTP(self.host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.email, self.password)
                    server.send_message(msg)
                print("Email sent successfully to stephane.kolijn@gmail.com")
            except Exception as e:
                print(f"Failed to send email: {str(e)}")
                return False
            
            # Create combined content for storage (including thread history)
            storage_content = email_content
            if is_reply and 'thread_history' in email_data:
                storage_content += f"\n\n{'-' * 60}\nPrevious Thread:\n{email_data['thread_history']}"
            
            # Store in Legitimate folder
            print("\n=== Storing in Legitimate folder ===")
            success = await self.store_in_legitimate_folder(
                email_id=email_data['id'],
                combined_content=storage_content,
                original_email=email_data
            )
            print(f"Storage result: {'Success' if success else 'Failed'}")
            
            return success
            
        except Exception as e:
            print(f"Error processing and storing response: {str(e)}")
            return False

    async def store_in_legitimate_folder(self, email_id: str, combined_content: str, original_email: Dict) -> bool:
        """Store complete thread in Responded folder."""
        try:
            mail = await self.connect_imap()
            
            # First check for existing thread
            search_subject = original_email['subject']
            if search_subject.lower().startswith('re:'):
                search_subject = search_subject[3:].strip()
            if search_subject.lower().startswith('fwd:'):
                search_subject = search_subject[4:].strip()
                
            # Select Responded folder
            mail.select('"AI_Processed/Responded"')
            
            # Clean and escape the search subject
            clean_subject = search_subject.replace('"', '\\"')  # Escape quotes
            clean_subject = clean_subject.split(',')[0]  # Take first part before comma
            clean_subject = clean_subject.strip()
            
            try:
                # Search for existing thread
                search_criteria = f'SUBJECT "{clean_subject}"'.encode()
                _, messages = mail.search(None, search_criteria)
                
                if messages[0]:
                    # Remove old thread messages
                    msg_ids = messages[0].split()
                    for old_id in msg_ids:
                        logger.info(f"Removing old thread message: {old_id.decode()}")
                        mail.store(old_id, '+FLAGS', '\\Deleted')
                    mail.expunge()
                    logger.info("Old thread messages removed")
            except Exception as e:
                logger.info(f"No existing thread found: {str(e)}")
            
            # Create new message with complete thread
            msg = MIMEMultipart()
            msg['From'] = original_email['from']
            msg['To'] = original_email.get('to', 'stephane.kolijn@gmail.com')
            msg['Subject'] = original_email['subject']
            msg['Date'] = original_email['date']
            msg['Message-ID'] = original_email.get('message_id', '')
            msg['In-Reply-To'] = original_email.get('in_reply_to', '')
            msg['References'] = original_email.get('references', '')
            
            # Add the combined content
            msg.attach(MIMEText(combined_content, 'plain'))
            
            # Store the new message
            logger.info("Storing message in AI_Processed/Responded...")
            result = mail.append('"AI_Processed/Responded"', '(\\Seen)', None, msg.as_bytes())
            
            if result[0] == 'OK':
                # Remove from inbox - make sure to select INBOX first
                mail.select('INBOX')
                try:
                    # Search for the email by Message-ID to ensure we get the right one
                    search_criteria = f'HEADER Message-ID "{original_email.get("message_id", "")}"'
                    _, messages = mail.search(None, search_criteria)
                    
                    if messages[0]:
                        # Get all matching messages (should be only one)
                        msg_ids = messages[0].split()
                        for msg_id in msg_ids:
                            mail.store(msg_id, '+FLAGS', '\\Deleted')
                        mail.expunge()
                        logger.info("Message removed from inbox")
                    else:
                        # Try by email_id directly as fallback
                        mail.store(str(email_id), '+FLAGS', '\\Deleted')
                        mail.expunge()
                        logger.info("Message removed from inbox (using ID)")
                        
                except Exception as e:
                    logger.error(f"Error removing from inbox: {str(e)}")
                    # Continue even if inbox removal fails
                
                logger.info("Message stored successfully")
                return True
                
            logger.error("Failed to store message")
            return False
            
        except Exception as e:
            logger.error(f"Error storing thread: {str(e)}")
            return False
        finally:
            try:
                mail.logout()
            except:
                pass

    async def update_email_with_response(self, email_id: str, combined_content: str) -> bool:
        """Update the original email with the AI response in the Legitimate folder."""
        try:
            print("\nUpdating email with response...")
            mail = await self.connect_imap()
            
            print("Selecting INBOX...")
            mail.select('"INBOX"')
            
            # Get the delimiter
            print("Getting folder delimiter...")
            _, list_response = mail.list()
            delimiter = '/'
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break
            
            # Construct folder path
            folder = f'"AI_Processed{delimiter}Legitimate"'
            print(f"Target folder: {folder}")
            
            # Get original message data
            _, msg_data = mail.fetch(email_id, '(RFC822)')
            if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
                raise Exception("Failed to fetch original message")
                
            original_email = email.message_from_bytes(msg_data[0][1])
            
            # Create updated message preserving headers
            msg = MIMEMultipart()
            msg['From'] = original_email['From']
            msg['To'] = original_email['To']
            msg['Subject'] = original_email['Subject']
            msg['Date'] = original_email['Date']
            msg['Message-ID'] = original_email['Message-ID']
            msg['In-Reply-To'] = original_email.get('Message-ID', '')
            msg['References'] = original_email.get('References', '')
            
            # Add the combined content
            msg.attach(MIMEText(combined_content, 'plain'))
            
            # Store the updated message
            print("Storing updated message...")
            print(f"From: {msg['From']}")
            print(f"Subject: {msg['Subject']}")
            
            # Ensure the target folder exists
            try:
                mail.select(folder)
            except imaplib.IMAP4.error:
                print(f"Creating folder {folder}")
                mail.create(folder)
            
            # Store message with basic flags
            append_result = mail.append(folder, '(\\Seen)', None, msg.as_bytes())
            print(f"Append result: {append_result}")
            
            if append_result[0] == 'OK':
                # Remove the original email from inbox
                mail.select('"INBOX"')  # Switch back to INBOX
                print("Removing original email from inbox...")
                mail.store(email_id, '+FLAGS', '(\\Seen \\Deleted)')
                mail.expunge()
                
                mail.logout()
                print("Email update completed successfully")
                return True
            else:
                print(f"Failed to append message: {append_result}")
                mail.logout()
                return False
            
        except Exception as e:
            print(f"Error updating email with response: {str(e)}")
            return False

    async def process_latest_emails(self, limit: int = 10) -> List[Dict]:
        """Get latest emails from inbox."""
        try:
            mail = await self.connect_imap()
            await self.setup_folders()
            
            mail.select('INBOX')
            _, messages = mail.search(None, 'ALL')
            email_ids = messages[0].split()
            
            if not email_ids:
                return []
                
            # Get latest emails
            email_ids = email_ids[-limit:]
            emails = []
            
            for email_id in email_ids:
                _, msg_data = mail.fetch(email_id, '(RFC822)')
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                # Extract body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()
                
                emails.append({
                    "id": email_id.decode(),
                    "subject": msg["subject"],
                    "from": msg["from"],
                    "to": msg["to"],
                    "date": msg["date"],
                    "body": body,
                    "message_id": msg["Message-ID"],
                    "in_reply_to": msg["In-Reply-To"]
                })
            
            return emails
            
        except Exception as e:
            print(f"Error getting emails: {str(e)}")
            return []
        finally:
            try:
                mail.logout()
            except:
                pass

    async def get_thread_history(self, email_data: Dict) -> Optional[str]:
        """Retrieve thread history from Responded folder."""
        try:
            mail = await self.connect_imap()
            
            # Select Responded folder
            mail.select('"AI_Processed/Responded"')
            
            # Clean up subject for searching
            search_subject = email_data['subject']
            if search_subject.lower().startswith('re:'):
                while search_subject.lower().startswith('re:'):
                    search_subject = search_subject[3:].strip()
            
            if search_subject.lower().startswith('fwd:'):
                search_subject = search_subject[4:].strip()
                
            logger.info(f"Searching for thread with subject: {search_subject}")
            
            # Search for existing thread
            _, messages = mail.search(None, f'SUBJECT "{search_subject}"')
            if messages[0]:
                msg_ids = messages[0].split()
                if msg_ids:
                    # Get latest thread message
                    latest_id = msg_ids[-1]
                    _, msg_data = mail.fetch(latest_id, '(RFC822)')
                    thread_message = email.message_from_bytes(msg_data[0][1])
                    
                    # Extract content
                    if thread_message.is_multipart():
                        for part in thread_message.walk():
                            if part.get_content_type() == "text/plain":
                                content = part.get_payload(decode=True).decode()
                                logger.info("Found existing thread")
                                return content
                    else:
                        content = thread_message.get_payload(decode=True).decode()
                        logger.info("Found existing thread")
                        return content
            
            logger.info("No existing thread found")
            return None
            
        except Exception as e:
            logger.error(f"Error getting thread history: {str(e)}")
            return None

    async def get_email_flags(self, email_id: str) -> List[str]:
        """Get flags for a specific email."""
        try:
            mail = await self.connect_imap()
            mail.select("INBOX")
            
            _, flags_data = mail.fetch(email_id, '(FLAGS)')
            flags_str = flags_data[0].decode()
            
            # Extract flags using regex
            import re
            flags_match = re.search(r'\(([^)]*)\)', flags_str)
            if flags_match:
                flags = flags_match.group(1).split()
                return flags
            return []
            
        except Exception as e:
            print(f"Error getting email flags: {str(e)}")
            return []

    async def flag_for_human_attention(self, email_id: str, reason: str) -> bool:
        """Flag an email for human attention with specific flags and status."""
        try:
            mail = await self.connect_imap()
            mail.select('"INBOX"')
            
            # Get the delimiter
            _, list_response = mail.list()
            delimiter = '/'
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break
            
            # Construct folder path
            folder = f'"AI_Processed{delimiter}Requires_Human"'
            
            # Get original message to preserve headers
            _, msg_data = mail.fetch(email_id, '(RFC822)')
            original_email = email.message_from_bytes(msg_data[0][1])
            
            # Create message with human attention flags
            msg = MIMEMultipart()
            msg['From'] = original_email['From']
            msg['To'] = original_email['To']
            msg['Subject'] = original_email['Subject']
            msg['Date'] = original_email['Date']
            msg['Message-ID'] = original_email['Message-ID']
            
            # Add reason for human attention at the top
            original_content = original_email.get_payload()
            combined_content = (
                f"[REQUIRES HUMAN ATTENTION]\n"
                f"Reason: {reason}\n"
                f"{'-' * 60}\n\n"
                f"{original_content}"
            )
            
            msg.attach(MIMEText(combined_content, 'plain'))
            
            # Move to Requires Human folder with specific flags
            append_result = mail.append(
                folder,
                '(\\Flagged \\Seen $Requires_Human)',
                None,
                msg.as_bytes()
            )
            
            if append_result[0] == 'OK':
                # Remove from inbox
                mail.store(email_id, '+FLAGS', '(\\Deleted)')
                mail.expunge()
                print(f"Email flagged for human attention: {msg['Subject']}")
                return True
                
            return False
            
        except Exception as e:
            print(f"Error flagging for human attention: {str(e)}")
            return False

    async def mark_human_response_complete(self, email_id: str) -> bool:
        """Mark an email as handled by human staff."""
        try:
            mail = await self.connect_imap()
            mail.select('"AI_Processed/Requires_Human"')
            
            # Mark as completed and move to Completed folder
            mail.store(email_id, '+FLAGS', '(\\Answered $Human_Handled)')
            
            # Optional: Move to a "Completed" subfolder
            _, list_response = mail.list()
            delimiter = '/'
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break
            
            completed_folder = f'"AI_Processed{delimiter}Completed"'
            
            # Create Completed folder if it doesn't exist
            try:
                mail.create(completed_folder)
            except imaplib.IMAP4.error:
                pass            
            # Move to Completed folder
            mail.copy(email_id, completed_folder)
            mail.store(email_id, '+FLAGS', '(\\Deleted)')
            mail.expunge()
            
            return True
            
        except Exception as e:
            print(f"Error marking as complete: {str(e)}")
            return False

    async def store_sent_email(self, msg: MIMEMultipart) -> bool:
        """Store sent email in the Sent folder."""
        try:
            mail = await self.connect_imap()
            
            # Try to select Sent folder (might have different names)
            sent_folders = ['"Sent"', '"Sent Items"', '"Sent Mail"']
            sent_folder = None
            
            for folder in sent_folders:
                try:
                    mail.select(folder)
                    sent_folder = folder
                    break
                except imaplib.IMAP4.error:
                    continue
            
            if not sent_folder:
                print("Could not find Sent folder")
                return False
            
            # Store the message
            append_result = mail.append(sent_folder, '(\\Seen)', None, msg.as_bytes())
            return append_result[0] == 'OK'
            
        except Exception as e:
            print(f"Error storing sent email: {str(e)}")
            return False

    async def move_to_folder(self, email_id: str, target_folder: str) -> bool:
        """Move email to specified folder, creating it if needed."""
        try:
            mail = await self.connect_imap()
            
            # First ensure all parent folders exist
            folder_parts = target_folder.split('/')
            current_path = ""
            for part in folder_parts:
                if current_path:
                    current_path += "/"
                current_path += part
                
                # Try to create each level of folder hierarchy
                try:
                    result = mail.create(f'"{current_path}"')
                    if result[0] == 'OK':
                        logger.info(f"Created folder: {current_path}")
                    else:
                        logger.info(f"Folder exists or creation failed: {current_path}")
                except Exception as e:
                    logger.info(f"Folder probably exists: {current_path} ({str(e)})")
            
            # Now select source folder and get the email
            mail.select('INBOX')
            
            # Fetch the email content
            _, msg_data = mail.fetch(str(email_id), '(RFC822)')
            if not msg_data[0]:
                logger.error("Could not fetch email content")
                return False
                
            email_content = msg_data[0][1]
            
            # Store in target folder
            logger.info(f"Storing email in {target_folder}...")
            result = mail.append(f'"{target_folder}"', '(\\Seen)', None, email_content)
            
            if result[0] == 'OK':
                # Only delete from inbox if successfully stored in target
                mail.store(str(email_id), '+FLAGS', '\\Deleted')
                mail.expunge()
                logger.info(f"Successfully moved email {email_id} to {target_folder}")
                return True
                
            logger.error(f"Failed to store email in {target_folder}")
            return False
            
        except Exception as e:
            logger.error(f"Error moving email: {str(e)}")
            return False
        finally:
            try:
                mail.logout()
            except:
                pass

    async def store_original(self, email_id: str, email: Dict) -> bool:
        """Store original email in Original_Received folder."""
        try:
            mail = await self.connect_imap()
            mail.select('INBOX')
            
            # Get original message
            _, msg_data = mail.fetch(str(email_id), '(RFC822)')
            original_email = msg_data[0][1]
            
            # Store in Original_Received
            result = mail.append('"Original_Received"', '(\\Seen)', None, original_email)
            print(f"Original mail storage result: {result[0]}")
            
            return result[0] == 'OK'
            
        except Exception as e:
            print(f"Error storing original: {str(e)}")
            return False
        finally:
            try:
                mail.logout()
            except:
                pass

    async def find_thread_across_folders(self, email: Dict) -> Optional[Dict]:
        """Search for thread history across all relevant folders."""
        try:
            mail = await self.connect_imap()
            search_subject = email['subject']
            if search_subject.lower().startswith('re:'):
                search_subject = search_subject[3:].strip()
            if search_subject.lower().startswith('fwd:'):
                search_subject = search_subject[4:].strip()
            
            # Clean and escape the search subject
            clean_subject = search_subject.replace('"', '\\"')  # Escape quotes
            clean_subject = clean_subject.split(',')[0]  # Take first part before comma
            clean_subject = clean_subject.strip()
            
            # List of folders to search (excluding certain folders)
            folders_to_search = [
                'AI_Processed/Responded',
                'AI_Processed/Requires_Human/business',
                'AI_Processed/Requires_Human/government',
                'AI_Processed/Requires_Human/group_reservation',
                'AI_Processed/Requires_Human/other'
            ]
            
            for folder in folders_to_search:
                try:
                    # Properly select folder with quotes and wait for response
                    select_result = mail.select(f'"{folder}"')
                    if select_result[0] != 'OK':
                        logger.error(f"Failed to select folder {folder}")
                        continue
                    
                    # Use properly encoded search criteria
                    search_criteria = f'SUBJECT "{clean_subject}"'.encode('utf-8')
                    _, messages = mail.search(None, search_criteria)
                    
                    if messages[0]:
                        msg_ids = messages[0].split()
                        latest_msg_id = msg_ids[-1]
                        _, msg_data = mail.fetch(latest_msg_id, '(RFC822)')
                        if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
                            continue
                            
                        email_body = msg_data[0][1]
                        
                        # Use email.message_from_bytes on the raw email data
                        import email as email_parser
                        msg = email_parser.message_from_bytes(email_body)
                        
                        # Extract content
                        content = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    content = part.get_payload(decode=True).decode()
                                    break
                        else:
                            content = msg.get_payload(decode=True).decode()
                        
                        return {
                            'folder': folder,
                            'history': content,
                            'original_subject': clean_subject  # Add original subject for thread marking
                        }
                except Exception as e:
                    logger.error(f"Error searching folder {folder}: {str(e)}")
                    # Create a new connection for next attempt
                    mail = await self.connect_imap()
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error searching for thread: {str(e)}")
            return None
        finally:
            try:
                mail.logout()
            except:
                pass

    async def create_folder_if_not_exists(self, folder_path: str) -> bool:
        """Create folder and any necessary parent folders."""
        try:
            mail = await self.connect_imap()
            
            # Split path and create each level
            parts = folder_path.split('/')
            current_path = ""
            
            for part in parts:
                if current_path:
                    current_path += "/"
                current_path += part
                
                try:
                    # Try to create the folder
                    result = mail.create(f'"{current_path}"')
                    if result[0] == 'OK':
                        logger.info(f"Created folder: {current_path}")
                        # Subscribe to the folder immediately after creation
                        mail.subscribe(f'"{current_path}"')
                        logger.info(f"Subscribed to folder: {current_path}")
                    else:
                        logger.info(f"Folder exists: {current_path}")
                        # Subscribe anyway in case it exists but isn't subscribed
                        try:
                            mail.subscribe(f'"{current_path}"')
                        except Exception as e:
                            if "already subscribed" not in str(e).lower():
                                logger.error(f"Error subscribing to folder {current_path}: {str(e)}")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Error creating folder {current_path}: {str(e)}")
                        return False
                    # Try to subscribe even if folder exists
                    try:
                        mail.subscribe(f'"{current_path}"')
                    except Exception as sub_e:
                        if "already subscribed" not in str(sub_e).lower():
                            logger.error(f"Error subscribing to existing folder {current_path}: {str(sub_e)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating folders: {str(e)}")
            return False
        finally:
            try:
                mail.logout()
            except:
                pass

    async def process_email(self, email_id: str, email_data: Dict, target_folder: str) -> bool:
        """Process a single email - backup, find thread, move to target folder."""
        mail = None
        try:
            mail = await self.connect_imap()
            
            # 1. First backup to Original_Received
            logger.info("Backing up to Original_Received...")
            backup_result = await self.store_original(email_id, email_data)
            if not backup_result:
                raise Exception("Failed to backup original email")
            
            # 2. Look for existing thread
            thread_info = None
            if email_data['subject'].lower().startswith('re:'):
                logger.info("Checking for existing thread...")
                thread_info = await self.find_thread_across_folders(email_data)
                if thread_info:
                    logger.info(f"Found existing thread in: {thread_info['folder']}")
                    target_folder = thread_info['folder']
            
            # 3. Ensure target folder exists
            await self.create_folder_if_not_exists(target_folder)
            
            # 4. Move email to target folder with appropriate flags
            logger.info(f"Moving email to {target_folder}...")
            mail.select('INBOX')
            _, msg_data = mail.fetch(str(email_id), '(RFC822)')
            email_content = msg_data[0][1]
            
            # Determine flags based on target folder and thread existence
            flags = []
            if 'Requires_Human' in target_folder:
                if thread_info:
                    # For thread replies, mark as flagged but read
                    flags = ['\\Flagged', '\\Seen']
                    
                    # Mark the first message of the thread as unread to make thread visible
                    try:
                        mail.select(f'"{target_folder}"')
                        _, messages = mail.search(None, f'SUBJECT "{thread_info["original_subject"]}"')
                        if messages[0]:
                            first_msg_id = messages[0].split()[0]  # Get first message ID
                            mail.store(first_msg_id, '-FLAGS', '\\Seen')  # Remove Seen flag
                            logger.info("Marked thread parent as unread")
                    except Exception as e:
                        logger.error(f"Error marking thread parent: {str(e)}")
                else:
                    # For new messages, mark as unread and flagged
                    flags = ['\\Flagged']  # No \Seen flag = unread
            else:
                flags = ['\\Seen']  # Mark as read for non-human-required emails
            
            flags_str = ' '.join(flags) if flags else None
            
            # Store in target folder with appropriate flags
            logger.info(f"Storing with flags: {flags_str}")
            result = mail.append(f'"{target_folder}"', flags_str, None, email_content)
            
            if result[0] == 'OK':
                # Delete from inbox in a separate try block to ensure it happens
                try:
                    mail.select('INBOX')
                    mail.store(str(email_id), '+FLAGS', '\\Deleted')
                    mail.expunge()
                    logger.info("Original email deleted from inbox")
                except Exception as e:
                    logger.error(f"Error deleting from inbox: {str(e)}")
                    # Try one more time with a fresh connection
                    try:
                        mail = await self.connect_imap()
                        mail.select('INBOX')
                        mail.store(str(email_id), '+FLAGS', '\\Deleted')
                        mail.expunge()
                        logger.info("Original email deleted from inbox (second attempt)")
                    except Exception as e:
                        logger.error(f"Failed to delete from inbox on second attempt: {str(e)}")
                        raise
                
                logger.info(f"Successfully processed email to {target_folder} with flags: {flags}")
                return True
            
            raise Exception(f"Failed to store email in {target_folder}")
            
        except Exception as e:
            logger.error(f"Error processing email: {str(e)}")
            return False
        finally:
            if mail:
                try:
                    mail.logout()
                except:
                    pass

    async def delete_existing_thread(self, folder: str, subject: str) -> bool:
        """Delete existing thread messages in a folder."""
        try:
            mail = await self.connect_imap()
            mail.select(f'"{folder}"')
            
            # Search for messages with the subject
            _, messages = mail.search(None, f'SUBJECT "{subject}"')
            if messages[0]:
                msg_ids = messages[0].split()
                for msg_id in msg_ids:
                    mail.store(msg_id, '+FLAGS', '\\Deleted')
                mail.expunge()
                logger.info(f"Deleted existing thread messages for subject: {subject}")
            return True
        except Exception as e:
            logger.error(f"Error deleting thread: {str(e)}")
            return False
        finally:
            try:
                mail.logout()
            except:
                pass

    async def store_with_content(self, email_id: str, target_folder: str, content: str, email_data: Dict, flags: List[str]) -> bool:
        """Store email with specific content in target folder."""
        try:
            mail = await self.connect_imap()
            
            # Create message with combined content
            msg = MIMEMultipart()
            msg['From'] = email_data['from']
            msg['To'] = email_data.get('to', 'stephane.kolijn@gmail.com')
            msg['Subject'] = email_data['subject']
            msg['Date'] = email_data['date']
            msg['Message-ID'] = email_data.get('message_id', '')
            msg['In-Reply-To'] = email_data.get('in_reply_to', '')
            
            msg.attach(MIMEText(content, 'plain'))
            
            # Store in target folder
            flags_str = ' '.join(flags) if flags else None
            result = mail.append(f'"{target_folder}"', flags_str, None, msg.as_bytes())
            
            if result[0] == 'OK':
                # Delete from inbox
                mail.select('INBOX')
                mail.store(str(email_id), '+FLAGS', '\\Deleted')
                mail.expunge()
                logger.info(f"Successfully stored email with content in {target_folder}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error storing with content: {str(e)}")
            return False
        finally:
            try:
                mail.logout()
            except:
                pass
