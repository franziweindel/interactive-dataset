#!/usr/bin/env python3
"""Oracle for task db_5.
Replays the reference SQL solution and submits the known answer.
"""
import json
import subprocess
import sys


SQL_OPS = [{"sql": "SELECT SUM(T2.priceEach * T2.quantityOrdered) FROM `products` AS T1 INNER JOIN `orderdetails` AS T2 ON T1.productCode = T2.productCode INNER JOIN `orders` AS T3 ON T2.orderNumber = T3.orderNumber WHERE T3.status = 'Shipped' AND T3.orderDate BETWEEN '2003-01-01' AND '2004-12-31'", "result": "[(7523698.790000005,)]"}]
FINAL_ANSWER = "[7523698.790000005]"


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
        "task_id": "db_5",
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
