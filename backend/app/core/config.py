from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    rd_api_token: str
    database_url: str = "sqlite:///./data/rdtm.db"
    log_level: str = "INFO"
    media_path: str = "/medias"
    max_retry_attempts: int = 3
    
    class Config:
        env_file = ".env"

settings = Settings()