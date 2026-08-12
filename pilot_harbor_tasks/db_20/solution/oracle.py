#!/usr/bin/env python3
"""Oracle for task db_20.
Replays the reference SQL solution and submits the known answer.
"""
import json
import subprocess
import sys


SQL_OPS = [{"sql": "SELECT `bond_type`, COUNT(*) AS count FROM `bond` WHERE `molecule_id` = (SELECT `molecule_id` FROM `molecule` WHERE `label` = 'TR018') GROUP BY `bond_type` ORDER BY count DESC LIMIT 1", "result": "[]"}]
FINAL_ANSWER = "[\"none\"]"


def execute_sql(sql, host="localhost", port=3306, user="root",
                password="agenttuning", database="agentdb"):
    """Execute SQL against the MySQL database."""
    proc = subprocess.run(
        ["mysql", "-h", host, "-P", str(port), "-u", user,
         f"-p{password}", "-N", "-e", f"USE {database}; {sql}"],
        capture_output=True, text=True, timeout=60,
    )
    return proc.stdout.strip()


def main():
    """Replay reference solution."""
    for i, op in enumerate(SQL_OPS):
        result = execute_sql(op["sql"])
        print(f"SQL[{i}]: {op['sql'][:80]}...")
        print(f"  Result: {result[:200]}")

    print(f"\nFinal Answer: {FINAL_ANSWER}")

    output = {
        "success": True,
        "answer": FINAL_ANSWER,
        "task_id": "db_20",
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
