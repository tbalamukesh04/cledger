from app.database.database import engine
from sqlalchemy import text

# VACUUM cannot run inside a transaction, must use raw connection
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
    conn.execute(text("VACUUM ANALYZE transactions"))
    print("VACUUM complete.")

    # Verify dead tuples are gone
    r = conn.execute(text("""
        SELECT relname, n_live_tup, n_dead_tup 
        FROM pg_stat_user_tables 
        WHERE relname = 'transactions'
    """)).fetchone()
    print(f"After VACUUM — live: {r[1]}, dead: {r[2]}")