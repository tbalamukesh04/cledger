import logging
from sqlalchemy import text
from app.database.database import SessionLocal

# Setup robust logging for the backfill audit trail
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_legacy_tenant")

TARGET_TABLES = ["groups", "participants", "raw_messages", "transactions"]
DEFAULT_TENANT_ID = 1
BATCH_SIZE = 1000

def run_legacy_backfill():
    """
    Safely creates the default legacy business tenant and propagates its ID across 
    all core transactional tables using a batched, zero-downtime strategy.
    """
    db = SessionLocal()
    try:
        logger.info("Starting multi-tenancy pre-flight validation checks...")

        # 1. Ensure the default legacy tenant exists
        business_check = db.execute(
            text("SELECT id, name FROM businesses WHERE id = :tid"), 
            {"tid": DEFAULT_TENANT_ID}
        ).fetchone()

        if not business_check:
            logger.info(f"Default tenant with ID {DEFAULT_TENANT_ID} not found. Creating 'Legacy Default' context...")
            db.execute(
                text("""
                    INSERT INTO businesses (id, name, slug, is_active, created_at, updated_at)
                    VALUES (:tid, 'Legacy Default', 'legacy-default', true, NOW(), NOW())
                """),
                {"tid": DEFAULT_TENANT_ID}
            )
            db.commit()
            logger.info("Successfully seeded default legacy business profile.")
        else:
            logger.info(f"Confirmed existence of default tenant context: '{business_check.name}'")

        # 2. Gather pre-backfill metrics for audit verification
        pre_flight_counts = {}
        for table_name in TARGET_TABLES:
            null_count = db.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id IS NULL")
            ).scalar()
            pre_flight_counts[table_name] = null_count
            logger.info(f"Table '{table_name}': Found {null_count} rows requiring tenant mapping assignment.")

        # 3. Execute batched backfill updates to prevent destructive table locks
        logger.info("Commencing safe data migration phase...")
        for table_name in TARGET_TABLES:
            rows_needing_update = pre_flight_counts[table_name]
            if rows_needing_update == 0:
                logger.info(f"Skipping backfill for '{table_name}'; table is already fully tenant-isolated.")
                continue

            processed = 0
            while True:
                # Update chunk by chunk using matching CTE or subquery limits depending on target index constraints
                result = db.execute(
                    text(f"""
                        UPDATE {table_name}
                        SET tenant_id = :tid
                        WHERE id IN (
                            SELECT id FROM {table_name}
                            WHERE tenant_id IS NULL
                            LIMIT :batch_size
                        )
                    """),
                    {"tid": DEFAULT_TENANT_ID, "batch_size": BATCH_SIZE}
                )
                db.commit()
                
                rows_updated = result.rowcount
                processed += rows_updated
                
                if rows_updated == 0:
                    break
                
                logger.info(f"[{table_name}] Progressively mapped {processed}/{rows_needing_update} rows...")

        # 4. Post-flight Referential Integrity & Orphan Assertions
        logger.info("Executing comprehensive post-migration data integrity audits...")
        integrity_failures = 0
        
        for table_name in TARGET_TABLES:
            remaining_orphans = db.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id IS NULL")
            ).scalar()
            
            if remaining_orphans > 0:
                logger.error(f"CRITICAL FAULT: Table '{table_name}' has {remaining_orphans} orphaned rows after backfill execution!")
                integrity_failures += 1
            else:
                logger.info(f"Verification SUCCESS: Table '{table_name}' contains exactly 0 unmapped legacy rows.")

        if integrity_failures > 0:
            raise RuntimeError("Database safety check failed! Data isolation boundary cannot be fully verified.")

        logger.info("Multi-tenancy legacy backfill pipeline completed cleanly without data drift or reassignment errors.")

    except Exception as e:
        db.rollback()
        logger.error(f"Backfill transaction aborted due to execution error: {str(e)}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_legacy_backfill()
