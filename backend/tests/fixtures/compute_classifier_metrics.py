"""
compute_classifier_metrics.py — Accuracy Metrics Computation
=============================================================
Loads classifier_eval_results.json and computes a full suite of
classification performance metrics. Writes metrics to
classifier_eval_metrics.json and prints a formatted summary to stdout.

Metrics computed
----------------
  accuracy              — overall fraction of correct predictions
  precision             — TP / (TP + FP)
  recall                — TP / (TP + FN)  [sensitivity]
  specificity           — TN / (TN + FP)
  false_positive_rate   — FP / (FP + TN)  [1 - specificity]
  false_negative_rate   — FN / (FN + TP)  [1 - recall]
  f1_score              — harmonic mean of precision and recall
  confusion_matrix      — TP, FP, TN, FN raw counts
  score_distribution    — per-score bucket TP/FP/TN/FN counts
  fp_signal_analysis    — which signal combinations drive false positives
  fn_signal_analysis    — which signal combinations drive false negatives

Usage
-----
  python tests/compute_classifier_metrics.py

Output
------
  tests/classifier_eval_metrics.json  — machine-readable metrics
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).parent / "classifier_eval_results.json"
METRICS_PATH = Path(__file__).parent / "classifier_eval_metrics.json"


def load_results() -> list:
    if not RESULTS_PATH.exists():
        print(f"ERROR: Results file not found at {RESULTS_PATH}")
        sys.exit(1)
    with open(RESULTS_PATH) as f:
        return json.load(f)


def compute_metrics(records: list) -> dict:
    tx    = [r for r in records if r["expected_classification"] == "transaction"]
    nontx = [r for r in records if r["expected_classification"] == "non_transaction"]

    TP = [r for r in tx    if r["predicted_classification"] == "transaction"]
    FN = [r for r in tx    if r["predicted_classification"] == "non_transaction"]
    TN = [r for r in nontx if r["predicted_classification"] == "non_transaction"]
    FP = [r for r in nontx if r["predicted_classification"] == "transaction"]

    n        = len(records)
    n_tp, n_fn, n_tn, n_fp = len(TP), len(FN), len(TN), len(FP)
    n_correct = n_tp + n_tn

    def safe_div(a, b): return round(a / b, 6) if b else None

    accuracy            = safe_div(n_correct,      n)
    precision           = safe_div(n_tp,           n_tp + n_fp)
    recall              = safe_div(n_tp,           n_tp + n_fn)
    specificity         = safe_div(n_tn,           n_tn + n_fp)
    false_positive_rate = safe_div(n_fp,           n_fp + n_tn)
    false_negative_rate = safe_div(n_fn,           n_fn + n_tp)
    f1 = round((2 * precision * recall) / (precision + recall), 6) \
         if precision and recall else 0.0

    # --- Score distribution ---
    score_dist = {}
    all_scores = sorted({r["classification_score"] for r in records})
    for score in all_scores:
        bucket = [r for r in records if r["classification_score"] == score]
        score_dist[score] = {
            "count":     len(bucket),
            "gate":      ">= threshold" if score >= records[0]["threshold"] else "< threshold",
            "TP":        sum(1 for r in bucket if r["expected_classification"]=="transaction"     and r["predicted_classification"]=="transaction"),
            "FN":        sum(1 for r in bucket if r["expected_classification"]=="transaction"     and r["predicted_classification"]=="non_transaction"),
            "TN":        sum(1 for r in bucket if r["expected_classification"]=="non_transaction" and r["predicted_classification"]=="non_transaction"),
            "FP":        sum(1 for r in bucket if r["expected_classification"]=="non_transaction" and r["predicted_classification"]=="transaction"),
        }

    # --- FP signal pattern analysis ---
    def signal_key(r):
        parts = []
        if r["amount_detected"]:           parts.append("amount")
        if r["currency_detected"]:         parts.append("currency")
        if r["transaction_verb_detected"]: parts.append("verb")
        if r["negative_context"]:          parts.append("negative")
        return "+".join(parts) if parts else "no_signals"

    fp_patterns = Counter(signal_key(r) for r in FP)
    fn_patterns = Counter(signal_key(r) for r in FN)

    # --- FP root cause categorisation ---
    fp_root_causes = defaultdict(list)
    for r in FP:
        has_verb = r["transaction_verb_detected"]
        has_neg  = r["negative_context"]
        has_amt  = r["amount_detected"]
        has_curr = r["currency_detected"]
        score    = r["classification_score"]

        if has_neg and score >= r["threshold"]:
            cause = "negative_context_penalty_insufficient"
        elif has_verb and not has_neg and not has_amt and not has_curr:
            cause = "verb_only_no_amount_no_currency"
        elif not has_verb and not has_neg and (has_amt or has_curr):
            cause = "amount_currency_no_verb_no_negative"
        elif has_verb and not has_neg and (has_amt or has_curr):
            cause = "verb_amount_currency_missing_contextual_guard"
        else:
            cause = "other"
        fp_root_causes[cause].append({
            "index":   r["index"],
            "message": r["message_text"],
            "score":   r["classification_score"],
        })

    return {
        "run_summary": {
            "total_entries":              n,
            "correctly_classified":       n_correct,
            "transaction_entries":        len(tx),
            "non_transaction_entries":    len(nontx),
            "threshold":                  records[0]["threshold"] if records else None,
        },
        "confusion_matrix": {
            "TP": n_tp,
            "FN": n_fn,
            "TN": n_tn,
            "FP": n_fp,
        },
        "metrics": {
            "accuracy":            accuracy,
            "precision":           precision,
            "recall":              recall,
            "specificity":         specificity,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "f1_score":            f1,
        },
        "score_distribution":    score_dist,
        "fp_signal_patterns":    dict(fp_patterns.most_common()),
        "fn_signal_patterns":    dict(fn_patterns.most_common()),
        "fp_root_causes":        {k: v for k, v in fp_root_causes.items()},
        "false_positives":       [{"index": r["index"], "message": r["message_text"],
                                   "score": r["classification_score"],
                                   "description": r.get("description","")} for r in FP],
        "false_negatives":       [{"index": r["index"], "message": r["message_text"],
                                   "score": r["classification_score"],
                                   "description": r.get("description","")} for r in FN],
    }


def print_summary(m: dict):
    SEP  = "=" * 72
    SEP2 = "-" * 72
    rs   = m["run_summary"]
    cm   = m["confusion_matrix"]
    mt   = m["metrics"]

    print(SEP)
    print("CLASSIFIER ACCURACY METRICS")
    print(f"  Total entries        : {rs['total_entries']}")
    print(f"  Correctly classified : {rs['correctly_classified']}")
    print(f"  Threshold            : {rs['threshold']}")
    print(SEP)

    print()
    print("CONFUSION MATRIX")
    print(SEP2)
    print(f"  {'':30} {'Pred: transaction':^20} {'Pred: non_transaction':^20}")
    print(f"  {'Actual: transaction':<30} {'TP = '+str(cm['TP']):^20} {'FN = '+str(cm['FN']):^20}")
    print(f"  {'Actual: non_transaction':<30} {'FP = '+str(cm['FP']):^20} {'TN = '+str(cm['TN']):^20}")

    print()
    print("METRICS")
    print(SEP2)
    rows = [
        ("Accuracy",            mt["accuracy"],            "overall correct / total"),
        ("Precision",           mt["precision"],           "TP / (TP+FP)  — of flagged txns, how many are real"),
        ("Recall",              mt["recall"],              "TP / (TP+FN)  — of real txns, how many were caught"),
        ("Specificity",         mt["specificity"],         "TN / (TN+FP)  — of real non-txns, how many blocked"),
        ("False Positive Rate", mt["false_positive_rate"], "FP / (FP+TN)  — non-txns wrongly passed to AI"),
        ("False Negative Rate", mt["false_negative_rate"], "FN / (FN+TP)  — real txns wrongly blocked from AI"),
        ("F1 Score",            mt["f1_score"],            "harmonic mean of precision and recall"),
    ]
    for name, val, note in rows:
        val_str = f"{val:.4f}" if val is not None else "N/A"
        print(f"  {name:<22}  {val_str}   {note}")

    print()
    print("SCORE DISTRIBUTION")
    print(SEP2)
    print(f"  {'Score':>6}  {'Count':>5}  {'Gate':>14}  {'TP':>4}  {'FN':>4}  {'TN':>4}  {'FP':>4}")
    print(SEP2)
    for score, v in sorted(m["score_distribution"].items(), key=lambda x: int(x[0])):
        print(f"  {score:>6}  {v['count']:>5}  {v['gate']:>14}  "
              f"{v['TP']:>4}  {v['FN']:>4}  {v['TN']:>4}  {v['FP']:>4}")

    print()
    print("FP SIGNAL PATTERNS  (what signals drove false positives)")
    print(SEP2)
    for pattern, count in m["fp_signal_patterns"].items():
        print(f"  {count:>3}x  {pattern}")

    print()
    print("FP ROOT CAUSES")
    print(SEP2)
    for cause, entries in m["fp_root_causes"].items():
        print(f"  {cause}  ({len(entries)})")
        for e in entries:
            print(f"    [{e['index']:3}] score={e['score']}  \"{e['message'][:65]}\"")

    if m["false_negatives"]:
        print()
        print("FALSE NEGATIVES")
        print(SEP2)
        for e in m["false_negatives"]:
            print(f"  [{e['index']:3}] score={e['score']}  \"{e['message'][:65]}\"")
            print(f"         {e['description']}")
    else:
        print()
        print("FALSE NEGATIVES: None")

    print()
    print(SEP)
    print(f"Metrics written to: {METRICS_PATH}")
    print(SEP)


def main():
    records = load_results()
    metrics = compute_metrics(records)

    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print_summary(metrics)


if __name__ == "__main__":
    main()