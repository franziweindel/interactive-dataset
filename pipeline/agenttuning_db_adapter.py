#!/usr/bin/env python3
"""
AgentTuning-DB adapter: converts AgentInstruct db tasks + BIRD databases
into Harbor-compatible task directories.

Each Harbor task contains:
  task.json        - task metadata, instruction, provenance
  init.sql         - MySQL initialization SQL (CREATE TABLE + INSERT)
  verifier.py      - outcome-based verifier
  oracle.py        - reference solution (replays trajectory SQL)
  Dockerfile       - runtime image definition
  docker-compose.yml - service orchestration
"""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from load_sqlite import convert_sqlite_to_mysql_sql


def extract_task_fields(row):
    """Extract structured fields from an AgentInstruct db conversation."""
    convs = row["conversations"]
    task_id = row["id"]

    # System prompt is turn 0
    system_prompt = convs[0]["value"] if convs else ""

    # Question + schema is turn 2
    question_full = convs[2]["value"] if len(convs) >= 3 else ""
    question_line = question_full.split("\n")[0].strip()

    # Extract table names
    table_names = re.findall(
        r"name of (?:the \d+\w+ table|this table) is (\w+)", question_full
    )

    # Extract SQL operations and results
    sql_ops = []
    final_answer = None

    for j, c in enumerate(convs):
        if c["from"] == "gpt" and "Action: Operation" in c["value"]:
            sql_match = re.search(r"```sql\s*(.*?)\s*```", c["value"], re.DOTALL)
            sql = sql_match.group(1).strip() if sql_match else ""
            traj_result = ""
            if j + 1 < len(convs) and convs[j + 1]["from"] == "human":
                traj_result = convs[j + 1]["value"].strip()
            sql_ops.append({"sql": sql, "result": traj_result})

        if c["from"] == "gpt" and "Final Answer:" in c["value"]:
            fa_match = re.search(r"Final Answer:\s*(.*)", c["value"])
            if fa_match:
                final_answer = fa_match.group(1).strip()

    # Determine task type
    task_type = "unknown"
    if sql_ops:
        first_sql_upper = sql_ops[0]["sql"].upper().strip()
        for prefix in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
            if first_sql_upper.startswith(prefix):
                task_type = prefix
                break

    return {
        "task_id": task_id,
        "system_prompt": system_prompt,
        "question_full": question_full,
        "question": question_line,
        "table_names": table_names,
        "sql_ops": sql_ops,
        "final_answer": final_answer,
        "task_type": task_type,
        "n_turns": len(convs),
    }


def generate_task_instruction(fields):
    """Generate the Harbor task instruction from extracted fields."""
    instruction = (
        "You are interacting with a MySQL database. "
        "You can execute SQL queries by calling the `execute_sql` tool with your query. "
        "When you have determined the answer, call the `submit_answer` tool with your final answer.\n\n"
    )
    instruction += f"Question: {fields['question_full']}"
    return instruction


def generate_init_sql(bird_db_dir, db_name):
    """Generate MySQL init SQL from a BIRD SQLite database."""
    sqlite_path = os.path.join(bird_db_dir, db_name, f"{db_name}.sqlite")
    if not os.path.isfile(sqlite_path):
        raise FileNotFoundError(f"BIRD database not found: {sqlite_path}")
    return convert_sqlite_to_mysql_sql(sqlite_path, "agentdb")


def generate_verifier(fields):
    """Generate a Python verifier script for the task."""
    final_answer = fields["final_answer"]
    task_type = fields["task_type"]

    return f'''#!/usr/bin/env python3
"""Verifier for task {fields["task_id"]}.
Checks the agent's submitted answer against the ground truth.
"""
import json
import sys
import re


GROUND_TRUTH = {json.dumps(final_answer)}
TASK_TYPE = {json.dumps(task_type)}


def normalize_answer(answer):
    """Normalize an answer for comparison."""
    if answer is None:
        return "0"
    s = str(answer).strip()
    # Strip surrounding brackets
    s = re.sub(r"^\\[(.*)\\]$", r"\\1", s)
    # Strip surrounding quotes
    s = re.sub(r'^["\\'](.*)["\\'"]$', r"\\1", s)
    # Normalize whitespace
    s = " ".join(s.split())
    # Normalize none/null/nan
    if s.lower() in ("none", "null", "nan", "n/a", ""):
        return "0"
    # Strip trailing .0 for integers
    if re.match(r"^-?\\d+\\.0+$", s):
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

    output = {{
        "success": result,
        "submitted": submitted,
        "ground_truth": GROUND_TRUTH,
        "task_id": {json.dumps(fields["task_id"])},
    }}
    print(json.dumps(output))
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
'''


def generate_oracle(fields):
    """Generate a Python oracle script that replays the reference solution."""
    sql_ops = fields["sql_ops"]
    final_answer = fields["final_answer"]

    return f'''#!/usr/bin/env python3
"""Oracle for task {fields["task_id"]}.
Replays the reference SQL solution and submits the known answer.
"""
import json
import subprocess
import sys


SQL_OPS = {json.dumps(sql_ops)}
FINAL_ANSWER = {json.dumps(final_answer)}


def execute_sql(sql, host="localhost", port=3306, user="root",
                password="agenttuning", database="agentdb"):
    """Execute SQL against the MySQL database."""
    proc = subprocess.run(
        ["mysql", "-h", host, "-P", str(port), "-u", user,
         f"-p{{password}}", "-N", "-e", f"USE {{database}}; {{sql}}"],
        capture_output=True, text=True, timeout=60,
    )
    return proc.stdout.strip()


def main():
    """Replay reference solution."""
    for i, op in enumerate(SQL_OPS):
        result = execute_sql(op["sql"])
        print(f"SQL[{{i}}]: {{op['sql'][:80]}}...")
        print(f"  Result: {{result[:200]}}")

    print(f"\\nFinal Answer: {{FINAL_ANSWER}}")

    output = {{
        "success": True,
        "answer": FINAL_ANSWER,
        "task_id": {json.dumps(fields["task_id"])},
    }}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
'''


def generate_docker_compose(db_name):
    """Generate docker-compose.yml for the task runtime."""
    return f"""version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: agenttuning
      MYSQL_DATABASE: agentdb
    ports:
      - "3306:3306"
    tmpfs:
      - /var/lib/mysql:size=2G
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --max-connections=100
      - --max-allowed-packet=256M
    volumes:
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: mysqladmin ping -h localhost -u root -pagenttuning
      interval: 5s
      timeout: 3s
      retries: 20
"""


def emit_harbor_task(fields, bird_db_dir, output_dir):
    """Emit a complete Harbor task directory."""
    task_id = fields["task_id"]
    db_name = fields.get("bird_db")

    task_dir = os.path.join(output_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)

    # 1. Task metadata
    task_json = {
        "id": task_id,
        "source": "agenttuning-db",
        "upstream_dataset": "THUDM/AgentInstruct",
        "upstream_split": "db",
        "upstream_benchmark": "BIRD",
        "bird_database": db_name,
        "task_type": fields["task_type"],
        "instruction": generate_task_instruction(fields),
        "ground_truth": fields["final_answer"],
        "n_reference_sql_ops": len(fields["sql_ops"]),
        "tools": [
            {
                "name": "execute_sql",
                "description": "Execute a SQL query against the MySQL database",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The SQL query to execute",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "submit_answer",
                "description": "Submit your final answer",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "answer": {
                            "type": "string",
                            "description": "The final answer to the question",
                        }
                    },
                    "required": ["answer"],
                },
            },
        ],
        "provenance": {
            "adapter": "agenttuning_db_adapter",
            "bird_db": db_name,
            "agentinstruct_id": task_id,
        },
    }

    with open(os.path.join(task_dir, "task.json"), "w") as f:
        json.dump(task_json, f, indent=2)

    # 2. Init SQL
    if db_name and bird_db_dir:
        init_sql = generate_init_sql(bird_db_dir, db_name)
        with open(os.path.join(task_dir, "init.sql"), "w") as f:
            f.write(init_sql)

    # 3. Verifier
    verifier = generate_verifier(fields)
    with open(os.path.join(task_dir, "verifier.py"), "w") as f:
        f.write(verifier)
    os.chmod(os.path.join(task_dir, "verifier.py"), 0o755)

    # 4. Oracle
    oracle = generate_oracle(fields)
    with open(os.path.join(task_dir, "oracle.py"), "w") as f:
        f.write(oracle)
    os.chmod(os.path.join(task_dir, "oracle.py"), 0o755)

    # 5. Docker compose
    compose = generate_docker_compose(db_name)
    with open(os.path.join(task_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)

    return task_dir


def convert_pilot(data_path, pilot_path, mapping_path, bird_db_dir, output_dir):
    """Convert the frozen pilot tasks."""
    with open(data_path) as f:
        ai_data = {r["id"]: r for r in json.load(f)}

    with open(pilot_path) as f:
        pilot = json.load(f)

    with open(mapping_path) as f:
        mapping = json.load(f)

    results = []
    for task_id, db_name in pilot.items():
        row = ai_data[task_id]
        fields = extract_task_fields(row)
        fields["bird_db"] = db_name

        task_dir = emit_harbor_task(fields, bird_db_dir, output_dir)
        results.append({"task_id": task_id, "dir": task_dir, "status": "emitted"})
        print(f"Emitted: {task_id} -> {task_dir}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data_agentinstruct_db.json")
    parser.add_argument("--pilot", default="reports/agenttuning_db_pilot.json")
    parser.add_argument("--mapping", default="reports/agenttuning_db_bird_mapping.json")
    parser.add_argument("--bird-db-dir", default="bird_data/dev_databases/dev_databases")
    parser.add_argument("--output", default="harbor_tasks")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    results = convert_pilot(
        args.data, args.pilot, args.mapping, args.bird_db_dir, args.output
    )
    print(f"\nEmitted {len(results)} tasks")
