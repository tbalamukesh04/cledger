import os
import json
import time
import hmac
import hashlib
import requests
import concurrent.futures
from dotenv import load_dotenv

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Use 127.0.0.1 to avoid localhost IPv6 DNS timeouts on Windows
WEBHOOK_URL = "http://127.0.0.1:8000/api/v1/webhook"
APP_SECRET = os.getenv("WEBHOOK_VERIFY_TOKEN", "dummy_secret")

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def send_single_webhook(run_id: str, index: int) -> dict:
    """Generates a unique payload and sends a single webhook, measuring latency."""
    # Ensure a unique message ID and Phone number to bypass idempotency 
    # and safely stress-test database insert locks.
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
                "text": {"body": f"Burst message {index}!"}
            }]
        }}]}]
    }

    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }

    start_time = time.perf_counter()
    try:
        response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers, timeout=5)
        latency_ms = (time.perf_counter() - start_time) * 1000
        return {
            "status": response.status_code,
            "text": response.text,
            "latency_ms": latency_ms,
            "error": None
        }
    except requests.RequestException as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return {
            "status": 500,
            "text": "",
            "latency_ms": latency_ms,
            "error": str(e)
        }

def run_burst_test(total_requests=50, max_workers=10):
    print(f"--- Starting Webhook Burst Test ---")
    print(f"Target: {WEBHOOK_URL}")
    print(f"Total Requests: {total_requests} (Concurrency: {max_workers})\n")

    # 1. Check initial queue length
    try:
        initial_q_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
        print(f"📊 Initial Redis Queue Length: {initial_q_len}")
    except Exception as e:
        print(f"❌ Could not connect to Redis: {e}")
        return

    run_id = str(int(time.time()))
    results = []

    # 2. Fire concurrent requests
    start_test_time = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = [executor.submit(send_single_webhook, run_id, i) for i in range(total_requests)]
        
        # Gather results as they complete
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    total_test_time = time.perf_counter() - start_test_time

    # 3. Analyze Results
    successes = [r for r in results if r["status"] == 200 and r["text"] == "EVENT_RECEIVED"]
    failures = [r for r in results if r["status"] != 200 or r["error"] is not None]
    latencies = [r["latency_ms"] for r in results]

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0

    print("\n--- Burst Test Results ---")
    print(f"✅ Successful Requests: {len(successes)} / {total_requests}")
    if failures:
        print(f"❌ Failed Requests: {len(failures)}")
        for f in failures[:3]: # Print first few errors
            print(f"   -> Status {f['status']}: {f['error'] or f['text']}")

    print(f"\n⏱️  Latency Metrics:")
    print(f"   - Average: {avg_latency:.2f} ms")
    print(f"   - Minimum: {min_latency:.2f} ms")
    print(f"   - Maximum: {max_latency:.2f} ms")
    print(f"   - Total Test Duration: {total_test_time:.2f} seconds")

    # 4. Check final queue length
    final_q_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
    expected_growth = len(successes)
    actual_growth = final_q_len - initial_q_len
    
    print(f"\n📦 Redis Queue Validation:")
    print(f"   - Final Queue Length: {final_q_len}")
    print(f"   - Expected Growth: +{expected_growth}")
    print(f"   - Actual Growth:   +{actual_growth}")

    if actual_growth == expected_growth and len(failures) == 0:
        print("\n🏆 PASS: System handled burst perfectly. Queue grew as expected with no failures.")
    else:
        print("\n⚠️ WARNING: Burst test revealed potential dropped requests or queue mismatches.")

if __name__ == "__main__":
    # You can tweak total_requests and max_workers here
    run_burst_test(total_requests=50, max_workers=10)