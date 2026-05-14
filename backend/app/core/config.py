# pyrefly: ignore [missing-import]
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class APISecurityConfig(BaseSettings):
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", 100))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", 60))
    
    MAX_PAGINATION_LIMIT: int = int(os.getenv("MAX_PAGINATION_LIMIT", 200))
    
    MAX_EXPORT_ROWS: int = int(os.getenv("MAX_EXPORT_ROWS", 100000))
    
    MAX_REQUEST_BODY_SIZE: int = int(os.getenv("MAX_REQUEST_BODY_SIZE", 10485760)) # 10MB
    
    # App Update Metadata Settings
    LATEST_APP_VERSION: str = os.getenv("LATEST_APP_VERSION", "1.0.0")
    LATEST_BUILD_NUMBER: int = int(os.getenv("LATEST_BUILD_NUMBER", 1))
    MIN_REQUIRED_VERSION: str = os.getenv("MIN_REQUIRED_VERSION", "1.0.0")
    FORCE_UPDATE: bool = os.getenv("FORCE_UPDATE", "false").lower() in ("true", "1", "yes")
    APK_DOWNLOAD_URL: str = os.getenv("APK_DOWNLOAD_URL", "https://api.cledger.com/downloads/app-release.apk")
    
    model_config = SettingsConfigDict(
        env_file = ".env",
        extra = "ignore"
    )

api_security_settings = APISecurityConfig()