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
    print("Extracting parsing_meta for Step 3 Validation...")
    with SessionLocal() as session:
        query = text("""
            SELECT r.message_id, r.raw_text, r.processing_status, r.parsing_meta, t.txn_type, t.amount
            FROM raw_messages r
            LEFT JOIN transactions t ON r.id = t.raw_message_id
            WHERE r.message_id LIKE 'wamid.%'
            ORDER BY r.id DESC
            LIMIT 15
        """)
        results = session.execute(query).fetchall()
        
        report_data = []
        for r in results:
            report_data.append({
                "wamid": r.message_id,
                "text": r.raw_text,
                "processing_status": r.processing_status,
                "extracted_type": r.txn_type,
                "extracted_amount": float(r.amount) if r.amount else None,
                "parsing_meta": r.parsing_meta
            })
            
        output_path = os.path.join(BASE_DIR, "tests", "step3_parsing_meta.json")
        with open(output_path, "w") as f:
            json.dump(report_data, f, indent=2)
            
        print(f"Extraction complete. Data saved to {output_path}")

if __name__ == "__main__":
    main()
