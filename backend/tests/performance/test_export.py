import time
import uuid
import random
import pytest
import httpx
import logging
import tracemalloc
from datetime import datetime, timezone, timedelta
from fastapi import Request
from sqlalchemy.orm import sessionmaker

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
    return None

async def mock_require_admin(request: Request):
    # Ensure tenant_id is an integer to match the DB schema exactly
    return {"user_id": 1, "role": "admin", "tenant_id": 1}

async def test_large_data_export(db_session, mock_redis):
    """
    Validate system behavior during large data export (10k+ records).
    """
    app.state.redis = mock_redis
    
    # CRITICAL FIX: Share the Pytest db_session directly with the API.
    # Since ASGITransport runs in the same thread, this is the only way to 
    # guarantee the API sees the data seeded by the test.
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = mock_require_admin
    app.dependency_overrides[require_admin] = mock_require_admin
    
    for route in app.routes:
        if hasattr(route, "dependencies"):
            for dep in route.dependencies:
                if isinstance(dep.dependency, (RateLimiter, IPFilter)):
                    app.dependency_overrides[dep.dependency] = mock_dependency
    
    total_records = 10000
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    base_date = datetime.now(timezone.utc)
    
    logger.info(f"Seeding {total_records} transactions for export...")
    seed_start = time.perf_counter()
    
    # 1. Setup Base Relations
    group = Groups(tenant_id=1, group_id=f"grp_exp_{run_id}", groupname="Export Group")
    phone_number = f"2609{random.randint(100000, 999999)}"
    participant = Participants(tenant_id=1, phone=phone_number, displayname="Export User")
    db_session.add(group)
    db_session.add(participant)
    db_session.flush() # Generate IDs
    
    # 2. Seed RawMessages
    raw_msgs = []
    for i in range(total_records):
        rm = RawMessages(
            tenant_id=1,
            group_id=group.id,
            sender_id=participant.id,
            message_id=f"msg_exp_{run_id}_{i}",
            received_at=base_date - timedelta(minutes=i),
            raw_text="Export test payload",
            raw_json={"dummy": True},
            hash=f"raw_exp_{run_id}_{i}",
            processed=True,
            is_transaction=True,
            created_at=base_date,
            updated_at=base_date
        )
        raw_msgs.append(rm)
    db_session.add_all(raw_msgs)
    db_session.flush()
    
    # 3. Seed Transactions
    txns = []
    for i, rm in enumerate(raw_msgs):
        txn = Transactions(
            tenant_id=1,
            raw_message_id=rm.id,
            amount=10.0 + (i % 100),
            currency="ZMW",
            txn_type="credit",
            txn_date=base_date - timedelta(minutes=i),
            confidence=0.95,
            status=TransactionStatus.PARSED,
            hash=f"txn_exp_{run_id}_{i}",
            remarks=f"Stress test record {i}",
            created_at=base_date,
            updated_at=base_date
        )
        txns.append(txn)
    db_session.add_all(txns)
    db_session.flush()
    # ... (seeding logic remains identical) ...
    logger.info(f"Database hydration complete in {time.perf_counter() - seed_start:.2f} seconds.")

    export_params = {
        "date_from": (base_date - timedelta(days=365)).isoformat(),
        "date_to": (base_date + timedelta(days=1)).isoformat(),
        "limit": 200 
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. WARM-UP REQUEST: Triggers FastAPI lifespan/startup events 
        # so they don't pollute the performance TTFB metric.
        await client.get("/api/v1/transactions/health") 

        lines_count = 0
        time_to_first_byte = None
        
        # 2. Start performance tracking AFTER the app is warmed up
        tracemalloc.start()
        export_start_time = time.perf_counter()
        
        try:
            headers = {"Authorization": "Bearer mock_token"}
            async with client.stream("GET", "/api/v1/transactions/export", params=export_params, headers=headers) as response:
                assert response.status_code == 200
                
                async for chunk in response.aiter_bytes():
                    if time_to_first_byte is None:
                        # 3. Capture TRUE Time to First Byte
                        time_to_first_byte = time.perf_counter() - export_start_time
                        
                    lines_count += chunk.decode('utf-8', errors='ignore').count('\n')
        finally:
            current_mem, peak_mem = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            app.dependency_overrides.clear()

    logger.info(f"\n--- Export Streaming & Memory Metrics ---")
    logger.info(f"Time to First Byte (TTFB): {time_to_first_byte * 1000:.2f} ms")
    logger.info(f"Rows Exported: {lines_count} / {total_records}")
    logger.info(f"Memory Usage (Peak): {peak_mem / 1024 / 1024:.2f} MB")

    assert time_to_first_byte < 5.0, f"Streaming delayed unexpectedly: {time_to_first_byte:.2f}s. Check for buffering or query plan regression."
    assert lines_count >= total_records