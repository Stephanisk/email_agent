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

load_dotenv()

class EmailClient:
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

    async def send_response(self, to_email: str, subject: str, original_content: str, 
                          email_metadata: Dict) -> bool:
        """Generate and send an AI response to an email."""
        try:
            print("\n=== GENERATING RESPONSE ===")
            print(f"Original email: {to_email}")
            print(f"Subject: {subject}")
            
            # Generate AI response
            ai_response = await self.ai_client.generate_response(
                email_content=original_content,
                email_metadata=email_metadata
            )
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = "stephane.kolijn@gmail.com"
            msg['Subject'] = f"Re: {subject}" if not subject.startswith('Re:') else subject
            
            # Add original sender info to the response body for reference
            response_with_metadata = (
                f"Original email from: {to_email}\n"
                f"Original subject: {subject}\n"
                f"---\n\n"
                f"{ai_response.content}"
            )
            
            print("\n=== SENDING RESPONSE ===")
            print(f"To: stephane.kolijn@gmail.com")
            print(f"Subject: {msg['Subject']}")
            print(f"Content:\n{response_with_metadata}")
            print("=" * 50)
            
            # Add AI-generated response with metadata
            msg.attach(MIMEText(response_with_metadata, 'plain'))
            
            # Connect to SMTP server and send
            with smtplib.SMTP(self.host, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
            
            print("\n=== EMAIL SENT SUCCESSFULLY ===")
            return True
            
        except Exception as e:
            print(f"Error sending response: {str(e)}")
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
        """Create standard folders if they don't exist."""
        try:
            mail = await self.connect_imap()
            
            # First, list existing folders to get the hierarchy delimiter
            _, list_response = mail.list()
            if not list_response:
                raise Exception("Could not get folder list")
            
            # Get the delimiter from the first folder entry
            delimiter = '/'  # Default to forward slash
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    print(f"Folder info: {folder_str}")
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break
            
            print(f"Using delimiter: {delimiter}")
            
            # Define standard folders using the correct delimiter
            base_folder = "AI_Processed"
            subfolders = ["Legitimate", "Spam", "Newsletter", "Requires_Human"]
            
            # First create base folder if it doesn't exist
            try:
                _, folders = mail.list()
                existing_folders = [f.decode().split('"')[-1] for f in folders if f]
                
                if base_folder not in existing_folders:
                    print(f"Creating base folder: {base_folder}")
                    mail.create(f'"{base_folder}"')
                    mail.subscribe(f'"{base_folder}"')
                else:
                    print(f"Base folder {base_folder} already exists")
            except imaplib.IMAP4.error as e:
                print(f"Base folder note: {str(e)}")
            
            # Then create subfolders if they don't exist
            for subfolder in subfolders:
                full_path = f"{base_folder}{delimiter}{subfolder}"
                try:
                    if full_path not in existing_folders:
                        print(f"Creating folder: {full_path}")
                        mail.create(f'"{full_path}"')
                        mail.subscribe(f'"{full_path}"')
                    else:
                        print(f"Folder {full_path} already exists")
                except imaplib.IMAP4.error as e:
                    print(f"Subfolder note for {subfolder}: {str(e)}")
            
            mail.logout()
            print("Folder setup completed")
            
        except Exception as e:
            print(f"Error setting up folders: {str(e)}")
            if 'mail' in locals():
                try:
                    mail.logout()
                except:
                    pass
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

            # Generate and send AI response for legitimate emails
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
        """Store or update the complete thread in the Legitimate folder."""
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
            
            legitimate_folder = f'"AI_Processed{delimiter}Legitimate"'
            print(f"Target folder: {legitimate_folder}")
            
            try:
                mail.select(legitimate_folder)
                
                # Clean up subject for searching
                search_subject = original_email['subject']
                if search_subject.lower().startswith('re:'):
                    # Remove all "Re:" prefixes
                    while search_subject.lower().startswith('re:'):
                        search_subject = search_subject[3:].strip()
                
                # Remove "Fwd:" if present
                if search_subject.lower().startswith('fwd:'):
                    search_subject = search_subject[4:].strip()
                
                # Find and remove all old thread messages
                print(f"Searching for old thread messages with subject: {search_subject}")
                _, messages = mail.search(None, f'SUBJECT "{search_subject}"')
                if messages[0]:
                    old_msg_ids = messages[0].split()
                    for old_id in old_msg_ids:
                        print(f"Marking old thread message {old_id} for deletion")
                        mail.store(old_id, '+FLAGS', '\\Deleted')
                    mail.expunge()
                    print("Removed old thread messages")
                
                # Create new message with complete thread
                msg = MIMEMultipart()
                msg['From'] = original_email['from']
                msg['To'] = original_email.get('to', 'stephane.kolijn@gmail.com')
                msg['Subject'] = original_email['subject']
                msg['Date'] = original_email['date']
                msg['Message-ID'] = original_email.get('message_id', '')
                msg['In-Reply-To'] = original_email.get('in_reply_to', '')
                
                msg.attach(MIMEText(combined_content, 'plain'))
                
                # Store the new message
                print("Storing updated thread message...")
                append_result = mail.append(legitimate_folder, '(\\Seen)', None, msg.as_bytes())
                
                if append_result[0] == 'OK':
                    # Remove original from inbox
                    mail.select('"INBOX"')
                    mail.store(email_id, '+FLAGS', '(\\Seen \\Deleted)')
                    mail.expunge()
                    
                    mail.logout()
                    print("Thread updated successfully")
                    return True
                
                mail.logout()
                print("Failed to store updated thread")
                return False
                
            except Exception as e:
                print(f"Error during thread update: {str(e)}")
                return False
            
        except Exception as e:
            print(f"Error storing in legitimate folder: {str(e)}")
            return False

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

    async def process_latest_emails(self, limit: int = 4) -> List[Dict]:
        """Process the latest emails with complete workflow."""
        try:
            # Ensure folders exist
            await self.setup_folders()
            
            # Fetch and classify emails
            print("\nFetching latest emails...")
            emails = await self.fetch_latest_emails(limit)
            
            if not emails:
                print("No emails found to process")
                return []
                
            processed_emails = []
            
            for email_data in emails:
                print(f"\nProcessing email: {email_data['subject']}")
                
                # Check if it's a reply and get thread history
                is_reply = email_data['subject'].lower().startswith('re:')
                if is_reply:
                    print("Email is a reply - checking thread history...")
                    thread_history = await self.get_thread_history(email_data)
                    if thread_history:
                        email_data['thread_history'] = thread_history
                        print("Found existing thread history")
                    else:
                        print("No thread history found")
                
                # Classify email
                print("Classifying email...")
                classification = await classify_email(email_data)
                email_data['classification'] = classification.dict()
                print(f"Classification result: {classification.category}")
                
                # Process email based on classification
                print("Processing based on classification...")
                success = await self.process_and_store_response(
                    email_data=email_data,
                    classification=classification,
                    is_reply=is_reply
                )
                
                if success:
                    processed_emails.append(email_data)
                    print(f"Successfully processed email: {email_data['subject']} -> {classification.category.value}")
                else:
                    print(f"Failed to process email: {email_data['subject']}")
            
            return processed_emails
            
        except Exception as e:
            print(f"Error processing emails: {str(e)}")
            raise

    async def get_thread_history(self, email_data: Dict) -> Optional[str]:
        """Retrieve the thread history from the Legitimate folder."""
        try:
            mail = await self.connect_imap()
            
            # Construct Legitimate folder path
            _, list_response = mail.list()
            delimiter = '/'
            for folder_info in list_response:
                if folder_info:
                    folder_str = folder_info.decode()
                    delimiter_match = re.search(r'"(.)"', folder_str)
                    if delimiter_match:
                        delimiter = delimiter_match.group(1)
                        break
            
            legitimate_folder = f'"AI_Processed{delimiter}Legitimate"'
            print(f"Searching for thread history in {legitimate_folder}")
            
            # Select the Legitimate folder
            try:
                mail.select(legitimate_folder)
            except imaplib.IMAP4.error as e:
                print(f"Could not select Legitimate folder: {str(e)}")
                return None
            
            # Clean up subject for searching
            search_subject = email_data['subject']
            if search_subject.lower().startswith('re:'):
                # Remove all "Re:" prefixes
                while search_subject.lower().startswith('re:'):
                    search_subject = search_subject[3:].strip()
            
            # Remove "Fwd:" if present
            if search_subject.lower().startswith('fwd:'):
                search_subject = search_subject[4:].strip()
                
            print(f"Searching for base subject: {search_subject}")
            
            # Try to find the thread using subject
            try:
                _, messages = mail.search(None, f'SUBJECT "{search_subject}"')
                if messages[0]:
                    msg_ids = messages[0].split()
                    if msg_ids:
                        # Get the latest message in the thread
                        latest_id = msg_ids[-1]
                        _, msg_data = mail.fetch(latest_id, '(RFC822)')
                        thread_message = email.message_from_bytes(msg_data[0][1])
                        print(f"Found thread with subject: {thread_message['subject']}")
                        
                        # Extract the content
                        if thread_message.is_multipart():
                            for part in thread_message.walk():
                                if part.get_content_type() == "text/plain":
                                    content = part.get_payload(decode=True).decode('utf-8', errors='replace')
                                    print("Found thread content in multipart message")
                                    return content
                        else:
                            content = thread_message.get_payload(decode=True).decode('utf-8', errors='replace')
                            print("Found thread content in single part message")
                            return content
            
            except Exception as e:
                print(f"Error searching by subject: {str(e)}")
            
            print("No thread history found")
            return None
            
        except Exception as e:
            print(f"Error getting thread history: {str(e)}")
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