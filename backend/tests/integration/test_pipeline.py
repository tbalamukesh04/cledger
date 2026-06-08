import os
import json
import hmac
import hashlib
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db, get_redis
from app.models.raw_messages import RawMessages
from app.models.participants import Participants
from app.models.groups import Groups
from app.models.transactions import Transactions, TransactionStatus
from app.models.transaction_audit import TransactionAudit
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.database.redis_client import WEBHOOK_QUEUE_NAME

pytestmark = pytest.mark.integration

os.environ["APP_SECRET"] = "dummy_secret"
os.environ["WHATSAPP_APP_SECRET"] = "dummy_secret"
os.environ["WEBHOOK_SECRET"] = "dummy_secret"
APP_SECRET = "dummy_secret"

def generate_signature(payload_dict: dict, secret: str) -> str:
    """Generates the SHA256 HMAC signature exactly as WhatsApp sends it."""
    payload_bytes = json.dumps(payload_dict, separators=(',', ':')).encode('utf-8')
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def test_webhook_ingestion_isolation(db_session, mock_redis):
    """
    Validates ONLY the ingestion phase: webhook payload -> database RawMessages -> Redis Queue.
    Ensures the front door works independently of the worker pipeline.
    """
    # 1. Dependency Override: Inject our Test Database & Test Redis
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: mock_redis
    
    # 1b. Patch out RateLimiter and IPFilter to prevent background network calls using non-test IPs
    client = TestClient(app)

    try:
        test_run_id = uuid.uuid4().hex[:8]
        phone_num = f"260999{test_run_id[:4]}"
        msg_id = f"wamid.ISOLATE_{test_run_id}"

        # 2. Build Realistic Payload
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1234567890",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "1234567890",
                            "phone_number_id": "1234567890"
                        },
                        "contacts": [{"profile": {"name": "Isolation Tester"}, "wa_id": phone_num}],
                        "messages": [{
                            "from": phone_num,
                            "id": msg_id,
                            "type": "text",
                            "timestamp": str(int(datetime.now().timestamp())),
                            "text": {"body": "This is an isolated ingestion test."}
                        }]
                    }
                }]
            }]
        }

        # 3. Simulate Webhook Post
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        resp = client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={"x-hub-signature-256": generate_signature(payload, APP_SECRET), "Content-Type": "application/json"}
        )

        assert resp.status_code == 200, f"Ingestion failed: {resp.text}"

        # 4. Validate Database Insertion
        db_session.expire_all()
        raw_msg = db_session.query(RawMessages).filter(RawMessages.message_id == msg_id).first()
        
        assert raw_msg is not None, "Raw message was not inserted into the database."
        assert raw_msg.processed is False, "Message should initially be marked as unprocessed."

        # 5. Validate Redis Queue Push
        queue_len = mock_redis.llen(WEBHOOK_QUEUE_NAME)
        assert queue_len == 1, f"Expected exactly 1 job in the queue, found {queue_len}"

        job_data = json.loads(mock_redis.lpop(WEBHOOK_QUEUE_NAME))
        assert job_data["raw_message_id"] == raw_msg.id, "Queue payload does not match the database record ID."
        assert job_data["webhook_event_type"] == "text"

    finally:
        # Always clean up overrides so we don't pollute the next tests
        app.dependency_overrides.clear()

class MockExtractionResult:
    """A lightweight mock of the Pydantic extraction schema for deterministic pipeline testing."""
    def __init__(self, amount, confidence_score):
        self.id = uuid.uuid4().hex
        self.amount = amount
        self.currency = "ZMW"
        self.transaction_verb = "credit"
        self.transaction_date = "2026-03-24"
        self.description = "E2E pipeline test transaction"
        self.confidence_score = confidence_score
        self.confidence = confidence_score

    def model_dump(self, **kwargs):
        return {
            "id": self.id,
            "amount": self.amount,
            "currency": self.currency,
            "transaction_verb": self.transaction_verb,
            "transaction_date": self.transaction_date,
            "description": self.description,
            "confidence_score": self.confidence_score,
            "confidence": self.confidence
        }

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_end_to_end_pipeline_flow(mock_parse, mock_process, mock_cache, db_session, mock_redis, mock_gemini):
    """
    Validates the complete pipeline from webhook payload ingestion via API, queue insertion, 
    scoring, AI extraction, to database and audit persistence.
    """
    # 1. Dependency Override: Inject our Test Database & Test Redis
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: mock_redis
    
    client = TestClient(app)
    
    try:
        # 2. Setup Mock State
        mock_cache.return_value = {}
        mock_process.return_value = "dummy_llm_response"
        test_run_id = uuid.uuid4().hex[:8]
        phone_num = f"260999{test_run_id[:4]}"

        # Helper to construct realistic WhatsApp payloads
        def build_payload(msg_id, text):
            return {
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "1234567890",
                    "changes": [{
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "1234567890"
                            },
                            "contacts": [{"profile": {"name": "E2E Tester"}, "wa_id": phone_num}],
                            "messages": [{
                                "from": phone_num,
                                "id": msg_id,
                                "type": "text",
                                "timestamp": str(int(datetime.now().timestamp())),
                                "text": {"body": text}
                            }]
                        }
                    }]
                }]
            }

        # --- STAGE 1: WEBHOOK INGESTION & SECURITY VALIDATION ---
        
        invalid_payload = build_payload(f"wamid.INVALID_{test_run_id}", "Bad sig message")
        invalid_bytes = json.dumps(invalid_payload, separators=(',', ':')).encode('utf-8')
        resp_invalid = client.post(
            "/api/v1/webhook", 
            content=invalid_bytes, 
            headers={"x-hub-signature-256": "sha256=invalid_signature_123", "Content-Type": "application/json"}
        )
        assert resp_invalid.status_code in [400, 401, 403], f"Security Failed: Expected rejection, got {resp_invalid.status_code} - {resp_invalid.text}"

        # Scenario B: Valid Transaction Request
        txn_msg_id = f"wamid.TXN_{test_run_id}"
        txn_payload = build_payload(txn_msg_id, "I paid John 500 ZMW for groceries.")
        txn_bytes = json.dumps(txn_payload, separators=(',', ':')).encode('utf-8')
        resp_txn = client.post(
            "/api/v1/webhook",
            content=txn_bytes,
            headers={"x-hub-signature-256": generate_signature(txn_payload, APP_SECRET), "Content-Type": "application/json"}
        )
        assert resp_txn.status_code == 200, f"Valid payload failed: {resp_txn.text}"

        # Scenario C: Valid Chat Request
        chat_msg_id = f"wamid.CHAT_{test_run_id}"
        chat_payload = build_payload(chat_msg_id, "Hey man, what time are we meeting?")
        chat_bytes = json.dumps(chat_payload, separators=(',', ':')).encode('utf-8')
        resp_chat = client.post(
            "/api/v1/webhook", 
            content=chat_bytes, 
            headers={"x-hub-signature-256": generate_signature(chat_payload, APP_SECRET), "Content-Type": "application/json"}
        )
        assert resp_chat.status_code == 200, f"Chat payload failed: {resp_chat.text}"

        # --- STAGE 2: QUEUE CONSUMPTION ---
        batch_jobs = []
        while True:
            result = mock_redis.rpop(WEBHOOK_QUEUE_NAME)
            if not result:
                break
            batch_jobs.append(WebhookJobPayload(**json.loads(result)))

        # 1 invalid was blocked, 2 valid were pushed
        assert len(batch_jobs) == 2, f"Expected 2 jobs in queue, got {len(batch_jobs)}"

        # --- STAGE 3: WORKER PROCESSING ---
        db_session.expire_all()
        msg_txn = db_session.query(RawMessages).filter(RawMessages.message_id == txn_msg_id).first()
        msg_chat = db_session.query(RawMessages).filter(RawMessages.message_id == chat_msg_id).first()

        assert msg_txn is not None, "Transaction raw message not persisted by webhook!"
        assert msg_chat is not None, "Chat raw message not persisted by webhook!"

            # LIFECYCLE TRANSITION VALIDATION (Pre-Worker)
        assert msg_txn.processed is False, "Lifecycle Error: Message should be un-processed before worker execution."
        assert db_session.query(Transactions).filter(Transactions.raw_message_id == msg_txn.id).count() == 0, "Lifecycle Error: Transaction should not exist yet."

        # Map the AI parser to successfully "extract" only the valid message
        mock_parse.return_value = {str(msg_txn.id): MockExtractionResult(amount=500.0, confidence_score=0.98)}

        # Execute the worker block synchronously
        results = process_webhook_batch(batch_jobs)

       # --- STAGE 4: STATE VALIDATION ---

        # 1. Validate Non-Transaction (Scoring engine bypasses AI)
        updated_chat = db_session.query(RawMessages).filter(RawMessages.message_id == chat_msg_id).first()
        assert updated_chat.processed is True
        assert updated_chat.is_transaction is False
        assert updated_chat.processing_status == "NON_TRANSACTION"
        assert db_session.query(Transactions).filter(Transactions.raw_message_id == updated_chat.id).count() == 0

        # 2. Validate Valid Transaction (Successfully routed and parsed)
        updated_txn = db_session.query(RawMessages).filter(RawMessages.message_id == txn_msg_id).first()
        assert updated_txn.processed is True
        assert updated_txn.is_transaction is True
        assert updated_txn.processing_status == "success"

        # 3. Validate Transaction Persistence
        txn_record = db_session.query(Transactions).filter(Transactions.raw_message_id == updated_txn.id).first()
        assert txn_record is not None
        assert float(txn_record.amount) == 500.0
        assert txn_record.currency == "ZMW"
        assert txn_record.status == TransactionStatus.PARSED

        # 4. Validate Audit Persistence
        audit_record = db_session.query(TransactionAudit).filter(TransactionAudit.transaction_id == txn_record.id).first()
        assert audit_record is not None
        assert str(audit_record.action).lower().endswith("created")
        assert audit_record.old_value is None, f"Expected old_value to be None for creation, got {audit_record.old_value}"
        assert float(audit_record.new_value["amount"]) == 500.0
        assert audit_record.actor_identifier == "system"

        # --- STAGE 5: FAILURE VISIBILITY & SYSTEM HEALTH CHECKS ---
        
        # 1. Verify no unprocessed jobs remain (Queue is clean)
        remaining_jobs = mock_redis.llen(WEBHOOK_QUEUE_NAME)
        assert remaining_jobs == 0, f"Silent Failure Check: Expected empty queue, found {remaining_jobs} dangling jobs."

        # 2. Verify no partial/abandoned message states
        unprocessed_msgs = db_session.query(RawMessages).filter(
            RawMessages.message_id.in_([txn_msg_id, chat_msg_id]),
            RawMessages.processed == False
        ).all()
        assert len(unprocessed_msgs) == 0, f"Silent Failure Check: Found {len(unprocessed_msgs)} messages left unprocessed."

        # 3. Verify absolute transaction counts (No duplicates or partial ghost writes)
        total_test_txns = db_session.query(Transactions).filter(
            Transactions.raw_message_id.in_([updated_txn.id, updated_chat.id])
        ).count()
        assert total_test_txns == 1, f"Data Integrity Check: Expected exactly 1 mapped transaction, found {total_test_txns}."

    finally:
        # Always clean up overrides so we don't pollute other tests
        app.dependency_overrides.clear()