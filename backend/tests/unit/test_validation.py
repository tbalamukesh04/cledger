from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.database.database import SessionLocal

from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages

import pytest

def test_database_validation_constraints():
    db = SessionLocal()

    try:
        test_group = Groups(group_id="whatsapp_group_999", groupname="Validation Squad")
        test_participant = Participants(phone="9998887776", displayname="Validator User")
        
        db.add(test_group)
        db.add(test_participant)
        db.commit()

        test_message = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id="wamid.VALIDATION_MSG_001",
            received_at=datetime.now(timezone.utc),
            raw_json={"test": "payload"},
            raw_text="This is a validation test message.",
            hash="hash_validation_001"
        )
        db.add(test_message)
        db.commit()

        duplicate_message = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id="wamid.VALIDATION_MSG_001", 
            received_at=datetime.now(timezone.utc),
            raw_json={"test": "payload_duplicate"},
            hash="hash_validation_002"
        )
        db.add(duplicate_message)
        
        with pytest.raises(IntegrityError):
            db.commit()
            
        db.rollback()
        
    finally:
        db.close()
