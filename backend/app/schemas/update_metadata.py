# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import datetime

class UpdateMetadataResponse(BaseModel):
    """
    Defines the standardized schema for mobile application version tracking
    and update availability metadata.
    """
    latest_version: str = Field(
        ..., 
        description="The latest semantic version string available (e.g., '1.0.0').",
        examples=["1.0.0"]
    )
    build_number: int = Field(
        ..., 
        description="The monotonic integer build identifier.",
        examples=[1]
    )
    min_required_version: str = Field(
        ..., 
        description="The minimum semantic version required to continue operating safely.",
        examples=["1.0.0"]
    )
    force_update: bool = Field(
        ..., 
        description="Flag indicating if the client must forcefully block access until updated."
    )
    download_url: HttpUrl = Field(
        ..., 
        description="Direct, secure HTTPS link to download the latest APK artifact.",
        examples=["https://api.cledger.com/downloads/app-release.apk"]
    )
    release_notes: List[str] = Field(
        ..., 
        description="Array of string logs detailing the structural updates and bug fixes.",
        examples=[["Initial MVP release"]]
    )
    release_timestamp: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        description="ISO 8601 timestamp tracking when the target version artifact was published."
    )