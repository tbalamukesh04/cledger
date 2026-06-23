from datetime import datetime, timezone
import json
from app.schemas.jobs import WebhookJobPayload

def test_payload_serialization():
    job = WebhookJobPayload(
        job_id="test_job_1",
        tenant_id=1,
        business_id="test_waba",
        phone_number_id="test_phone",
        message_id="wamid.105",
        raw_message_id=105,
        participant_id=42,
        group_id=7,
        message_timestamp=datetime.now(timezone.utc),
        webhook_event_type="text_message",
        ingestion_time=datetime.now(timezone.utc)
    )

    json_string = job.to_json()
    
    parsed_dict = json.loads(json_string)
    assert parsed_dict["raw_message_id"] == 105
    assert "T" in parsed_dict["message_timestamp"] 
