import logging
import httpx
from fastapi import HTTPException
from app.core.config import api_security_settings
from app.utils.logger import log_event, log_error
from app.core.log_events import LogEvent

logger = logging.getLogger(__name__)

class MetaAuthService:
    """
    Dedicated service layer for handling Meta Graph API interactions, 
    token exchanges, and WABA subscription operations.
    """
    
    def __init__(self):
        self.base_url = f"https://graph.facebook.com/{api_security_settings.META_GRAPH_VERSION}"
        self.client_id = api_security_settings.META_APP_ID
        self.client_secret = api_security_settings.META_APP_SECRET

    async def exchange_code_for_short_lived_token(self, auth_code: str) -> str:
        """Exchanges the temporary authorization code for a short-lived user access token."""
        url = f"{self.base_url}/oauth/access_token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": auth_code
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                log_event(LogEvent.SYSTEM_ERROR, "Meta OAuth short-lived token exchange failed", response=response.text)
                raise HTTPException(status_code=400, detail="Failed to exchange Meta authorization code.")
            
            return response.json().get("access_token")

    async def exchange_for_long_lived_token(self, short_lived_token: str) -> str:
        """Upgrades a short-lived user access token into a long-lived access token."""
        url = f"{self.base_url}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "fb_exchange_token": short_lived_token
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                log_event(LogEvent.SYSTEM_ERROR, "Meta long-lived token exchange failed", response=response.text)
                raise HTTPException(status_code=400, detail="Failed to upgrade to long-lived Meta token.")
            
            return response.json().get("access_token")

    async def process_tenant_onboarding(self, auth_code: str) -> str:
        """
        Executes the Meta OAuth authorization code exchange protocol.
        Returns the upgraded long-lived access token.
        """
        log_event(LogEvent.WEBHOOK_RECEIVED, "Executing Meta authorization code exchange.")
        
        short_token = await self.exchange_code_for_short_lived_token(auth_code)
        long_token = await self.exchange_for_long_lived_token(short_token)
        
        return long_token
