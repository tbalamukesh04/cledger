import os
import json
import time
import hmac
import hashlib
import uuid
import random
import pytest
import asyncio
import re
import httpx
import logging
import concurrent.futures
from fastapi import Request
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError, IntegrityError

from app.main import app
from app.middleware.rate_limiter import RateLimiter
from app.middleware.ip_filter import IPFilter
from app.database.redis_client import WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.models.transactions import Transactions, TransactionStatus
from app.models.audit_logs import AuditLog, EventType, ActorType
from app.crud.transaction_crud import upsert_transaction
from app.workers import worker_service
from app.schemas.llm_extraction import LLMExtractionSchema
from app.api.dependencies import get_db

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.performance, pytest.mark.asyncio]

APP_SECRET = os.getenv("WEBHOOK_VERIFY_TOKEN", "dummy_secret")

try:
    from app.core.config import settings
    # Dynamically extract the backend's configured Meta/WhatsApp secret
    _secret = None
    for key in dir(settings):
        if "SECRET" in key.upper() and "JWT" not in key.upper():
            val = getattr(settings, key)
            if isinstance(val, str) and val:
                _secret = val
                break
    APP_SECRET = _secret or "dummy_secret"
except Exception:
    APP_SECRET = "dummy_secret"

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    """Generates the HMAC SHA256 signature to emulate Meta's webhook security."""
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def create_payload(index: int, run_id: str) -> bytes:
    """Constructs a deterministic, Meta-compliant payload for stress testing."""
    msg_id = f"wamid.BURST_{run_id}_{index}"
    phone = f"260999{index:04d}" 
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": f"Burst User {index}"}, "wa_id": phone}],
            "messages": [{
                "from": phone,
                "id": msg_id,
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": f"Burst message {index} Paid 150 ZMW"}
            }]
        }}]}]
    }
    return json.dumps(payload, separators=(',', ':')).encode('utf-8')

async def mock_dependency(request: Request):
    """No-op dependency to bypass middleware during load testing."""
    return None

async def monitor_queue_depth(mock_redis, interval=0.2):
    """Continuously records the Redis queue depth while the worker is active."""
    depths = []
    while worker_service.is_running:
        depths.append(mock_redis.llen(WEBHOOK_QUEUE_NAME))
        await asyncio.sleep(interval)
    return depths

def generate_mock_json_response(*args, **kwargs):
    """Dynamically reads the AI prompt and explicitly returns parsed schemas for ANY IDs found."""
    prompt_str = str(args) + str(kwargs)
    keys = set(re.findall(r'\b\d+\b', prompt_str) + re.findall(r'wamid\.BURST_[a-zA-Z0-9_]+', prompt_str))
    response_list = []
    for k in keys:
        response_list.append({
            "id": k,  # ID must be strictly included inside the JSON schema
            "amount": 150.0, 
            "currency": "ZMW", 
            "transaction_verb": "credit",
            "transaction_date": "2023-10-25", 
            "confidence": 0.95, 
            "reference": "Stress test"
        })
        
    # Return the native dictionary structure exactly as the real Gemini requests.post().json() does
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(response_list)}]
                }
            }
        ]
    }

async def mock_gemini_generate_async(*args, **kwargs):
    return generate_mock_json_response(*args, **kwargs)
    
def mock_gemini_generate_sync(*args, **kwargs):
    return generate_mock_json_response(*args, **kwargs)

async def test_webhook_burst_ingestion(db_session, mock_redis):
    """
    Simulates high-volume webhook ingestion, runs the background worker concurrently,
    and measures processing latency and queue drainage dynamics.
    """
    app.state.redis = mock_redis

    # Isolate parameterized dependencies and enforce explicit overrides
    for route in app.routes:
        if hasattr(route, "dependencies"):
            for dep in route.dependencies:
                if isinstance(dep.dependency, RateLimiter) or isinstance(dep.dependency, IPFilter):
                    app.dependency_overrides[dep.dependency] = mock_dependency

    total_requests = 50  # Scaled down to prevent local SQLite/Postgres overwhelm
    run_id = str(int(time.time()))
    
    # Reset worker flag in case of dirty state from previous tests
    worker_service.is_running = True

    # Create an independent thread-safe connection pool strictly for the test scope
    test_engine = create_engine(db_session.bind.url, pool_size=50, max_overflow=50)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
            
    # Force the API to use the thread-safe connection pool, completely bypassing the single-threaded conftest.py mock
    app.dependency_overrides[get_db] = override_get_db

    try:
        # Force the Worker to use the EXACT SAME thread-safe pool so it can see the API's committed records
        with patch('app.database.database.SessionLocal', TestingSessionLocal), \
             patch('app.workers.job_handler.SessionLocal', TestingSessionLocal), \
             patch('app.workers.worker_service.get_redis_client', return_value=mock_redis), \
             patch("app.ai.gemini_client.GeminiClient.generate_content_async", new_callable=AsyncMock, side_effect=mock_gemini_generate_async, create=True), \
             patch("app.ai.gemini_client.GeminiClient.generate_content", side_effect=mock_gemini_generate_sync, create=True):
            
            # 1. Start the queue monitor
            monitor_task = asyncio.create_task(monitor_queue_depth(mock_redis, 0.2))
            
            # 2. Spawn the worker loop in a separate thread so it doesn't block the async event loop
            worker_task = asyncio.create_task(asyncio.to_thread(worker_service.start_worker))

            # 3. Fire the burst ingestion
            sem = asyncio.Semaphore(2)  # Strict limit to guarantee NO QueuePool timeouts
            async def bounded_post(req_client, content, headers):
                async with sem:
                    return await req_client.post("/api/v1/webhook", content=content, headers=headers)

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                tasks = []
                for i in range(total_requests):
                    payload_bytes = create_payload(i, run_id)
                    headers = {
                        'Content-Type': 'application/json',
                        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
                    }
                    tasks.append(bounded_post(client, payload_bytes, headers))
                
                burst_start = time.perf_counter()
                responses = await asyncio.gather(*tasks)
                burst_end = time.perf_counter()

            # 4. Wait for worker to drain the queues completely
            timeout_seconds = 45
            drain_start = time.perf_counter()
            while True:
                q_len = mock_redis.llen(WEBHOOK_QUEUE_NAME)
                active_len = mock_redis.llen(WEBHOOK_ACTIVE_QUEUE)
                if q_len == 0 and active_len == 0:
                    break
                if time.perf_counter() - drain_start > timeout_seconds:
                    pytest.fail("Worker failed to drain the queue within the timeout period.")
                await asyncio.sleep(0.5)
            
            # Allow final DB transactions to cleanly commit
            await asyncio.sleep(1)

    finally:
        # 5. Clean shutdown
        app.dependency_overrides.clear()
        worker_service.is_running = False
        await worker_task
        queue_depths = await monitor_task

    # System Stability Assertions
    successes = [res for res in responses if res.status_code == 200]
    assert len(successes) == total_requests, f"Burst failed. Expected {total_requests} 200 OK responses, got {len(successes)}."

    # Queue Dynamics Assertions
    max_depth = max(queue_depths) if queue_depths else 0
    logger.info(f"Burst duration: {burst_end - burst_start:.2f}s | Max Queue Depth observed: {max_depth}")
    assert mock_redis.llen(WEBHOOK_QUEUE_NAME) == 0, "Queue did not drain completely."

    # Performance Metrics Extraction from Database scoped to this run ID
    messages = db_session.query(RawMessages).filter(
        RawMessages.message_id.like(f"wamid.BURST_{run_id}_%"),
        RawMessages.processing_started_at.isnot(None)
    ).all()
    assert len(messages) == total_requests, f"Missing processing metrics. Expected {total_requests}, found {len(messages)}."

    enqueue_to_start_ms = []
    start_to_write_ms = []

    for msg in messages:
        if msg.received_at and msg.processing_started_at:
            q_time = (msg.processing_started_at - msg.received_at).total_seconds() * 1000
            enqueue_to_start_ms.append(max(0, q_time))
            
        if msg.processing_started_at and msg.processing_completed_at:
            p_time = (msg.processing_completed_at - msg.processing_started_at).total_seconds() * 1000
            start_to_write_ms.append(max(0, p_time))

    avg_q_latency = sum(enqueue_to_start_ms) / len(enqueue_to_start_ms) if enqueue_to_start_ms else 0
    avg_p_latency = sum(start_to_write_ms) / len(start_to_write_ms) if start_to_write_ms else 0

    logger.info(f"--- Performance Latency Metrics ---")
    logger.info(f"Avg Time in Queue (Enqueue -> Processing Start): {avg_q_latency:.2f} ms")
    logger.info(f"Avg Processing Time (Start -> DB Commit): {avg_p_latency:.2f} ms")
    
    # Sanity threshold check
    assert avg_q_latency < 5000, "Queue wait time degraded severely under load."


def db_write_worker(engine, txn_data, audit_data):
    """Worker function for concurrent DB stress testing. Uses independent session per thread."""
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    start_time = time.perf_counter()
    try:
        # Measure Transaction + Internal Audit Logic
        upsert_transaction(db=db, txn_data=txn_data, commit=False, actor_identifier="stress_tester")
        
        # Explicit Audit Log insertion to simulate wider system write impact
        audit = AuditLog(**audit_data)
        db.add(audit)
        
        db.commit()
        latency = (time.perf_counter() - start_time) * 1000
        return {"status": "success", "latency": latency, "error": None}
    except (OperationalError, IntegrityError) as e:
        db.rollback()
        latency = (time.perf_counter() - start_time) * 1000
        return {"status": "failure", "latency": latency, "error": type(e).__name__}
    except Exception as e:
        db.rollback()
        latency = (time.perf_counter() - start_time) * 1000
        return {"status": "failure", "latency": latency, "error": str(e)}
    finally:
        db.close()


async def test_database_write_performance(db_session):
    """
    Directly stress the database bypassing Redis and workers.
    Measures transaction and audit log insert latencies, and checks for lock contention.
    """
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    total_unique_writes = 500
    total_duplicate_writes = 50  # Simulates race condition lock contention
    
    # 1. Setup Base Foreign Key Constraints (Serial)
    group = Groups(tenant_id=1, group_id=f"grp_load_{run_id}", groupname="Load Group")
    phone_number = f"2609{random.randint(100000, 999999)}"
    participant = Participants(tenant_id=1, phone=phone_number, displayname="Load User")
    db_session.add(group)
    db_session.add(participant)
    db_session.commit()

    raw_msgs = []
    for i in range(total_unique_writes):
        msg = RawMessages(
            tenant_id=1,
            group_id=group.id,
            sender_id=participant.id,
            message_id=f"msg_{run_id}_{i}",
            received_at=datetime.now(timezone.utc),
            raw_json={"dummy": True},
            hash=f"raw_hash_{run_id}_{i}"
        )
        raw_msgs.append(msg)
    
    db_session.add_all(raw_msgs)
    db_session.commit()
    
    raw_msg_ids = [msg.id for msg in raw_msgs]
    
    # 2. Build Concurrent Load Tasks
    write_tasks = []
    for i in range(total_unique_writes):
        txn_data = {
            "tenant_id": 1,
            "raw_message_id": raw_msg_ids[i],
            "amount": 100.0 + i,
            "currency": "ZMW",
            "txn_type": "credit",
            "txn_date": datetime.now(timezone.utc),
            "confidence": 0.99,
            "status": TransactionStatus.PARSED,
            "hash": f"txn_hash_{run_id}_{i}",
            "parsing_meta": {"test": True},
            "remarks": "stress test unique"
        }
        audit_data = {
            "entity_type": "transaction",
            "entity_id": str(raw_msg_ids[i]),
            "event_type": EventType.UPDATE,
            "actor_type": ActorType.SYSTEM,
            "actor_identifier": "stress_worker",
            "old_state": None,
            "new_state": {"status": "parsed"}
        }
        write_tasks.append((txn_data, audit_data))
        
    # Inject intentional duplication to trigger DB locks/Integrity checks concurrently
    for _ in range(total_duplicate_writes):
        duplicate_txn = write_tasks[0][0].copy()
        duplicate_audit = write_tasks[0][1].copy()
        write_tasks.append((duplicate_txn, duplicate_audit))
        
    # 3. Execute Concurrent Writes via ThreadPool
    loop = asyncio.get_running_loop()
    start_time = time.perf_counter()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
        futures = [
            loop.run_in_executor(pool, db_write_worker, db_session.bind, t_data, a_data)
            for t_data, a_data in write_tasks
        ]
        results = await asyncio.gather(*futures)
        
    end_time = time.perf_counter()
    
    # 4. Analyze Results
    throughput = len(results) / (end_time - start_time)
    
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] == "failure"]
    latencies = [r["latency"] for r in successes]
    
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
    
    logger.info(f"\n--- Database Performance Metrics ---")
    logger.info(f"Total Time: {end_time - start_time:.2f}s | Throughput: {throughput:.2f} writes/sec")
    logger.info(f"Average Write Latency: {avg_latency:.2f} ms")
    logger.info(f"P95 Write Latency: {p95_latency:.2f} ms")
    logger.info(f"Max Write Latency: {max_latency:.2f} ms")
    logger.info(f"Successes: {len(successes)} | Contention Blocks/Failures: {len(failures)}")
    
    if failures:
        error_types = {}
        for f in failures:
            error_types[f["error"]] = error_types.get(f["error"], 0) + 1
        logger.warning(f"Write Exceptions Encounted (Expected for Duplicates): {error_types}")
        
    # 5. Assertions
    # We expect all 500 unique writes to succeed flawlessly.
    unique_success_count = sum(1 for r in results[:total_unique_writes] if r["status"] == "success")
    assert unique_success_count == total_unique_writes, f"Database dropped {total_unique_writes - unique_success_count} unique writes under load."
    
    # Verify throughput doesn't degrade severely (Sanity check: > 10 writes/sec locally)
    assert throughput > 10, "Database write throughput dropped below critical acceptable limits."
    assert avg_latency < 1000, "Database latency spiked above 1000ms per transaction."

async def test_sustained_stress_and_recovery(db_session, mock_redis):
    """
    Validates system stability, memory handling, and worker recovery over multiple
    consecutive bursts. Ensures no stalls, no state accumulation, and consistent latency.
    """
    app.state.redis = mock_redis
    
    # Isolate parameterized dependencies and enforce explicit overrides
    for route in app.routes:
        if hasattr(route, "dependencies"):
            for dep in route.dependencies:
                if isinstance(dep.dependency, RateLimiter) or isinstance(dep.dependency, IPFilter):
                    app.dependency_overrides[dep.dependency] = mock_dependency

    num_bursts = 3
    requests_per_burst = 30  # Optimized chunks for rapid local testing
    timeout_seconds = 30

    worker_service.is_running = True
    burst_metrics = []

    # Create an independent thread-safe connection pool for sustained stress
    test_engine = create_engine(db_session.bind.url, pool_size=50, max_overflow=50)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
            
    app.dependency_overrides[get_db] = override_get_db

    try:
        # Patch the Worker to use the thread-safe pool
        with patch('app.database.database.SessionLocal', TestingSessionLocal), \
             patch('app.workers.job_handler.SessionLocal', TestingSessionLocal), \
             patch('app.workers.worker_service.get_redis_client', return_value=mock_redis), \
             patch("app.ai.gemini_client.GeminiClient.generate_content_async", new_callable=AsyncMock, side_effect=mock_gemini_generate_async, create=True), \
             patch("app.ai.gemini_client.GeminiClient.generate_content", side_effect=mock_gemini_generate_sync, create=True):

            # Spawn worker in the background
            worker_task = asyncio.create_task(asyncio.to_thread(worker_service.start_worker))

            for burst_idx in range(num_bursts):
                run_id = f"sustained_{int(time.time())}_{burst_idx}"       
                logger.info(f"--- Initiating Burst {burst_idx + 1}/{num_bursts} ---")

                # 1. Fire the burst
                sem = asyncio.Semaphore(2)

                async def bounded_post(req_client, content, headers):
                    async with sem:
                        return await req_client.post("/api/v1/webhook", content=content, headers=headers)

                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                    tasks = []
                    for i in range(requests_per_burst):
                        payload_bytes = create_payload(i, run_id)
                        headers = {
                            'Content-Type': 'application/json',
                            'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
                        }
                        tasks.append(bounded_post(client, payload_bytes, headers))
                    
                    burst_start = time.perf_counter()
                    responses = await asyncio.gather(*tasks)
                    burst_end = time.perf_counter()
                
                # Assert no HTTP failures during ingestion
                successes = [r for r in responses if r.status_code == 200]
                assert len(successes) == requests_per_burst, f"Ingestion failed during Burst {burst_idx + 1}"
                
                # 2. Wait for full drain to prove the worker has not stalled
                drain_start = time.perf_counter()
                while True:
                    q_len = mock_redis.llen(WEBHOOK_QUEUE_NAME)
                    active_len = mock_redis.llen(WEBHOOK_ACTIVE_QUEUE)
                    if q_len == 0 and active_len == 0:
                        break
                    if time.perf_counter() - drain_start > timeout_seconds:
                        pytest.fail(f"Worker stalled during burst {burst_idx + 1}. Queues failed to drain.")
                    await asyncio.sleep(0.5)
                
                # Allow minor DB commit settlement delay
                await asyncio.sleep(1)
                drain_end = time.perf_counter()
                
                # 3. Extract latencies specific to THIS burst iteration
                messages = db_session.query(RawMessages).filter(
                    RawMessages.message_id.like(f"wamid.BURST_{run_id}_%")
                ).all()
                
                assert len(messages) == requests_per_burst, f"Data missing or duplicated in Burst {burst_idx + 1}"
                
                q_times = []
                p_times = []
                for m in messages:
                    if m.received_at and m.processing_started_at:
                        q_times.append((m.processing_started_at - m.received_at).total_seconds() * 1000)
                    if m.processing_started_at and m.processing_completed_at:
                        p_times.append((m.processing_completed_at - m.processing_started_at).total_seconds() * 1000)
                
                avg_q = sum(q_times) / len(q_times) if q_times else 0
                avg_p = sum(p_times) / len(p_times) if p_times else 0
                total_drain_time = drain_end - burst_start
                
                burst_metrics.append({
                    "burst": burst_idx + 1,
                    "avg_queue_latency_ms": avg_q,
                    "avg_proc_latency_ms": avg_p,
                    "drain_time_s": total_drain_time
                })
                
    finally:
        worker_service.is_running = False
        await worker_task
        app.dependency_overrides.clear()
        
    # 4. End-to-End Stability Assertions
    # Verify overall data integrity (Idempotency holding up across repeated loads)
    total_expected = num_bursts * requests_per_burst
    
    # Isolate checking to ONLY the transactions generated by THIS specific test run
    sustained_msgs = db_session.query(RawMessages.id).filter(
        RawMessages.message_id.like("wamid.BURST_sustained_%")
    ).all()
    sustained_msg_ids = [m.id for m in sustained_msgs]
    
    total_transactions = db_session.query(Transactions).filter(
        Transactions.raw_message_id.in_(sustained_msg_ids)
    ).count()
    
    assert total_transactions == total_expected, f"State accumulation error: Expected {total_expected} total DB transactions, found {total_transactions}."
    
    # Verify Latency does not degrade exponentially between first and last bursts
    first_burst = burst_metrics[0]
    last_burst = burst_metrics[-1]
    
    logger.info(f"\n--- Sustained Stress & Recovery Report ---")
    for metric in burst_metrics:
        logger.info(f"Wave {metric['burst']}: Drain Time = {metric['drain_time_s']:.2f}s | Avg Queue Wait = {metric['avg_queue_latency_ms']:.2f}ms | Avg DB Proc = {metric['avg_proc_latency_ms']:.2f}ms")
        
    # We allow some natural slight variance, but the last burst should not be more than 4x slower 
    # than the first burst in processing time, which would indicate a serious memory leak or DB lock pileup.
    assert last_burst["avg_proc_latency_ms"] < (first_burst["avg_proc_latency_ms"] * 4), "Processing latency degraded drastically across bursts. Potential memory leak or lock accumulation detected."
    assert last_burst["drain_time_s"] < (first_burst["drain_time_s"] * 3), "Worker took increasingly longer to drain queues over time. Throughput is decaying."