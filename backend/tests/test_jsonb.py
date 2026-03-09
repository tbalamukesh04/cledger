import json
from datetime import datetime, timezone
from app.database.database import SessionLocal

from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages

def test_jsonb_storage():
    db = SessionLocal()

    # Mock WhatsApp webhook payload
    mock_payload = { "object": "whatsapp_business_account",
                    "entry": [ 
                        { "changes": [ 
                            { "value": { "messages": [ 
                                { "from":"260574021221", 
                                "id":"wamid.MSG123", 
                                "timestamp": "1771694280", 
                                "type":"text", 
                                "text": {"body": "2200 per month (2 guards)"}, 
                                "context": { "from": "1203630ABC@g.us" } } ], 
                                "contacts": [ {"profile": {"name":"Mark"}, "wa_id": "260574021221" } ] } } ] } ] }

    try:
        # --- PRE-REQUISITE: Ensure Foreign Key dependencies exist ---
        # 1. Create dummy group if it doesn't exist
        dummy_group = db.query(Groups).filter(Groups.id == 1).first()
        if not dummy_group:
            dummy_group = Groups(group_id="dummy_group_whatsapp_id", groupname="Test Group")
            db.add(dummy_group)
            db.commit()

        # 2. Create dummy participant if it doesn't exist
        dummy_participant = db.query(Participants).filter(Participants.id == 1).first()
        if not dummy_participant:
            dummy_participant = Participants(phone="260574021221", displayname="Mark")
            db.add(dummy_participant)
            db.commit()


        # --- MAIN TEST: Insert RawMessage ---
        # Traverse the nested lists using [0]
        message_data = mock_payload['entry'][0]['changes'][0]['value']['messages'][0]

        # Convert the unix timestamp to a Python datetime object
        dt_received = datetime.fromtimestamp(int(message_data['timestamp']), tz=timezone.utc)

        new_message = RawMessages(
            group_id = dummy_group.id,
            sender_id = dummy_participant.id,
            message_id = message_data['id'],
            received_at = dt_received,
            raw_json = mock_payload,  # Storing the full payload for the retrieval test below
            raw_text = message_data['text']['body'], # Need ['text']['body'] to get actual string
            hash = "e44dcaa4247132d75db62bc8cbeb4f81fc598853ce33e3ed8505e682b260a868" # Shortened for test readability
        )
        db.add(new_message)
        db.commit()
        print("✅ Successfully inserted JSONB payload into raw_messages.")

        # --- RETRIEVAL TEST ---
        # Updated to use the correct attribute `message_id` and the correct ID "wamid.MSG123"
        retrieved_message = db.query(RawMessages).filter(
            RawMessages.message_id == "wamid.MSG123"
        ).first()
        
        # Verify the data remains a structured Python dictionary, proving JSONB works
        extracted_body = retrieved_message.raw_json["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
        print(f"✅ Successfully retrieved JSONB. Extracted text: '{extracted_body}'")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_jsonb_storage()