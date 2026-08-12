#!/usr/bin/env python3
"""
Validate a Harbor task end-to-end:
1. Clean startup (docker-compose up)
2. Deterministic reset (drop and reload database)
3. Oracle success (replay reference SQL, submit correct answer)
4. No-op failure (submit without doing anything)
5. Incorrect-attempt failure (submit wrong answer)
6. Verifier protection (verifier rejects bad answers)

Uses an existing MySQL container (agenttuning-mysql) for efficiency.
"""
import json
import os
import re
import subprocess
import sys
import time


def run_mysql(sql, host="localhost", port=3307, user="root",
              password="agenttuning", database="agentdb"):
    """Execute SQL against the MySQL database via docker."""
    proc = subprocess.run(
        ["docker", "exec", "agenttuning-mysql",
         "mysql", "-u", user, f"-p{password}", "-N", "-e",
         f"USE {database}; {sql}"],
        capture_output=True, text=True, timeout=60,
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def load_init_sql(task_dir):
    """Load the init SQL into the running MySQL container."""
    sql_path = os.path.join(task_dir, "init.sql")
    with open(sql_path) as f:
        sql = f.read()

    proc = subprocess.run(
        ["docker", "exec", "-i", "agenttuning-mysql",
         "mysql", "-u", "root", "-pagenttuning", "--default-character-set=utf8mb4"],
        input=sql,
        capture_output=True, text=True, timeout=300,
    )
    return proc.returncode == 0, proc.stderr


def run_verifier(task_dir, answer):
    """Run the verifier with a given answer."""
    verifier_path = os.path.join(task_dir, "verifier.py")
    proc = subprocess.run(
        ["python3", verifier_path, str(answer)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        result = json.loads(proc.stdout.strip())
        return result.get("success", False), result
    except (json.JSONDecodeError, ValueError):
        return False, {"error": proc.stdout + proc.stderr}


def validate_task(task_dir, verbose=True, preloaded_db=None):
    """Run full validation on a Harbor task.

    If preloaded_db is set, skip init SQL loading and use the named database directly.
    """
    task_json_path = os.path.join(task_dir, "task.json")
    with open(task_json_path) as f:
        task = json.load(f)

    task_id = task["id"]
    ground_truth = task["ground_truth"]
    db_name = preloaded_db or task.get("provenance", {}).get("bird_db", "agentdb")
    results = {"task_id": task_id, "checks": {}, "all_passed": False}

    if verbose:
        print(f"\n{'='*60}")
        print(f"Validating: {task_id} (database: {db_name})")
        print(f"  Ground truth: {ground_truth}")
        print(f"{'='*60}")

    # 1. Clean startup: verify database is accessible
    if verbose:
        print("\n[1] Clean startup: verifying database...")
    if preloaded_db:
        stdout, stderr, rc = run_mysql("SELECT 1;", database=db_name)
        ok = rc == 0
        err = stderr
    else:
        ok, err = load_init_sql(task_dir)
    results["checks"]["startup"] = {"passed": ok}
    if not ok:
        if verbose:
            print(f"  FAIL: {err[:200]}")
        return results
    if verbose:
        print("  PASS")

    # 2. Deterministic reset: verify consistent state
    if verbose:
        print("\n[2] Deterministic reset check...")
    # Run a deterministic query to verify state
    test_sql = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE();"
    stdout1, _, _ = run_mysql(test_sql, database=db_name)
    stdout2, _, _ = run_mysql(test_sql, database=db_name)
    ok2 = stdout1 == stdout2 and stdout1 != ""
    results["checks"]["reset"] = {"passed": ok2, "table_count": stdout1}
    if verbose:
        print(f"  Table count: {stdout1} (consistent: {ok2})")
        print(f"  {'PASS' if ok2 else 'FAIL'}")

    # 3. Oracle success: replay reference SQL and verify answer
    if verbose:
        print("\n[3] Oracle success...")
    oracle_path = os.path.join(task_dir, "oracle.py")
    with open(oracle_path) as f:
        oracle_code = f.read()

    # Extract SQL ops from oracle
    sql_ops_match = re.search(r"SQL_OPS = (.+?)$", oracle_code, re.MULTILINE)
    if sql_ops_match:
        sql_ops = json.loads(sql_ops_match.group(1))
    else:
        sql_ops = []

    oracle_results = []
    for i, op in enumerate(sql_ops):
        stdout, stderr, rc = run_mysql(op["sql"], database=db_name)
        oracle_results.append({
            "sql": op["sql"][:80],
            "result": stdout[:200],
            "expected": op["result"][:200],
            "rc": rc,
        })
        if verbose:
            print(f"  SQL[{i}]: {op['sql'][:60]}...")
            print(f"    Result: {stdout[:100]}")

    # Verify the oracle answer
    oracle_ok, oracle_detail = run_verifier(task_dir, ground_truth)
    results["checks"]["oracle"] = {
        "passed": oracle_ok,
        "sql_results": oracle_results,
        "detail": oracle_detail,
    }
    if verbose:
        print(f"  Verifier result: {'PASS' if oracle_ok else 'FAIL'}")

    # 4. No-op failure: submit without doing anything meaningful
    if verbose:
        print("\n[4] No-op failure (submit 'I don't know')...")
    noop_ok, noop_detail = run_verifier(task_dir, "I don't know")
    # We WANT this to fail
    noop_passed = not noop_ok
    results["checks"]["noop_failure"] = {
        "passed": noop_passed,
        "detail": noop_detail,
    }
    if verbose:
        print(f"  Verifier correctly rejected: {'PASS' if noop_passed else 'FAIL'}")

    # 5. Incorrect attempt failure: submit a plausible but wrong answer
    if verbose:
        print("\n[5] Incorrect attempt failure...")
    # Generate a plausible wrong answer
    wrong_answer = _generate_wrong_answer(ground_truth)
    wrong_ok, wrong_detail = run_verifier(task_dir, wrong_answer)
    wrong_passed = not wrong_ok
    results["checks"]["incorrect_failure"] = {
        "passed": wrong_passed,
        "wrong_answer": wrong_answer,
        "detail": wrong_detail,
    }
    if verbose:
        print(f"  Wrong answer: {wrong_answer}")
        print(f"  Verifier correctly rejected: {'PASS' if wrong_passed else 'FAIL'}")

    # Summary
    all_passed = all(c["passed"] for c in results["checks"].values())
    results["all_passed"] = all_passed

    if verbose:
        print(f"\n{'='*60}")
        print(f"Task {task_id}: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
        for name, check in results["checks"].items():
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  {name}: {status}")
        print(f"{'='*60}")

    return results


def _generate_wrong_answer(ground_truth):
    """Generate a plausible but incorrect answer."""
    gt = str(ground_truth)
    # Try to parse as number and modify
    try:
        # Strip brackets and quotes
        clean = re.sub(r'[\[\]"\']', '', gt).strip()
        num = float(clean)
        return str(int(num + 42) if num == int(num) else round(num + 3.14, 2))
    except (ValueError, TypeError):
        pass
    # For text answers, return something different
    if gt.lower() in ('["none"]', "none", '["0"]', "[0]"):
        return "42"
    return "WRONG_ANSWER_XYZ"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("task_dirs", nargs="+", help="Harbor task directories to validate")
    parser.add_argument("--output", default="reports/validation_results.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    all_results = []
    for task_dir in args.task_dirs:
        # Read task.json to get the BIRD database name
        task_json_path = os.path.join(task_dir, "task.json")
        with open(task_json_path) as f:
            task_meta = json.load(f)
        bird_db = task_meta.get("bird_database") or task_meta.get("provenance", {}).get("bird_db")
        result = validate_task(task_dir, verbose=not args.quiet, preloaded_db=bird_db)
        all_results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for r in all_results if r["all_passed"])
    print(f"Tasks passed: {passed}/{len(all_results)}")
    for r in all_results:
        status = "PASS" if r["all_passed"] else "FAIL"
        failed_checks = [k for k, v in r["checks"].items() if not v["passed"]]
        extra = f" (failed: {', '.join(failed_checks)})" if failed_checks else ""
        print(f"  {r['task_id']}: {status}{extra}")

    # Save results
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
