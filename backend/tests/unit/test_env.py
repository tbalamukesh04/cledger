import os
from dotenv import load_dotenv

def test_environment_variables():
    load_dotenv()

    env_mode = os.getenv("ENVIRONMENT")
    db_url = os.getenv("DATABASE_URL")
    redis_url = os.getenv("REDIS_URL")

    assert env_mode is not None, "ENVIRONMENT variable is not set."
    assert db_url is not None, "DATABASE_URL variable is not set."
    assert redis_url is not None, "REDIS_URL variable is not set."