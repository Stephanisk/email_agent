from fastapi import APIRouter, HTTPException
from typing import List, Dict
from app.services.email_client import fetch_latest_emails, EmailClientError

router = APIRouter(prefix="/email", tags=["email"])

@router.get("/test", response_model=List[Dict])
async def test_email_connection():
    """Test endpoint to verify email connection and fetch latest emails."""
    try:
        emails = await fetch_latest_emails(limit=3)
        return emails
    except EmailClientError as e:
        raise HTTPException(status_code=500, detail=str(e)) 