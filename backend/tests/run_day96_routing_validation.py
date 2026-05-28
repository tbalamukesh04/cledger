import os
import json
import time
import redis
import uuid
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import hmac
import hashlib
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(BASE_DIR, "tests", "fixtures", "schema_routing_dataset.json")
WEBHOOK_URL = "http://localhost:8000/api/v1/webhook"
REPORT_MD_PATH = os.path.join(BASE_DIR, "tests", "DAY96_ROUTING_REPORT.md")

load_dotenv(os.path.join(BASE_DIR, ".env"))
DATABASE_URI = os.getenv("DATABASE_URL")
APP_SECRET = os.getenv("APP_SECRET", "test_secret")

engine = create_engine(DATABASE_URI)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def generate_signature(payload_bytes: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()

def inject_dataset():
    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)

    injected_data = []
    
    print("Injecting payloads into live webhook...")
    for item in dataset:
        wamid = f"wamid.{uuid.uuid4().hex}"
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1234567890",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "1234", "phone_number_id": "5678"},
                        "contacts": [{"profile": {"name": "Test Validation"}, "wa_id": "918056646050"}],
                        "messages": [{
                            "from": "918056646050",
                            "id": wamid,
                            "timestamp": str(int(time.time())),
                            "text": {"body": item["payload"]},
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
            "X-Hub-Signature-256": generate_signature(payload_bytes)
        }
        
        res = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
        if res.status_code == 200:
            injected_data.append({
                "wamid": wamid, 
                "expected": item["expected_routing"], 
                "desc": item["description"]
            })
            print(f"Injected: {item['description']}")
        else:
            print(f"Failed to inject: {item['description']} - Status {res.status_code}")

    return injected_data

def validate_pipeline(injected_data):
    print("Awaiting worker processing (75 seconds)...")
    time.sleep(75)
    
    db = SessionLocal()
    report_lines = ["# DAY 96: Schema Enforcement & Routing Validation\n"]
    
    for item in injected_data:
        wamid = item["wamid"]
        expected = item["expected"]
        
        raw = db.execute(text("SELECT id, processing_status, parsing_meta FROM raw_messages WHERE message_id = :wamid"), {"wamid": wamid}).fetchone()
        
        if not raw:
            report_lines.append(f"- ❌ **{item['desc']}**: Raw message not found in DB.")
            continue
            
        raw_id, processing_status, parsing_meta = raw
        
        txn = db.execute(text("SELECT status FROM transactions WHERE raw_message_id = :raw_id"), {"raw_id": raw_id}).fetchone()
        audit = db.execute(text("SELECT event_type, new_state FROM audit_logs WHERE entity_id = :raw_id AND entity_type = 'raw_message'"), {"raw_id": str(raw_id)}).fetchall()
        
        actual_routing = "unknown"
        if expected in ["parsed", "review_needed"] and txn:
            actual_routing = txn[0].lower()
        elif expected == "reject" and not txn and processing_status == "review_needed":
            actual_routing = "reject"
            
        match = (actual_routing == expected) or (expected == "review_needed" and actual_routing == "review_needed") or (expected == "parsed" and actual_routing == "parsed")
        
        status_icon = "✅" if match else "❌"
        report_lines.append(f"## {status_icon} {item['desc']}")
        report_lines.append(f"- **Expected**: {expected} | **Actual**: {actual_routing}")
        report_lines.append(f"- **Raw Status**: {processing_status}")
        
        if parsing_meta and "ai_extraction" in parsing_meta:
            report_lines.append(f"- **AI Status**: {(parsing_meta.get('ai_extraction') or {}).get('status')}")
            report_lines.append(f"- **Confidence**: {(parsing_meta.get('ai_extraction') or {}).get('confidence')}")
            
        if expected == "reject" and audit:
            report_lines.append(f"- **Audit Triggered**: Yes")
            
        report_lines.append("\n")

    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"Validation complete. Report written to {REPORT_MD_PATH}")

if __name__ == "__main__":
    injected = inject_dataset()
    validate_pipeline(injected)