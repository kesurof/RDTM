import os
from typing import Optional
from pydantic import BaseSettings, validator

class RDTMSettings(BaseSettings):
    # Real-Debrid Configuration
    rd_api_key: str
    rd_base_url: str = "https://api.real-debrid.com/rest/1.0"
    
    # Database Configuration
    database_url: str = "sqlite:///./rdtm.db"
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # Torrent Configuration
    max_concurrent_torrents: int = 10
    torrent_check_interval: int = 30
    auto_delete_completed: bool = True
    
    # Download Configuration
    download_path: str = "./downloads"
    temp_path: str = "./temp"
    
    # Security
    secret_key: str
    access_token_expire_minutes: int = 30
    
    @validator('rd_api_key')
    def validate_api_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError('Clé API Real-Debrid invalide')
        return v
    
    @validator('download_path', 'temp_path')
    def validate_paths(cls, v):
        os.makedirs(v, exist_ok=True)
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = RDTMSettings()
