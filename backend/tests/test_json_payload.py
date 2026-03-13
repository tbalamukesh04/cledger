from datetime import datetime, timezone
import json
from app.schemas.jobs import WebhookJobPayload

def test_payload_serialization():
    print("--- Testing Job Payload Serialization ---")
    
    # 1. Create a dummy payload instance
    try:
        job = WebhookJobPayload(
            raw_message_id=105,
            participant_id=42,
            group_id=7,
            message_timestamp=datetime.now(timezone.utc),
            webhook_event_type="text_message",
            ingestion_time=datetime.now(timezone.utc)
        )
        print("✅ Pydantic model instantiated successfully.")
    except Exception as e:
        print(f"❌ Failed to instantiate model: {e}")
        return

    # 2. Serialize to JSON string
    try:
        json_string = job.to_json()
        print(f"✅ Serialized JSON String:\n{json_string}")
        
        # 3. Validate it's a real JSON string by parsing it back
        parsed_dict = json.loads(json_string)
        assert parsed_dict["raw_message_id"] == 105
        assert "T" in parsed_dict["message_timestamp"] # Checking ISO format
        print("✅ JSON structure validated perfectly!")
        
    except Exception as e:
        print(f"❌ Failed during serialization/validation: {e}")

if __name__ == "__main__":
    test_payload_serialization()