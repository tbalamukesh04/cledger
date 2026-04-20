from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.database.database import SessionLocal

from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages

import pytest

import uuid
def test_database_validation_constraints():
    db = SessionLocal()
    run_id = uuid.uuid4().hex[:8]

    try:
        test_group = Groups(group_id=f"grp_{run_id}", groupname="Validation Squad")
        test_participant = Participants(phone=f"999{run_id}", displayname="Validator User")
        
        db.add(test_group)
        db.add(test_participant)
        db.commit()

        test_message = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id=f"wamid.VAL_{run_id}",
            received_at=datetime.now(timezone.utc),
            raw_json={"test": "payload"},
            raw_text="This is a validation test message.",
            hash=f"hash_1_{run_id}"
        )
        db.add(test_message)
        db.commit()

        duplicate_message = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id=f"wamid.VAL_{run_id}", 
            received_at=datetime.now(timezone.utc),
            raw_json={"test": "payload_duplicate"},
            hash=f"hash_2_{run_id}"
        )
        db.add(duplicate_message)
        
        with pytest.raises(IntegrityError):
            db.commit()
            
        db.rollback()
        
    finally:
        db.close()
