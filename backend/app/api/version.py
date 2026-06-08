from fastapi import APIRouter
from app.schemas.update_metadata import UpdateMetadataResponse
from app.core.config import api_security_settings

router = APIRouter(tags=["Version"])

@router.get(
    "/app/version", 
    response_model=UpdateMetadataResponse, 
    summary="Retrieve application update metadata"
)
async def get_app_version() -> UpdateMetadataResponse:
    """
    Publicly accessible endpoint returning stable update metadata for mobile clients.
    Bypasses all authentication and session checks to allow client applications 
    to verify version constraints and update availability immediately upon launch.
    """
    return UpdateMetadataResponse(
        latest_version=api_security_settings.LATEST_APP_VERSION,
        build_number=api_security_settings.LATEST_BUILD_NUMBER,
        min_required_version=api_security_settings.MIN_REQUIRED_VERSION,
        force_update=api_security_settings.FORCE_UPDATE,
        download_url=api_security_settings.APK_DOWNLOAD_URL,
        release_notes=["Initial MVP release"]
    )