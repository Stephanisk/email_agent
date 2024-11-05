from pydantic_settings import BaseSettings
from functools import lru_cache

class EmailSettings(BaseSettings):
    EMAIL_HOST: str
    EMAIL_ADDRESS: str
    EMAIL_PASSWORD: str
    IMAP_PORT: int = 993
    SMTP_PORT: int = 587

    class Config:
        env_file = ".env"

@lru_cache()
def get_email_settings() -> EmailSettings:
    return EmailSettings() 