import json
from datetime import datetime, timezone
from app.database.database import SessionLocal

from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages
import uuid

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
        run_id = uuid.uuid4().hex[:8]
        dummy_group = Groups(group_id=f"grp_{run_id}", groupname="Test Group")
        db.add(dummy_group)
        
        dummy_participant = Participants(phone=f"2605{run_id}", displayname="Mark")
        db.add(dummy_participant)
        db.commit()

        # --- MAIN TEST: Insert RawMessage ---
        message_data = mock_payload['entry'][0]['changes'][0]['value']['messages'][0]
        dt_received = datetime.fromtimestamp(int(message_data['timestamp']), tz=timezone.utc)

        msg_id = f"wamid.MSG_{run_id}"
        new_message = RawMessages(
            group_id = dummy_group.id,
            sender_id = dummy_participant.id,
            message_id = msg_id,
            received_at = dt_received,
            raw_json = mock_payload,
            raw_text = message_data['text']['body'],
            hash = f"hash_{run_id}" 
        )
        db.add(new_message)
        db.commit()

        # --- RETRIEVAL TEST ---
        retrieved_message = db.query(RawMessages).filter(
            RawMessages.message_id == msg_id
        ).first()
        
        assert retrieved_message.raw_text == "2200 per month (2 guards)", "Extracted text does not match expected payload."

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()