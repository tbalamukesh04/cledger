import json
from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME, verify_redis_connection

def test_queue():
    print("--- Testing Redis Queue Initialization ---")
    
    # 1. Verify Connection
    is_connected = verify_redis_connection()
    if not is_connected:
        print("❌ Could not connect to Redis. Check your server.")
        return

    # 2. Define a dummy job payload
    dummy_job = {
        "job_id": "test_job_001",
        "message_id": "wamid.TEST12345",
        "status": "pending"
    }

    # 3. Insert into the queue (LPUSH)
    # We serialize the dictionary to a JSON string before pushing
    redis_client.lpush(WEBHOOK_QUEUE_NAME, json.dumps(dummy_job))
    
    # 4. Verify insertion by checking list length
    queue_length = redis_client.llen(WEBHOOK_QUEUE_NAME)
    print(f"✅ Job successfully pushed! Current '{WEBHOOK_QUEUE_NAME}' length: {queue_length}")

    # 5. Clean up the test job so it doesn't pollute actual workers later
    redis_client.rpop(WEBHOOK_QUEUE_NAME)
    print("🧹 Cleaned up test job.")

if __name__ == "__main__":
    test_queue()