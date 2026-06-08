import os
import json
import time
import uuid
import requests
import logging
from datetime import datetime, timezone
import hashlib
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import hmac
from dotenv import load_dotenv

# Local heuristics import
from app.schemas.preprocessing import ProcessingContext, PreprocessedPayload
from app.parsing.scoring_engine import TransactionScorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

WEBHOOK_URL = "http://localhost:8000/api/v1/webhook"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(BASE_DIR, "tests", "fixtures", "batch_dataset_testing.json")
REPORT_JSON_PATH = os.path.join(BASE_DIR, "tests", "day95_comparison_report.json")
REPORT_MD_PATH = os.path.join(BASE_DIR, "tests", "day95_validation_summary.md")

# Load environment variables to get the correct database credentials
load_dotenv(os.path.join(BASE_DIR, ".env"))
DATABASE_URI = os.getenv("DATABASE_URL")
if not DATABASE_URI:
    raise ValueError("DATABASE_URL environment variable not found. Check your .env file.")

engine = create_engine(DATABASE_URI, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
scoring_engine = TransactionScorer()

def build_whatsapp_payload(message_id: str, text_body: str, timestamp_iso: str) -> dict:
    """Constructs a Meta-compliant WhatsApp Webhook payload."""
    unix_timestamp = int(datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00")).timestamp())
    wamid = f"wamid.{uuid.uuid4().hex[:20]}"
    
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "TEST_ENTRY_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "1234567890",
                        "phone_number_id": "1234567890"
                    },
                    "contacts": [{
                        "profile": {"name": "Validation Script"},
                        "wa_id": "918056646050"
                    }],
                    "messages": [{
                        "from": "918056646050",
                        "id": wamid,
                        "timestamp": str(unix_timestamp),
                        "type": "text",
                        "text": {"body": text_body},
                        "context": {"script_id": message_id} # Traceable injection
                    }]
                }
            }]
        }]
    }, wamid

def run_heuristic_parse(msg_id: str, text_body: str, wamid: str) -> dict:
    """Executes the local heuristic scoring engine for baseline comparison."""
    numeric_id = int(msg_id.replace("msg_", "")) if "msg_" in msg_id else 999
    
    payload = PreprocessedPayload(
        raw_message_id=numeric_id,
        wamid=wamid,
        normalized_text=text_body,
        normalized_timestamp=datetime.now(timezone.utc),
        participant_id=1,
        message_id=wamid,
        message_type="text",
        message_hash=hashlib.sha256(text_body.encode()).hexdigest(),
        text_hash=hashlib.sha256(text_body.encode()).hexdigest(),
        idempotency_identifier=f"idem_{wamid}"
    )
    context = ProcessingContext(payload=payload)
    result_context = scoring_engine.evaluate(context)
    
    return {
        "total_score": result_context.scoring.total_score,
        "is_candidate": result_context.scoring.is_transaction_candidate,
        "signals": result_context.scoring.rule_breakdown
    }

def fetch_persisted_transaction(session, wamid: str) -> dict:
    """Queries the database for the final state of the injected transaction."""
    query = text("""
        SELECT t.id, t.amount, t.currency, t.txn_type, t.status, t.remarks, r.processing_status
        FROM raw_messages r
        LEFT JOIN transactions t ON r.id = t.raw_message_id
        WHERE r.message_id = :wamid
    """)
    result = session.execute(query, {"wamid": wamid}).fetchone()
    if not result:
        return {"db_status": "not_found", "processing_status": "missing"}
    
    return {
        "db_status": "found",
        "processing_status": result.processing_status,
        "transaction_id": result.id,
        "amount": float(result.amount) if result.amount else None,
        "currency": result.currency,
        "transaction_type": result.txn_type,
        "status": result.status,
        "remarks": result.remarks
    }

def main():
    logger.info("Starting Day 95 Batched LLM Pipeline Validation")
    
    with open(DATASET_PATH, 'r') as f:
        dataset = json.load(f)

    report_data = []
    injected_wamids = {}

    # Step 1: Inject payloads
    for batch in dataset:
        logger.info(f"Injecting {batch['batch_id']}")
        for item in batch["payload"]:
            payload, wamid = build_whatsapp_payload(item["id"], item["text"], item["timestamp"])
            injected_wamids[item["id"]] = {
                "wamid": wamid,
                "text": item["text"],
                "batch_id": batch["batch_id"]
            }
            
            try:
                # Generate cryptographic signature to bypass 403 Forbidden
                payload_bytes = json.dumps(payload).encode('utf-8')
                app_secret = os.getenv("APP_SECRET", "dummy_secret_for_testing")
                signature = hmac.new(
                    key=app_secret.encode('utf-8'),
                    msg=payload_bytes,
                    digestmod=hashlib.sha256
                ).hexdigest()
                
                headers = {
                    "Content-Type": "application/json",
                    "x-hub-signature-256": f"sha256={signature}"
                }
                
                # Send raw bytes to ensure exact HMAC match
                response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
                response.raise_for_status()
                logger.info(f"Injected {item['id']} -> {wamid}")
                
                # Prevent tripping the 15 requests / 60 seconds rate limit
                time.sleep(0.5) 
            except Exception as e:
                logger.error(f"Failed to inject {item['id']}: {e}")

    # Step 2: Await worker batching and processing
    wait_time = 30
    logger.info(f"Waiting {wait_time} seconds for worker batch execution...")
    time.sleep(wait_time)

    # Step 3: Extract and Compare
    logger.info("Executing comparison protocol...")
    with SessionLocal() as session:
        for msg_id, data in injected_wamids.items():
            wamid = data["wamid"]
            text_body = data["text"]
            
            heuristic_result = run_heuristic_parse(msg_id, text_body, wamid)
            db_state = fetch_persisted_transaction(session, wamid)
            
            mismatch = False
            notes = []
            if heuristic_result["is_candidate"] and db_state["processing_status"] != "success":
                mismatch = True
                notes.append("Heuristic marked as candidate, but pipeline rejected or failed.")
            elif not heuristic_result["is_candidate"] and db_state["db_status"] == "found" and db_state["transaction_id"]:
                mismatch = True
                notes.append("Heuristic rejected, but LLM pipeline extracted a transaction.")
            
            report_data.append({
                "message_id": msg_id,
                "batch_id": data["batch_id"],
                "text": text_body,
                "wamid": wamid,
                "heuristic_parse": heuristic_result,
                "persisted_transaction": db_state,
                "mismatch": mismatch,
                "mismatch_notes": notes
            })

    # Step 4: Write artifacts
    with open(REPORT_JSON_PATH, "w") as f:
        json.dump(report_data, f, indent=2)

    with open(REPORT_MD_PATH, "w") as f:
        f.write("# DAY 95: Pipeline Validation Summary\n\n")
        f.write("## Execution Metrics\n")
        f.write(f"- Total Messages Injected: {len(injected_wamids)}\n")
        
        mismatches = [r for r in report_data if r["mismatch"]]
        f.write(f"- Total Mismatches (Heuristic vs Pipeline): {len(mismatches)}\n\n")
        
        f.write("## Mismatch Analysis\n")
        for m in mismatches:
            f.write(f"### {m['message_id']} ({m['batch_id']})\n")
            f.write(f"- **Text**: {m['text']}\n")
            f.write(f"- **Heuristic Result**: {m['heuristic_parse']['is_candidate']} (Score: {m['heuristic_parse']['total_score']})\n")
            f.write(f"- **DB State**: {m['persisted_transaction']['processing_status']} | Txn ID: {m['persisted_transaction']['transaction_id']}\n")
            f.write(f"- **Notes**: {', '.join(m['mismatch_notes'])}\n\n")
            
    logger.info("Validation run complete. Artifacts generated.")

if __name__ == "__main__":
    main()
