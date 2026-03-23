"""
test_classifier_eval.py — Classifier Evaluation Harness
========================================================
Evaluates the transaction classifier (scoring engine) directly in-process.

No webhook, no Redis, no worker process, no Gemini API calls are made.
The scoring engine is the unit under test. The harness imports
TransactionScorer and ProcessingContext directly and runs each dataset
message through the same code path the worker uses — minus the AI
extraction step, which is irrelevant to classifier accuracy.

This is correct because:
  - The classifier decision (is_transaction_candidate) is made entirely
    by TransactionScorer.evaluate() using regex-based feature extraction
    and weighted scoring.
  - That decision is independent of Gemini. Gemini only runs AFTER the
    classifier already produced a result.
  - Pulling the result from the DB after a full pipeline run would mix
    classifier latency with Gemini latency and worker batch scheduling,
    making the eval non-deterministic and slow.

Usage
-----
  # From the backend/ directory (no server or worker needed):
  python tests/test_classifier_eval.py

Requirements
------------
  - Python environment with app dependencies installed (pydantic, etc.)
  - classifier_eval_dataset.json present in the same directory as this script
  - No running services required

Output
------
  tests/classifier_eval_report.txt  — full per-message breakdown + summary metrics
"""

import os
import sys
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make app.* importable when run from backend/tests/ or backend/
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# Import the classifier components directly
# ---------------------------------------------------------------------------
from app.parsing.scoring_engine import TransactionScorer
from app.schemas.preprocessing import PreprocessedPayload, ProcessingContext
from app.ai.config import SCORING_WEIGHTS, SCORING_THRESHOLD

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATASET_PATH = Path(__file__).parent / "classifier_eval_dataset.json"
REPORT_PATH  = Path(__file__).parent / "classifier_eval_report.txt"

# ---------------------------------------------------------------------------
# Logging — stdout only; the report file is written separately
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("classifier_eval")


# ---------------------------------------------------------------------------
# Core classification function
# ---------------------------------------------------------------------------
def classify_message(text: str, scorer: TransactionScorer) -> dict:
    """
    Run a single message text through the scoring engine and return
    the full result: label, score, threshold, and rule breakdown.

    Replicates exactly what process_webhook_batch does before the AI call:
      1. Build a minimal PreprocessedPayload with the normalised text
      2. Wrap it in ProcessingContext
      3. Call scorer.evaluate(context)
      4. Read context.scoring for the result

    No DB writes, no Redis, no Gemini.
    """
    payload = PreprocessedPayload(
        raw_message_id=0,
        participant_id=0,
        normalized_timestamp=datetime.now(timezone.utc),
        message_id="eval_harness",
        message_type="text",
        normalized_text=text,
        message_hash="eval_harness",
        idempotency_identifier="eval_harness",
    )

    context = ProcessingContext(payload=payload)
    context = scorer.evaluate(context)
    s = context.scoring

    return {
        "label":                     "transaction" if s.is_transaction_candidate else "non_transaction",
        "score":                     s.total_score,
        "threshold":                 scorer.threshold,
        "is_candidate":              s.is_transaction_candidate,
        "rule_breakdown":            s.rule_breakdown,
        "amount_detected":           s.amount_detected,
        "currency_detected":         s.currency_detected,
        "date_detected":             s.date_detected,
        "transaction_verb_detected": s.transaction_verb_detected,
        "negative_context":          s.negative_context,
    }


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------
def run_evaluation():
    if not DATASET_PATH.exists():
        logger.error(f"Dataset not found at {DATASET_PATH}. Aborting.")
        sys.exit(1)

    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    total  = len(dataset)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    logger.info(f"Classifier evaluation run {run_id} — {total} entries")
    logger.info(f"Scoring weights   : {SCORING_WEIGHTS}")
    logger.info(f"Scoring threshold : {SCORING_THRESHOLD}")
    logger.info(f"Report path       : {REPORT_PATH}")
    logger.info("-" * 70)

    scorer  = TransactionScorer()
    records = []

    for idx, entry in enumerate(dataset):
        msg_text    = entry["message_text"]
        expected    = entry["expected_classification"]
        description = entry.get("description", "")

        result    = classify_message(msg_text, scorer)
        predicted = result["label"]
        correct   = (predicted == expected)

        verdict = "✓" if correct else "✗"
        logger.info(
            f"[{idx+1:3}/{total}] {verdict}  "
            f"expected={expected:<16} predicted={predicted:<16} "
            f"score={result['score']:>3}  "
            f"neg={result['negative_context']}  "
            f"verb={result['transaction_verb_detected']}  "
            f"amt={result['amount_detected']}  "
            f"curr={result['currency_detected']}"
        )
        if not correct:
            logger.warning(f"         MISMATCH → \"{msg_text[:80]}\"")

        records.append({
            "index":                     idx + 1,
            "message_text":              msg_text,
            "description":               description,
            "expected":                  expected,
            "predicted":                 predicted,
            "correct":                   correct,
            "score":                     result["score"],
            "threshold":                 result["threshold"],
            "rule_breakdown":            result["rule_breakdown"],
            "amount_detected":           result["amount_detected"],
            "currency_detected":         result["currency_detected"],
            "date_detected":             result["date_detected"],
            "transaction_verb_detected": result["transaction_verb_detected"],
            "negative_context":          result["negative_context"],
        })

    write_report(records, run_id, total)
    logger.info(f"Evaluation complete. Report written to {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def write_report(records: list, run_id: str, total: int):

    tx_expected    = [r for r in records if r["expected"] == "transaction"]
    nontx_expected = [r for r in records if r["expected"] == "non_transaction"]

    TP = [r for r in tx_expected    if r["predicted"] == "transaction"]
    FN = [r for r in tx_expected    if r["predicted"] == "non_transaction"]
    TN = [r for r in nontx_expected if r["predicted"] == "non_transaction"]
    FP = [r for r in nontx_expected if r["predicted"] == "transaction"]

    n_eval    = len(records)
    n_correct = len(TP) + len(TN)

    accuracy    = n_correct / n_eval if n_eval else 0.0
    precision   = len(TP) / (len(TP) + len(FP)) if (len(TP) + len(FP)) else 0.0
    recall      = len(TP) / (len(TP) + len(FN)) if (len(TP) + len(FN)) else 0.0
    f1          = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
    specificity = len(TN) / (len(TN) + len(FP)) if (len(TN) + len(FP)) else 0.0

    SEP  = "=" * 100
    SEP2 = "-" * 100

    lines = []
    def w(*args): lines.append(" ".join(str(a) for a in args))

    # --- Header ---
    w(SEP)
    w("CLASSIFIER EVALUATION REPORT")
    w(f"Run ID    : {run_id}")
    w(f"Generated : {datetime.now(timezone.utc).isoformat()}")
    w(f"Dataset   : {DATASET_PATH}")
    w(f"Weights   : {SCORING_WEIGHTS}")
    w(f"Threshold : {SCORING_THRESHOLD}")
    w(f"Total entries : {total}")
    w(SEP)

    # --- Summary metrics ---
    w()
    w("SUMMARY METRICS")
    w(SEP2)
    w(f"  {'Accuracy':<24}  {accuracy:.4f}   ({n_correct}/{n_eval} correct)")
    w(f"  {'Precision':<24}  {precision:.4f}   (TP / (TP+FP))   — of predicted transactions, how many are real")
    w(f"  {'Recall (Sensitivity)':<24}  {recall:.4f}   (TP / (TP+FN))   — of real transactions, how many were caught")
    w(f"  {'Specificity':<24}  {specificity:.4f}   (TN / (TN+FP))   — of real non-transactions, how many were blocked")
    w(f"  {'F1 Score':<24}  {f1:.4f}   (harmonic mean of precision and recall)")
    w()

    # --- Confusion matrix ---
    w("CONFUSION MATRIX")
    w(SEP2)
    w(f"  {'':34} {'Predicted: transaction':^26} {'Predicted: non_transaction':^26}")
    w(f"  {'Actual: transaction':<34} {'TP = ' + str(len(TP)):^26} {'FN = ' + str(len(FN)):^26}")
    w(f"  {'Actual: non_transaction':<34} {'FP = ' + str(len(FP)):^26} {'TN = ' + str(len(TN)):^26}")
    w()

    # --- Class breakdown ---
    w("CLASS BREAKDOWN")
    w(SEP2)
    w(f"  Transaction entries in dataset     : {len(tx_expected)}")
    w(f"    Correctly classified  (TP)       : {len(TP)}")
    w(f"    Missed — False Neg    (FN)       : {len(FN)}")
    w(f"  Non-transaction entries in dataset : {len(nontx_expected)}")
    w(f"    Correctly blocked     (TN)       : {len(TN)}")
    w(f"    Passed through — FP              : {len(FP)}")
    w()

    # --- False Positives ---
    w(SEP)
    w(f"FALSE POSITIVES  ({len(FP)})  — expected non_transaction, classified as transaction")
    w("  These messages were incorrectly routed to AI extraction.")
    w(SEP2)
    if FP:
        for r in FP:
            w(f"  [{r['index']:3}] \"{r['message_text'][:85]}\"")
            w(f"        score={r['score']}  threshold={r['threshold']}")
            w(f"        breakdown  : {r['rule_breakdown']}")
            w(f"        signals    : amount={r['amount_detected']}  currency={r['currency_detected']}"
              f"  verb={r['transaction_verb_detected']}  negative_context={r['negative_context']}")
            w(f"        description: {r['description']}")
            w()
    else:
        w("  None")
        w()

    # --- False Negatives ---
    w(SEP)
    w(f"FALSE NEGATIVES  ({len(FN)})  — expected transaction, classified as non_transaction")
    w("  These messages were incorrectly blocked from AI extraction.")
    w(SEP2)
    if FN:
        for r in FN:
            w(f"  [{r['index']:3}] \"{r['message_text'][:85]}\"")
            w(f"        score={r['score']}  threshold={r['threshold']}")
            w(f"        breakdown  : {r['rule_breakdown']}")
            w(f"        signals    : amount={r['amount_detected']}  currency={r['currency_detected']}"
              f"  verb={r['transaction_verb_detected']}  negative_context={r['negative_context']}")
            w(f"        description: {r['description']}")
            w()
    else:
        w("  None")
        w()

    # --- Score distribution ---
    w(SEP)
    w("SCORE DISTRIBUTION")
    w(SEP2)
    w(f"  {'Score':>6}  {'Count':>5}  {'Gate':>14}  {'TP':>4}  {'FN':>4}  {'TN':>4}  {'FP':>4}")
    w(SEP2)
    score_counts = Counter(r["score"] for r in records)
    for score in sorted(score_counts):
        at = [r for r in records if r["score"] == score]
        tp_at = sum(1 for r in at if r["expected"] == "transaction"     and r["predicted"] == "transaction")
        fn_at = sum(1 for r in at if r["expected"] == "transaction"     and r["predicted"] == "non_transaction")
        tn_at = sum(1 for r in at if r["expected"] == "non_transaction" and r["predicted"] == "non_transaction")
        fp_at = sum(1 for r in at if r["expected"] == "non_transaction" and r["predicted"] == "transaction")
        gate  = ">= threshold" if score >= SCORING_THRESHOLD else "< threshold"
        w(f"  {score:>6}  {score_counts[score]:>5}  {gate:>14}  {tp_at:>4}  {fn_at:>4}  {tn_at:>4}  {fp_at:>4}")
    w()

    # --- Full per-entry breakdown ---
    w(SEP)
    w("FULL PER-ENTRY BREAKDOWN")
    w(SEP2)
    w(f"  {'#':>3}  {'Expected':<16} {'Predicted':<16} {'Result':>6}  "
      f"{'Score':>5}  {'Neg':>3}  {'Verb':>4}  {'Amt':>3}  {'Curr':>4}  Message")
    w(SEP2)
    for r in records:
        verdict_str = "OK"   if r["correct"] else "FAIL"
        neg_str  = "Y" if r["negative_context"]          else "n"
        verb_str = "Y" if r["transaction_verb_detected"] else "n"
        amt_str  = "Y" if r["amount_detected"]           else "n"
        curr_str = "Y" if r["currency_detected"]         else "n"
        msg_preview = r["message_text"].replace("\n", " ")[:55]
        w(
            f"  {r['index']:>3}  {r['expected']:<16} {r['predicted']:<16} {verdict_str:>6}  "
            f"{r['score']:>5}  {neg_str:>3}  {verb_str:>4}  {amt_str:>3}  {curr_str:>4}  "
            f"{msg_preview!r}"
        )

    w(SEP)
    w("END OF REPORT")
    w(SEP)

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_evaluation()