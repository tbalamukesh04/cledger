import json
import httpx
import hmac
import hashlib
import time
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Must match the WHATSAPP_APP_SECRET in backend/.env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")
if not APP_SECRET:
    raise ValueError("WHATSAPP_APP_SECRET not found in .env file")
WEBHOOK_URL = "http://localhost:8000/api/v1/webhook/whatsapp"
DATASET_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "review_validation_dataset.json")

def generate_signature(payload_bytes: bytes) -> str:
    """Generate Meta-compliant HMAC SHA256 signature for payload."""
    signature = hmac.new(APP_SECRET.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={signature}"

async def run_injection():
    print(f"Loading dataset from {DATASET_PATH}")
    with open(DATASET_PATH, 'r') as f:
        dataset = json.load(f)

    async with httpx.AsyncClient() as client:
        for item in dataset:
            print(f"\n[Injecting] ID: {item['id']} | Desc: {item['description']}")
            print(f"Payload: {item['payload']}")
            
            # Construct standard WhatsApp webhook payload
            payload = {
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "day97_test_acc",
                    "changes": [{
                        "value": {
                            "metadata": {"phone_number_id": "1234567890"},
                            "contacts": [{"profile": {"name": "Review Tester"}, "wa_id": "918056646050"}],
                            "messages": [{
                                "from": "918056646050",
                                "id": f"wamid.DAY97.{item['id']}.{int(time.time())}",
                                "timestamp": str(int(time.time())),
                                "text": {"body": item['payload']},
                                "type": "text"
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            }
            
            payload_bytes = json.dumps(payload).encode('utf-8')
            headers = {
                "Content-Type": "application/json",
                "x-hub-signature-256": generate_signature(payload_bytes)
            }
            
            try:
                response = await client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
                if response.status_code == 200:
                    print(f"SUCCESS: Webhook accepted (200 OK)")
                else:
                    print(f"FAILED: Status {response.status_code} | {response.text}")
            except Exception as e:
                print(f"ERROR: Connection failed - {str(e)}")
            
            # Stagger to allow realistic batching intervals
            await asyncio.sleep(2)

    print("\nInjection complete. Allow 5-10 seconds for the worker queue to process and route transactions to 'review_needed'.")

if __name__ == "__main__":
    asyncio.run(run_injection())
