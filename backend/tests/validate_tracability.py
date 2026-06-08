import os
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))
DATABASE_URI = os.getenv("DATABASE_URL")

if not DATABASE_URI:
    raise ValueError("DATABASE_URL environment variable not found.")

engine = create_engine(DATABASE_URI, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def main():
    print("Extracting Step 6 Traceability Validation...")
    with SessionLocal() as session:
        query = text("""
            SELECT 
                r.id as raw_id, r.message_id as wamid, r.raw_text, r.parsing_meta,
                t.id as txn_id, t.amount, t.currency, t.txn_type, t.status,
                a.id as audit_id, a.action, a.old_value, a.new_value, a.actor_identifier
            FROM transactions t
            JOIN raw_messages r ON t.raw_message_id = r.id
            JOIN transaction_audit a ON t.id = a.transaction_id
            WHERE r.message_id LIKE 'wamid.%'
            ORDER BY t.created_at DESC
            LIMIT 1
        """)
        result = session.execute(query).fetchone()
        
        if not result:
            print("No complete transaction traces found.")
            return

        trace_report = {
            "1_raw_message": {
                "id": result.raw_id,
                "wamid": result.wamid,
                "text": result.raw_text
            },
            "2_ai_extraction_metadata": result.parsing_meta.get("ai_extraction", {}) if result.parsing_meta else {},
            "3_persisted_transaction": {
                "id": result.txn_id,
                "amount": float(result.amount) if result.amount else None,
                "currency": result.currency,
                "type": result.txn_type,
                "status": result.status
            },
            "4_audit_log": {
                "audit_id": result.audit_id,
                "event_type": result.action,
                "actor_identifier": result.actor_identifier,
                "state_transition": {
                    "old": result.old_value,
                    "new": result.new_value
                }
            }
        }
            
        output_path = os.path.join(BASE_DIR, "tests", "step6_traceability_report.json")
        with open(output_path, "w") as f:
            json.dump(trace_report, f, indent=2)
            
        print(f"Extraction complete. Data saved to {output_path}")

if __name__ == "__main__":
    main()
