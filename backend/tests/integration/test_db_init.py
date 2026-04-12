def test_db_initialization():
    from app.database.database import engine
    assert engine is not None, "Database engine failed to initialize."
