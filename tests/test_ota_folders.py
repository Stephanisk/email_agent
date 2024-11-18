import asyncio
from app.services.email_client import EmailClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def test_ota_folder_creation():
    """Test creation of OTA folder structure."""
    try:
        logger.info("\n" + "="*80)
        logger.info("Testing OTA Folder Creation")
        logger.info("="*80)
        
        email_client = EmailClient()
        
        # First list existing folders
        mail = await email_client.connect_imap()
        _, list_response = mail.list()
        existing_folders = [f.decode().split('"')[-1].strip() for f in list_response if f]
        
        logger.info("\nExisting folders before creation:")
        for folder in existing_folders:
            logger.info(f"- {folder}")
            
        # Create OTA folder structure
        ota_folders = [
            "AI_Processed/OTA",
            "AI_Processed/OTA/Booking",
            "AI_Processed/OTA/Hostelworld",
            "AI_Processed/OTA/FDM",
            "AI_Processed/OTA/Expedia"
        ]
        
        logger.info("\nCreating OTA folders...")
        for folder in ota_folders:
            try:
                mail.create(f'"{folder}"')
                mail.subscribe(f'"{folder}"')  # Subscribe to make visible in RoundCube
                logger.info(f"Created and subscribed to folder: {folder}")
            except Exception as e:
                logger.info(f"Folder exists or error: {folder} ({str(e)})")
                
        # Verify folders after creation
        _, list_response = mail.list()
        final_folders = [f.decode().split('"')[-1].strip() for f in list_response if f]
        
        logger.info("\nFinal folder list:")
        for folder in final_folders:
            logger.info(f"- {folder}")
            
        # Verify OTA folders exist
        missing_folders = [f for f in ota_folders if f not in final_folders]
        if missing_folders:
            logger.error("\nSome folders were not created:")
            for folder in missing_folders:
                logger.error(f"- {folder}")
        else:
            logger.info("\nAll OTA folders created successfully!")
            
    except Exception as e:
        logger.error(f"Error during test: {str(e)}")
    finally:
        try:
            mail.logout()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_ota_folder_creation()) 