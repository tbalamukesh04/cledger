import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.businesses import Businesses
from app.core.config import api_security_settings
from app.utils.logger import log_event, log_error
from app.core.log_events import LogEvent

logger = logging.getLogger(__name__)

class WABASubscriptionService:
    """
    Dedicated service for managing the lifecycle of WABA webhook subscriptions.
    Handles persistence of operational states, idempotency, and diagnostics.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.base_url = f"https://graph.facebook.com/{api_security_settings.META_GRAPH_VERSION}"

    async def subscribe_waba(self, tenant_id: int, waba_id: str, access_token: str) -> bool:
        """
        Idempotently subscribes the given WABA to the platform's webhook integration.
        Persists detailed state back to the businesses tenant row.
        """
        business = self.db.query(Businesses).filter(Businesses.id == tenant_id).first()
        if not business:
            log_event(LogEvent.SYSTEM_ERROR, "Subscription aborted: Tenant ID not resolved.", tenant_id=tenant_id)
            return False

        if business.waba_subscription_status == "subscribed":
            log_event(LogEvent.WEBHOOK_RECEIVED, "WABA already marked as subscribed; executing idempotent refresh.", waba_id=waba_id)

        business.waba_subscription_status = "pending"
        self.db.commit()

        url = f"{self.base_url}/{waba_id}/subscribed_apps"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers)
                
                business.waba_last_subscription_check = datetime.now(timezone.utc)
                
                # Meta returns {"success": true} on successful subscription execution
                if response.status_code == 200 and response.json().get("success"):
                    business.waba_subscription_status = "subscribed"
                    business.waba_subscription_timestamp = datetime.now(timezone.utc)
                    business.waba_subscription_error = None
                    self.db.commit()
                    
                    log_event(LogEvent.WEBHOOK_RECEIVED, "WABA successfully subscribed to platform webhooks.", waba_id=waba_id, tenant_id=tenant_id)
                    return True
                else:
                    error_detail = response.text
                    business.waba_subscription_status = "failed"
                    business.waba_subscription_error = error_detail
                    self.db.commit()
                    
                    log_event(LogEvent.SYSTEM_ERROR, "Meta WABA subscription execution failed", response=error_detail, waba_id=waba_id, tenant_id=tenant_id)
                    return False
                    
        except httpx.RequestError as exc:
            business.waba_subscription_status = "failed"
            business.waba_subscription_error = f"Network Transport Error: {str(exc)}"
            self.db.commit()
            
            log_error(LogEvent.SYSTEM_ERROR, error=exc, message="Network timeout or resolution error during WABA subscription API sequence.")
            return False