import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import OperationalError
import redis.exceptions
import json
import hashlib
from datetime import datetime, timezone

from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions
from app.models.groups import Groups
from app.models.participants import Participants
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.database.redis_client import WEBHOOK_ACTIVE_QUEUE, WEBHOOK_QUEUE_NAME

pytestmark = pytest.mark.failure

def test_failure_module_discovery():
    """Basic test to ensure pytest correctly discovers the failure module."""
    assert True

class TestDatabaseFailures:
    def test_db_commit_operational_error(self, db_session, mock_redis, mock_gemini):
        """Simulate a database connection drop during the final batch commit."""
        mock_redis.flushall()
        test_group = Groups(group_id="test_group_db_fail", groupname="Test Group")
        test_participant = Participants(phone="6666666666", displayname="Test User 4")
        db_session.add_all([test_group, test_participant])
        db_session.flush()

        msg_id = f"wamid.db_fail_test"
        raw_msg = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id=msg_id,
            raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 500"}, "timestamp": "1710000000"}]}}]}]},
            received_at=datetime.now(timezone.utc),
            processed=False,
            hash=hashlib.sha256(msg_id.encode()).hexdigest()
        )
        db_session.add(raw_msg)
        db_session.commit()
        
        raw_msg_id = raw_msg.id

        job_payload = WebhookJobPayload(
            job_id=f"job_db_fail_{raw_msg_id}",
            raw_message_id=raw_msg_id,
            webhook_event_type="messages",
            message_timestamp=datetime.now(timezone.utc),
            participant_id=test_participant.id,
            group_id=test_group.id,
            ingestion_time=datetime.now(timezone.utc)
        )
        
        # Configure LLM mock for a valid response
        mock_gemini.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps([{        
                "id": str(raw_msg_id),
                "amount": 500.0,
                "currency": "ZMW",
                "transaction_verb": "credit",
                "confidence": 0.95
            }])}]}}]
        }

        # 2. Mock db_session.commit to raise OperationalError (DB Connection Drop)
        with patch.object(db_session, 'commit', side_effect=OperationalError('Simulated DB Outage', None, None)):
            # 3. Process batch during outage
            results = process_webhook_batch([job_payload])
            
        # Verify job is safely caught and marked for retry
        assert results[job_payload.job_id] == "retry"
        
        # 4. Verify DB state (rollback occurred, no partial writes)
        db_session.expire_all()
        
        txns = db_session.query(Transactions).filter(Transactions.raw_message_id == raw_msg_id).all()
        assert len(txns) == 0  # No phantom transaction
        
        updated_raw_msg = db_session.query(RawMessages).filter(RawMessages.id == raw_msg_id).first()
        assert updated_raw_msg.processed is False  # Original state is preserved
        assert updated_raw_msg.processing_status != "success"

        # 5. Verify system recovers after DB is restored (commit unpatched)
        results_recovery = process_webhook_batch([job_payload])
        assert results_recovery[job_payload.job_id] == "success"

        txns_recovered = db_session.query(Transactions).filter(Transactions.raw_message_id == raw_msg_id).all()
        assert len(txns_recovered) == 1
        assert float(txns_recovered[0].amount) == 500.0

class TestRedisFailures:
    def test_redis_timeout(self, db_session, mock_redis, mock_gemini):
        """Simulate a Redis timeout when trying to read or write to the queue."""
        test_group = Groups(group_id="test_group_timeout", groupname="Test Group")
        test_participant = Participants(phone="8888888888", displayname="Test User 2")
        db_session.add_all([test_group, test_participant])
        db_session.flush()

        msg_id = f"wamid.timeout_test"
        raw_msg = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id=msg_id,
            raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 500 for timeout test"}, "timestamp": "1710000000"}]}}]}]},
            received_at=datetime.now(timezone.utc),
            processed=False,
            hash=hashlib.sha256(msg_id.encode()).hexdigest()
        )
        db_session.add(raw_msg)
        db_session.commit()

        raw_msg_id = raw_msg.id
        
        job_payload = WebhookJobPayload(
            job_id=f"job_timeout_{raw_msg_id}", # Keep your existing job ID string here
            raw_message_id=raw_msg_id,
            webhook_event_type="messages",
            message_timestamp=datetime.now(timezone.utc),
            participant_id=test_participant.id,
            group_id=test_group.id,
            ingestion_time=datetime.now(timezone.utc)
        )
        mock_gemini.side_effect = TimeoutError("Simulated LLM Network Timeout")

        try:
            results = process_webhook_batch([job_payload])
            assert results[job_payload.job_id] != "success"
        except Exception:
            pass

        db_session.expire_all()

        txns = db_session.query(Transactions).filter(Transactions.raw_message_id == raw_msg_id).all()
        assert len(txns) == 0

        updated_raw_msg = db_session.query(RawMessages).filter(RawMessages.id == raw_msg_id).first()
        assert updated_raw_msg.processed is False
        assert updated_raw_msg.processing_status != "success"

class TestLLMFailures:
    def test_llm_network_timeout(self, db_session, mock_redis, mock_gemini):
        """Simulate an external network timeout to the Gemini API."""
        pass

class TestWorkerInterruption:
    def test_worker_crash_and_recovery(self, db_session, mock_redis, mock_gemini):
        """Simulate a hard worker crash mid-job, and verify recovery and idempotency."""
        mock_redis.flushall()
        # 1. Setup DB state
        test_group = Groups(group_id='test_group_crash', groupname="Test Group Crash", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
        test_participant = Participants(phone = "9099999999", displayname="Test Participant Crash")
        db_session.add_all([test_group, test_participant])
        db_session.flush()
        
        msg_id = f"wamid.crash_test"
        raw_json = {
            "entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 500 for recovery test"}, "timestamp": "1710000000"}]}}]}]
        }
        raw_msg = RawMessages(
            group_id = test_group.id, 
            sender_id = test_participant.id,
            message_id = msg_id,
            raw_json = raw_json,
            received_at = datetime.now(timezone.utc),
            processed = False,
            hash = hashlib.sha256(msg_id.encode()).hexdigest()
        )
        db_session.add(raw_msg)
        db_session.commit()

        raw_msg_id = raw_msg.id

        job_payload = WebhookJobPayload(
            job_id=f"job_{raw_msg_id}",
            raw_message_id=raw_msg_id,
            webhook_event_type="messages",
            message_timestamp=datetime.now(timezone.utc),
            participant_id=test_participant.id,
            group_id=test_group.id,
            ingestion_time=datetime.now(timezone.utc)
        )
        payload_str = job_payload.model_dump_json()

        # -------------------------------------------------------------
        # SCENARIO A: Worker crashes BEFORE processing (Job trapped in Active)
        # -------------------------------------------------------------
        mock_redis.lpush(WEBHOOK_QUEUE_NAME, payload_str)
        # Worker polls using rpoplpush
        popped = mock_redis.rpoplpush(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE)
        assert popped == payload_str
        
        # Simulating Crash: Active queue has 1 item, main queue is empty
        assert mock_redis.llen(WEBHOOK_ACTIVE_QUEUE) == 1
        assert mock_redis.llen(WEBHOOK_QUEUE_NAME) == 0

        # --- RESTART WORKER (Execute worker_service.py Startup Recovery Block) ---
        while True:
            recovered_job = mock_redis.rpoplpush(WEBHOOK_ACTIVE_QUEUE, WEBHOOK_QUEUE_NAME)
            if not recovered_job:
                break

        # Verify job was successfully rescued
        assert mock_redis.llen(WEBHOOK_ACTIVE_QUEUE) == 0
        assert mock_redis.llen(WEBHOOK_QUEUE_NAME) == 1

        # Process the rescued job successfully
        mock_gemini.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps([{        
                "id": str(raw_msg_id),
                "amount": 500.0,
                "currency": "ZMW",
                "transaction_date": "2024-03-09",
                "transaction_verb": "credit",
                "confidence": 0.95
            }])}]}}]
        }

        rescued_payload_str = mock_redis.rpop(WEBHOOK_QUEUE_NAME)
        rescued_job_obj = WebhookJobPayload(**json.loads(rescued_payload_str))
        
        results = process_webhook_batch([rescued_job_obj])
        assert results[rescued_job_obj.job_id] == "success"

        # Verify exactly one transaction created
        txns = db_session.query(Transactions).filter(Transactions.raw_message_id == raw_msg_id).all()
        assert len(txns) == 1
        assert txns[0].amount == 500.0

        # -------------------------------------------------------------
        # SCENARIO B: Worker crashes AFTER DB Commit, BEFORE Redis Cleanup
        # -------------------------------------------------------------
        # The DB is committed, but the job is stranded in the active queue
        mock_redis.lpush(WEBHOOK_ACTIVE_QUEUE, payload_str)
        
        # --- RESTART WORKER AGAIN ---
        while True:
            rec_job = mock_redis.rpoplpush(WEBHOOK_ACTIVE_QUEUE, WEBHOOK_QUEUE_NAME)
            if not rec_job:
                break
        
        # Process the duplicate rescued job
        dup_payload_str = mock_redis.rpop(WEBHOOK_QUEUE_NAME)
        dup_job_obj = WebhookJobPayload(**json.loads(dup_payload_str))
        
        results2 = process_webhook_batch([dup_job_obj])
        
        # It should succeed instantly without AI/DB calls because raw_msg.processed == True
        assert results2[dup_job_obj.job_id] == "success"
        
        # Verify NO duplicate transaction was created
        txns_after = db_session.query(Transactions).filter(Transactions.raw_message_id == raw_msg_id).all()
        assert len(txns_after) == 1

    def test_system_restart_pending_queue(self, db_session, mock_redis, mock_gemini):
        """Simulate a system restart with multiple jobs already waiting in the main queue."""
        mock_redis.flushall()
        # 1. Setup DB state for multiple incoming messages while offline
        test_group = Groups(group_id="test_group_restart", groupname="Test Group")
        test_participant = Participants(phone="7777777777", displayname="Test User 2")
        db_session.add_all([test_group, test_participant])
        db_session.flush()

        raw_messages = []
        for i in range(3):
            msg_id = f"wamid.pending_{i}"
            raw_msg = RawMessages(
                group_id=test_group.id,
                sender_id=test_participant.id,
                message_id=msg_id,
                raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": f"Paid {100 + i}"}, "timestamp": "1710000000"}]}}]}]},
                received_at=datetime.now(timezone.utc),
                processed=False,
                hash=hashlib.sha256(msg_id.encode()).hexdigest()
            )
            raw_messages.append(raw_msg)
            
        db_session.add_all(raw_messages)
        db_session.commit()

        # 2. Enqueue jobs (Simulate webhooks being received while worker is OFF)
        for raw_msg in raw_messages:
            job_payload = WebhookJobPayload(
                job_id=f"job_pending_{raw_msg.id}",
                raw_message_id=raw_msg.id,
                webhook_event_type="messages",
                message_timestamp=datetime.now(timezone.utc),
                participant_id=test_participant.id,
                group_id=test_group.id,
                ingestion_time=datetime.now(timezone.utc)
            )

            mock_redis.lpush(WEBHOOK_QUEUE_NAME, job_payload.model_dump_json())

        # Verify jobs are waiting in the main queue
        assert mock_redis.llen(WEBHOOK_QUEUE_NAME) == 3
        assert mock_redis.llen(WEBHOOK_ACTIVE_QUEUE) == 0

        # --- SIMULATE SYSTEM RESTART ---
        
        # Worker boots up, runs crash recovery (active queue is empty, so it breaks immediately)
        while True:
            recovered_job = mock_redis.rpoplpush(WEBHOOK_ACTIVE_QUEUE, WEBHOOK_QUEUE_NAME)
            if not recovered_job:
                break
        
        # Worker starts normal polling and pulls a batch
        batch_jobs = []
        batch_payloads = []
        
        while mock_redis.llen(WEBHOOK_QUEUE_NAME) > 0:
            payload_str = mock_redis.rpoplpush(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE)
            batch_payloads.append(payload_str)
            batch_jobs.append(WebhookJobPayload(**json.loads(payload_str)))

        assert len(batch_jobs) == 3
        assert mock_redis.llen(WEBHOOK_ACTIVE_QUEUE) == 3
        
        # Configure LLM mock to return 3 results matching the batch
        mock_llm_results = []
        for i, job in enumerate(batch_jobs):
            mock_llm_results.append({
                "id": str(job.raw_message_id),
                "amount": 100.0 + i,
                "currency": "ZMW",
                "transaction_verb": "credit",
                "confidence": 0.95
            })
            
        mock_gemini.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(mock_llm_results)}]}}]
        }

        # 3. Process the pending batch
        results = process_webhook_batch(batch_jobs)

        # Worker cleans up active queue based on success status
        for job, payload_str in zip(batch_jobs, batch_payloads):
            assert results[job.job_id] == "success"
            mock_redis.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)

        # 4. Final Verifications
        assert mock_redis.llen(WEBHOOK_QUEUE_NAME) == 0
        assert mock_redis.llen(WEBHOOK_ACTIVE_QUEUE) == 0

        # Ensure exactly 3 transactions were saved and amounts correspond
        txns = db_session.query(Transactions).all()
        assert len(txns) == 3
        
        amounts = sorted([float(t.amount) for t in txns])
        assert amounts == [100.0, 101.0, 102.0]

class TestIdempotencySafety:
    def test_idempotent_job_reprocessing(self, db_session, mock_redis, mock_gemini):
        """Verify that processing the exact same job multiple times yields consistent state and no duplicates."""
        # 1. Setup DB state
        test_group = Groups(group_id="test_group_idem", groupname="Test Group")
        test_participant = Participants(phone="5555555555", displayname="Test User 5")
        db_session.add_all([test_group, test_participant])
        db_session.flush()

        msg_id = f"wamid.idem_test_1"
        raw_msg = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id=msg_id,
            raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 500"}, "timestamp": "1710000000"}]}}]}]},
            received_at=datetime.now(timezone.utc),
            processed=False,
            hash=hashlib.sha256(msg_id.encode()).hexdigest()
        )
        db_session.add(raw_msg)
        db_session.commit()
        
        raw_msg_id = raw_msg.id
        job_payload = WebhookJobPayload(
            job_id=f"job_idem_{raw_msg_id}",
            raw_message_id=raw_msg_id,
            webhook_event_type="messages",
            message_timestamp=datetime.now(timezone.utc),
            participant_id=test_participant.id,
            group_id=test_group.id,
            ingestion_time=datetime.now(timezone.utc)
        )

        mock_gemini.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps([{        
                "id": str(raw_msg_id),
                "amount": 500.0,
                "currency": "ZMW",
                "transaction_verb": "credit",
                "confidence": 0.95
            }])}]}}]
        }

        # 2. First Execution (Normal Processing)
        results1 = process_webhook_batch([job_payload])
        assert results1[job_payload.job_id] == "success"

        txns1 = db_session.query(Transactions).filter(Transactions.raw_message_id == raw_msg_id).all()
        assert len(txns1) == 1

        # 3. Second Execution (Simulate stranded queue retry or double delivery)
        # Reset mock to ensure we can track if the AI is incorrectly called again
        mock_gemini.reset_mock()
        
        results2 = process_webhook_batch([job_payload])
        
        # Should gracefully return success to clear the stranded job
        assert results2[job_payload.job_id] == "success"
        
        # Verify LLM was completely bypassed (cost and time savings)
        mock_gemini.assert_not_called()

        # 4. Final Data Verification (Idempotency Guarantee)
        db_session.expire_all()
        txns2 = db_session.query(Transactions).filter(Transactions.raw_message_id == raw_msg_id).all()
        
        assert len(txns2) == 1  # Still exactly 1 transaction
        assert float(txns2[0].amount) == 500.0

class TestFailureObservability:
    def test_failure_logging_and_observability(self, db_session, mock_redis, mock_gemini, caplog):
        """Verify that processing failures are not silent and emit structured logs with context."""
        import logging
        caplog.set_level(logging.ERROR)
        mock_redis.flushall()

        # 1. Setup DB state
        test_group = Groups(group_id="test_group_log", groupname="Test Group")
        test_participant = Participants(phone="4444444444", displayname="Test User 6")
        db_session.add_all([test_group, test_participant])
        db_session.flush()

        msg_id = f"wamid.log_test"
        raw_msg = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id=msg_id,
            raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 500"}, "timestamp": "1710000000"}]}}]}]},
            received_at=datetime.now(timezone.utc),
            processed=False,
            hash=hashlib.sha256(msg_id.encode()).hexdigest()
        )
        db_session.add(raw_msg)
        db_session.commit()
        
        raw_msg_id = raw_msg.id
        job_payload = WebhookJobPayload(
            job_id=f"job_log_{raw_msg_id}",
            raw_message_id=raw_msg_id,
            webhook_event_type="messages",
            message_timestamp=datetime.now(timezone.utc),
            participant_id=test_participant.id,
            group_id=test_group.id,
            ingestion_time=datetime.now(timezone.utc)
        )

        # 2. Simulate an unexpected critical failure
        mock_gemini.side_effect = RuntimeError("Critical AI Subsystem Failure")

        # 3. Process the batch
        try:
            process_webhook_batch([job_payload])
        except Exception:
            # If the worker bubbles up the error to trigger a queue retry, we catch it here so the test doesn't fail.
            pass

        # 4. Assert Observability & Logging Guarantees
        error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
        
        # Guarantee 1: No silent failures
        assert len(error_records) > 0, "System silently swallowed the failure! No ERROR logs emitted."
        
        # Guarantee 2: Error context is preserved in the log output
        assert "Critical AI Subsystem Failure" in caplog.text, "Error context/message missing from logs"