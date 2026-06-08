import os
import hmac
import hashlib
import logging

logger = logging.getLogger(__name__)
def verify_whatsapp_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Verifies the HMAC-SHA256 signature of incoming WhatsApp webhooks
    to ensure they originated from Meta and have not been tampered with.
    
    Args:
        raw_body (bytes): The exact raw byte payload of the incoming request.
        signature_header (str): The 'x-hub-signature-256' header value.
        
    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    app_secret = os.getenv("APP_SECRET", "dummy_secret_for_testing")

    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("Security Warning: Missing or malformed signature header")
        return False

    provided_hash = signature_header.split("sha256=")[1]

    computed_hmac = hmac.new(
        key = app_secret.encode('utf-8'),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    is_valid = hmac.compare_digest(provided_hash, computed_hmac)
    
    if not is_valid:
        logger.warning("Security Warning: Invalid signature!! Possible malformed Payload")
    return is_valid