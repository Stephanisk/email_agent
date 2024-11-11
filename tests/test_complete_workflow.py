import asyncio
import pytest
from app.services.email_workflow import EmailWorkflow
from app.services.classification.models import MainCategory, HumanAttentionCategory

@pytest.mark.asyncio
async def test_complete_workflow():
    workflow = EmailWorkflow()
    
    test_emails = [
        {
            "id": "test1",
            "subject": "Room availability for next week",
            "from": "guest@example.com",
            "to": "hotel@example.com",
            "body": "Hello, I would like to know if you have any rooms available next week.",
            "attachments": [],
            "date": "2024-03-20"
        },
        {
            "id": "test2",
            "subject": "Dringende Kennisgeving: Belastingcontrole",
            "from": "inspectie@belastingdienst.be",
            "to": "hotel@example.com",
            "body": "Geachte heer/mevrouw, Bij deze delen wij u mede...",
            "attachments": ["doc1.pdf"],
            "date": "2024-03-20"
        },
        # Add more test cases here...
    ]
    
    print("\n" + "="*50)
    print("Starting Complete Workflow Test")
    print("="*50)
    
    for email in test_emails:
        print(f"\nProcessing email: {email['subject']}")
        result = await workflow.process_email(email)
        
        print(f"Classification: {result['classification']['main_category']}")
        if result['classification'].get('sub_category'):
            print(f"Sub-category: {result['classification']['sub_category']}")
        print(f"Language detected: {result['language']}")
        print(f"Successfully processed: {result['processed']}")
        print("-"*50)
        
        # Assertions
        assert result['processed'] == True
        assert 'classification' in result
        assert 'language' in result

if __name__ == "__main__":
    asyncio.run(test_complete_workflow()) 