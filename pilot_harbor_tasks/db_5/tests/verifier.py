#!/usr/bin/env python3
"""Verifier for task db_5.
Checks the agent's submitted answer against the ground truth.
"""
import json
import sys
import re


GROUND_TRUTH = "[7523698.790000005]"
TASK_TYPE = "SELECT"


def normalize_answer(answer):
    """Normalize an answer for comparison."""
    if answer is None:
        return "0"
    s = str(answer).strip()
    # Strip surrounding brackets
    s = re.sub(r"^\[(.*)\]$", r"\1", s)
    # Strip surrounding quotes
    s = re.sub(r'^["\'](.*)["\'"]$', r"\1", s)
    # Normalize whitespace
    s = " ".join(s.split())
    # Normalize none/null/nan
    if s.lower() in ("none", "null", "nan", "n/a", ""):
        return "0"
    # Strip trailing .0 for integers
    if re.match(r"^-?\d+\.0+$", s):
        s = s.split(".")[0]
    return s


def compare_answers(submitted, ground_truth):
    """Compare submitted answer to ground truth."""
    sub_norm = normalize_answer(submitted)
    gt_norm = normalize_answer(ground_truth)

    if sub_norm == gt_norm:
        return True

    # Try numeric comparison
    try:
        sub_f = float(sub_norm.replace(",", "").replace("%", ""))
        gt_f = float(gt_norm.replace(",", "").replace("%", ""))
        return abs(sub_f - gt_f) < 0.01
    except (ValueError, TypeError):
        pass

    # Case-insensitive string comparison
    if sub_norm.lower() == gt_norm.lower():
        return True

    return False


def main():
    """Read submitted answer from stdin or file, compare to ground truth."""
    if len(sys.argv) > 1:
        submitted = sys.argv[1]
    else:
        submitted = sys.stdin.read().strip()

    result = compare_answers(submitted, GROUND_TRUTH)

    output = {
        "success": result,
        "submitted": submitted,
        "ground_truth": GROUND_TRUTH,
        "task_id": "db_5",
    }
    print(json.dumps(output))
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
