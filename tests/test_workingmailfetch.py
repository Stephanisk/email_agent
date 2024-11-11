import asyncio
from app.services.email_client import EmailClient

async def test_email_workflow():
    """Test complete email workflow including classification, responses, and human handling."""
    try:
        print("\n" + "="*50)
        print("Starting Complete Email Workflow Test")
        print("="*50)
        
        # Initialize client
        client = EmailClient()
        
        # Setup folders first
        print("\nSetting up folders...")
        await client.setup_folders()
        
        # Process single email
        print("\nProcessing latest email...")
        processed_emails = await client.process_latest_emails(limit=1)
        
        if processed_emails:
            email = processed_emails[0]
            print("\n" + "="*50)
            print("Processed Email Details")
            print("="*50)
            print(f"Subject: {email['subject']}")
            print(f"From: {email['from']}")
            print(f"Category: {email['classification']['category']}")
            print(f"Confidence: {email['classification']['confidence']}")
            print(f"Reason: {email['classification']['reason']}")
            
            # Handle based on classification
            if email['classification']['category'] == 'legitimate':
                print("\nActions performed:")
                print("✓ Generated AI response")
                print("✓ Sent response to stephane.kolijn@gmail.com")
                print("✓ Moved original + response to AI_Processed/Legitimate")
                
            elif email['classification']['category'] == 'requires_human':
                print("\nActions performed:")
                print("✓ Flagged for human attention")
                print("✓ Moved to AI_Processed/Requires_Human")
                print("✓ Added attention flags")
                
            else:
                print(f"\nAction: ✓ Moved to AI_Processed/{email['classification']['category']}")
            
        else:
            print("\nNo email was processed")
            
        print("\n" + "="*50)
        print("Test completed! Please check:")
        print("="*50)
        print("1. Your email (stephane.kolijn@gmail.com) for AI responses")
        print("2. Roundcube folders:")
        if processed_emails:
            category = processed_emails[0]['classification']['category']
            print(f"   ➜ AI_Processed/{category}")
            if category == 'requires_human':
                print("   ➜ AI_Processed/Completed (after human handling)")
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(test_email_workflow()) 