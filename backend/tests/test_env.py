# backend/test_env.py
import os
from dotenv import load_dotenv

# Load the variables from the .env file
load_dotenv()

# Fetch the variables
env_mode = os.getenv("ENVIRONMENT")
db_url = os.getenv("DATABASE_URL")
redis_url = os.getenv("REDIS_URL")

# Print them out to verify
print("--- Environment Variables Check ---")
print(f"Environment: {env_mode}")
print(f"Database URL: {db_url}")
print(f"Redis URL: {redis_url}")
print("-----------------------------------")