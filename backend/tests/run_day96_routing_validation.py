import json
import uuid
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.database.redis_client import get_redis_client, WEBHOOK_QUEUE_NAME
from app.database.postgres_client import get_db_connection
from app.schemas.jobs import WebhookJobPayload

PAYLOADS = [
    {"label": "valid transaction message", "msg": "Paid John 500 ZMW for lunch yesterday", "expected": "parsed"},
    {"label": "missing required keys: amount and currency", "msg": "Paid John for lunch yesterday", "expected": "reject"},
    {"label": "ambiguous amount/currency message", "msg": "Paid 500 or 600 for lunch", "expected": "reject"},
    {"label": "conflicting transaction direction", "msg": "Sent and received 500 ZMW from John", "expected": "reject"},
    {"label": "mixed currency message", "msg": "Paid 500 ZMW and 10 USD for lunch", "expected": "review_needed"},
    {"label": "noisy message with emojis and text clutter", "msg": "Hey! 🚀 Just paid John 500 ZMW for the amazing lunch we had yesterday! 🍔🎉", "expected": "parsed"},
    {"label": "non-transaction message that still contains money-like numbers", "msg": "I walked 500 steps and earned 10 points", "expected": "reject"},
    {"label": "intentionally confusing financial phrases", "msg": "I owe John 500 ZMW but I paid him 300 ZMW for now", "expected": "parsed"},
    {"label": "edited/reversal-like message that conflicts with the original", "msg": "Wait, I didn't pay John 500 ZMW, it was 400 ZMW", "expected": "review_needed"},
    {"label": "duplicate amounts in one message", "msg": "Paid John 500 ZMW and then another 500 ZMW", "expected": "reject"}
]

def inject_test_payloads():
    redis_client = get_redis_client()
    injected_data = []
    
    print("Injecting payloads into live webhook...")
    for item in PAYLOADS:
        raw_message_id = str(uuid.uuid4().int)[:5]
        
        # Connect to DB to insert raw message
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO raw_messages (message_id, sender_id, receiver_id, raw_text, status) 
               VALUES (%s, 'test_user', 'system', %s, 'pending') RETURNING id""",
            (raw_message_id, item['msg'])
        )
        db_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        payload = WebhookJobPayload(
            job_id=str(uuid.uuid4()),
            raw_message_id=db_id,
            webhook_payload={"message": item['msg']}
        )
        
        redis_client.rpush(WEBHOOK_QUEUE_NAME, payload.to_json())
        injected_data.append({"db_id": db_id, "label": item['label'], "expected": item['expected']})
        print(f"Injected: {item['label']}")
        
    return injected_data

def validate_pipeline(injected_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    report_lines = ["# DAY 96: Schema Enforcement & Routing Validation\n"]
    
    for data in injected_data:
        cursor.execute("SELECT status, parsing_metadata, audit_logs FROM raw_messages WHERE id = %s", (data['db_id'],))
        row = cursor.fetchone()
        
        if row:
            actual_status = row[0]
            parsing_meta = row[1] if row[1] else {}
            audit_logs = row[2]
            
            icon = "✅" if actual_status == data['expected'] else "❌"
            report_lines.append(f"## {icon} {data['label']}")
            report_lines.append(f"- **Expected**: {data['expected']} | **Actual**: {actual_status}")
            report_lines.append(f"- **Raw Status**: {parsing_meta.get('system_status', 'unknown')}")
            report_lines.append(f"- **AI Status**: {(parsing_meta.get('ai_extraction') or {}).get('status')}")
            report_lines.append(f"- **Confidence**: {(parsing_meta.get('ai_extraction') or {}).get('confidence_score')}")
            
            if audit_logs:
                report_lines.append("- **Audit Triggered**: Yes")
            report_lines.append("\n")
            
    conn.close()
    
    report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'DAY96_ROUTING_REPORT.md'))
    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))
        
    print(f"Validation complete. Report written to {report_path}")

if __name__ == "__main__":
    injected = inject_test_payloads()
    print("Awaiting worker processing (75 seconds)...")
    time.sleep(75)
    validate_pipeline(injected)