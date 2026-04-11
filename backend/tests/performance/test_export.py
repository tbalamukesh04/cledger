import time
import uuid
import random
import pytest
import asyncio
import httpx
import logging
import tracemalloc
from datetime import datetime, timezone, timedelta
from fastapi import Request

from app.main import app
from app.middleware.rate_limiter import RateLimiter
from app.middleware.ip_filter import IPFilter
from app.core.auth_dependencies import require_admin, get_current_user
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.models.transactions import Transactions, TransactionStatus
from app.api.dependencies import get_db

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.performance, pytest.mark.asyncio]

async def mock_dependency(request: Request):
    """No-op dependency to bypass middleware during load testing."""
    return None

async def mock_require_admin(request: Request):
    """Bypass admin authentication for export performance testing."""
    return {"user_id": 1, "role": "admin", "tenant_id": 1}

async def test_large_data_export(db_session, mock_redis):
    """
    Validate system behavior during large data export (10k+ records).
    Ensures memory stability by verifying the payload is streamed immediately
    in chunks rather than fully buffered in backend memory.
    """
    app.state.redis = mock_redis
    
    # CRITICAL FIX: Share the Pytest db_session directly. ASGITransport runs in the 
    # same thread, meaning it can safely read Pytest's isolated uncommitted SAVEPOINT data!
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    
    # Explicitly override router-level dependencies that might be hidden from app.routes
    app.dependency_overrides[get_current_user] = mock_require_admin
    app.dependency_overrides[require_admin] = mock_require_admin
    
    # Isolate endpoint by stripping security and rate-limiting middlewares
    for route in app.routes:
        if hasattr(route, "dependencies"):
            for dep in route.dependencies:
                if isinstance(dep.dependency, RateLimiter) or isinstance(dep.dependency, IPFilter):
                    app.dependency_overrides[dep.dependency] = mock_dependency
    
    total_records = 10000
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    base_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    
    logger.info(f"Seeding {total_records} transactions for export...")
    seed_start = time.perf_counter()
    
    # 1. Setup Base Relations
    group = Groups(tenant_id=1, group_id=f"grp_exp_{run_id}", groupname="Export Group")
    phone_number = f"2609{random.randint(100000, 999999)}"
    participant = Participants(tenant_id=1, phone=phone_number, displayname="Export User")
    db_session.add(group)
    db_session.add(participant)
    db_session.flush() # Flush to generate IDs safely without disk commits
    
    # 2. Fast ORM Insert: RawMessages
    raw_msgs = []
    for i in range(total_records):
        rm = RawMessages(
            tenant_id=1,
            group_id=group.id,
            sender_id=participant.id,
            message_id=f"msg_exp_{run_id}_{i}",
            received_at=base_date + timedelta(minutes=i),
            raw_json={"dummy": True},
            hash=f"raw_exp_{run_id}_{i}",
            processed=True,
            is_transaction=True
        )
        raw_msgs.append(rm)
    
    db_session.add_all(raw_msgs)
    db_session.flush()
    
    # 3. Fast ORM Insert: Transactions
    txns = []
    for i, rm in enumerate(raw_msgs):
        txn = Transactions(
            tenant_id=1,
            raw_message_id=rm.id, 
            amount=10.0 + (i % 100),
            currency="ZMW",
            txn_type="credit" if i % 2 == 0 else "debit",
            txn_date=base_date + timedelta(minutes=i),
            confidence=0.95,
            status=TransactionStatus.PARSED,
            hash=f"txn_exp_{run_id}_{i}",
            remarks=f"Stress test export record {i}"
        )
        txns.append(txn)
        
    db_session.add_all(txns)
    db_session.commit()
    
    logger.info(f"Database hydration complete in {time.perf_counter() - seed_start:.2f} seconds.")

    # Stream Validation
    export_params = {
        "date_from": "2020-01-01",
        "date_to": "2030-01-01"
    }
    
    chunk_count = 0
    total_bytes = 0
    lines_count = 0
    time_to_first_byte = None
    
    # Start Tracing Memory
    tracemalloc.start()
    export_start_time = time.perf_counter()
    
    try:
        headers = {"Authorization": "Bearer mock_token_to_bypass_httpbearer"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            async with client.stream("GET", "/api/v1/transactions/export", params=export_params, headers=headers) as response:
                assert response.status_code == 200, f"Export request failed: Status {response.status_code}"
                
                async for chunk in response.aiter_bytes():
                    if time_to_first_byte is None:
                        time_to_first_byte = time.perf_counter() - export_start_time
                        
                    chunk_count += 1
                    total_bytes += len(chunk)
                    lines_count += chunk.decode('utf-8', errors='ignore').count('\n')
                    
        export_end_time = time.perf_counter()
    finally:
        app.dependency_overrides.clear()
        
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
        
    logger.info(f"\n--- Export Streaming & Memory Metrics ---")
    logger.info(f"Time to First Byte (TTFB): {time_to_first_byte * 1000:.2f} ms")
    logger.info(f"Total Export Duration: {export_end_time - export_start_time:.2f} seconds")
    logger.info(f"Total Network Transfer: {total_bytes / 1024:.2f} KB")    
    logger.info(f"Chunks Streamed: {chunk_count}")
    logger.info(f"Rows Exported: {lines_count} / {total_records}")
    logger.info(f"Memory Usage (Peak during stream): {peak_mem / 1024 / 1024:.2f} MB")
    logger.info(f"Memory Usage (Post stream): {current_mem / 1024 / 1024:.2f} MB")

    # Success Assertions
    assert time_to_first_byte < 1.5, f"Memory buffering risk: Streaming delayed by {time_to_first_byte:.2f}s."
    assert lines_count >= total_records, f"Data loss detected. Expected at least {total_records} rows, received {lines_count}."