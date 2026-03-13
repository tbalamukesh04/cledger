import json
from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME

def inspect_queue():
    print(f"--- Inspecting Redis Queue: {WEBHOOK_QUEUE_NAME} ---")
    
    # Check queue length
    length = redis_client.llen(WEBHOOK_QUEUE_NAME)
    print(f"Queue Length: {length}")
    
    if length > 0:
        # Peek at the most recently pushed item (index 0)
        items = redis_client.lrange(WEBHOOK_QUEUE_NAME, 0, 0)
        if items:
            print("\n✅ Latest job payload in queue:")
            # Parse and format the JSON for readable output
            parsed_job = json.loads(items[0])
            print(json.dumps(parsed_job, indent=2))
    else:
        print("❌ Queue is empty. Webhook did not enqueue the job.")

if __name__ == "__main__":
    inspect_queue()