from fastapi import APIRouter

router = APIRouter()

@router.post("/webhook", tags=["Webhook"])
async def handle_webhook():
    """Endpoint to receive incoming webhooks."""
    return {"message": "Webhook endpoint ready"}