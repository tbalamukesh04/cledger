import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class APISecurityConfig(BaseSettings):
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", 100))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", 60))
    
    MAX_PAGINATION_LIMIT: int = int(os.getenv("MAX_PAGINATION_LIMIT", 200))
    
    MAX_EXPORT_ROWS: int = int(os.getenv("MAX_EXPORT_ROWS", 100000))
    
    MAX_REQUEST_BODY_SIZE: int = int(os.getenv("MAX_REQUEST_BODY_SIZE", 10485760)) # 10MB
    
    model_config = SettingsConfigDict(
        env_file = ".env",
        extra = "ignore"
    )

api_security_settings = APISecurityConfig()