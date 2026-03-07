# metrics.py
# Computes precision, recall, F1 by comparing two element-set dicts.

from typing import Dict, Set, Tuple


def compute(
    ground_truth: Dict[str, Set[str]],
    extracted:    Dict[str, Set[str]],
) -> Dict[str, dict]:
    """
    Returns per-category and overall metrics.
    Each value is a dict: {tp, fp, fn, recall, precision, f1}
    """
    categories = ["classes", "fields", "methods",
                  "inherits", "implements", "associates", "depends_on"]
    results = {}

    total_tp = total_fp = total_fn = 0

    for cat in categories:
        gt  = ground_truth.get(cat, set())
        ext = extracted.get(cat, set())
        tp  = len(gt & ext)
        fp  = len(ext - gt)
        fn  = len(gt - ext)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        results[cat] = _scores(tp, fp, fn)

    results["overall"] = _scores(total_tp, total_fp, total_fn)
    return results


def consistency(
    extracted_a: Dict[str, Set[str]],
    extracted_b: Dict[str, Set[str]],
) -> float:
    """Jaccard similarity between two diagram extractions (0–100%)."""
    inter = union = 0
    for cat in set(extracted_a) | set(extracted_b):
        a = extracted_a.get(cat, set())
        b = extracted_b.get(cat, set())
        inter += len(a & b)
        union += len(a | b)
    return round(inter / union * 100, 1) if union else 100.0


def _scores(tp: int, fp: int, fn: int) -> dict:
    precision = round(tp / (tp + fp) * 100, 1) if (tp + fp) else 100.0
    recall    = round(tp / (tp + fn) * 100, 1) if (tp + fn) else 100.0
    f1_denom  = precision + recall
    f1        = round(2 * precision * recall / f1_denom, 1) if f1_denom else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "recall": recall, "precision": precision, "f1": f1}