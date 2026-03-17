import os

# --- Scoring Rubric Weights ---
# These are the base points awarded for successful AI extractions.
WEIGHT_AMOUNT = int(os.getenv("SCORING_WEIGHT_AMOUNT", "2"))
WEIGHT_CURRENCY = int(os.getenv("SCORING_WEIGHT_CURRENCY", "2"))
WEIGHT_DATE = int(os.getenv("SCORING_WEIGHT_DATE", "2"))
WEIGHT_VERB = int(os.getenv("SCORING_WEIGHT_VERB", "2"))

# Penalty applied if a negative context (e.g., a question or future intent) is detected
WEIGHT_NEGATIVE = int(os.getenv("SCORING_WEIGHT_NEGATIVE", "-4"))

# --- Classification Threshold ---
# Minimum score required to classify a message as a valid transaction.
# Example: 6 points means we need at least 3 valid signals (e.g., amount + currency + verb)
TRANSACTION_THRESHOLD = int(os.getenv("SCORING_TRANSACTION_THRESHOLD", "6"))