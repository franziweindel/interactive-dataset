#!/usr/bin/env python3
"""
interactive_dataset pipeline — single-command entry point.

Usage:
    python3 pipeline/run_pipeline.py --source agenttuning-db [options]

This automates the full pipeline from SYSTEM.md / STARTING_PIPELINE.md:
  1. Download source data
  2. Load/construct source adapter
  3. Recover upstream assets (BIRD databases)
  4. Classify and map all tasks
  5. Start runtime (MySQL), load databases
  6. Validate tasks (SQL execution + result comparison)
  7. Apply deterministic repairs (backtick fix)
  8. Select pilot tasks
  9. Emit Harbor tasks for pilot
  10. Validate pilot through Harbor checks
  11. Generalization test on unseen sample
  12. Write reports
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"
FINDINGS_DIR = PROJECT_ROOT / "findings"
BIRD_DEV_DIR = PROJECT_ROOT / "bird_data" / "dev_databases" / "dev_databases"
BIRD_TRAIN_DIR = PROJECT_ROOT / "bird_data" / "train_databases"
BIRD_TRAIN_ALT = PROJECT_ROOT / "bird_data" / "train_dl" / "train" / "train_databases"
BIRD_TRAIN_META = PROJECT_ROOT / "bird_data" / "train_meta" / "train"

MYSQL_CONTAINER = "agenttuning-mysql"
MYSQL_PASSWORD = "agenttuning"
LARGE_DB_THRESHOLD = 500 * 1024 * 1024  # 500 MB

sys.path.insert(0, str(PIPELINE_DIR))
from load_sqlite import convert_sqlite_to_mysql_sql

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def log(msg):
    print(f"[pipeline] {msg}", flush=True)


def run_mysql(sql, database="mysql"):
    proc = subprocess.run(
        ["docker", "exec", MYSQL_CONTAINER,
         "mysql", "-u", "root", f"-p{MYSQL_PASSWORD}", "-N", "-e",
         f"USE `{database}`; {sql}"],
        capture_output=True, text=True, timeout=60, errors="replace",
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def fix_backtick_quoting(sql):
    """Deterministic repair: `table.column` → `table`.`column`"""
    return re.sub(r'`(\w+)\.(\w+)`', r'`\1`.`\2`', sql)


def extract_task_fields(row):
    """Extract structured fields from an AgentInstruct db conversation."""
    convs = row["conversations"]
    task_id = row["id"]
    question_full = convs[2]["value"] if len(convs) >= 3 else ""
    question_line = question_full.split("\n")[0].strip()

    table_names = re.findall(
        r"name of (?:the \d+\w+ table|this table) is (\w+)", question_full
    )

    sql_ops = []
    final_answer = None
    has_error = False

    for j, c in enumerate(convs):
        if c["from"] == "gpt" and "Action: Operation" in c["value"]:
            sql_match = re.search(r"```sql\s*(.*?)\s*```", c["value"], re.DOTALL)
            sql = sql_match.group(1).strip() if sql_match else ""
            traj_result = ""
            if j + 1 < len(convs) and convs[j + 1]["from"] == "human":
                traj_result = convs[j + 1]["value"].strip()
                if any(kw in traj_result for kw in ["1054", "1064", "Error", "ERROR"]):
                    has_error = True
            sql_ops.append({"sql": sql, "result": traj_result})
        if c["from"] == "gpt" and "Final Answer:" in c["value"]:
            fa_match = re.search(r"Final Answer:\s*(.*)", c["value"])
            if fa_match:
                final_answer = fa_match.group(1).strip()

    task_type = "unknown"
    if sql_ops:
        first_upper = sql_ops[0]["sql"].upper().strip()
        for prefix in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
            if first_upper.startswith(prefix):
                task_type = prefix
                break

    return {
        "task_id": task_id,
        "question_full": question_full,
        "question": question_line,
        "table_names": table_names,
        "sql_ops": sql_ops,
        "final_answer": final_answer,
        "task_type": task_type,
        "n_turns": len(convs),
        "n_sql_ops": len(sql_ops),
        "has_error": has_error,
    }


def deep_match(mysql_out, traj_out):
    """Compare MySQL tab-separated output with trajectory Python-tuple output."""
    if not mysql_out and not traj_out:
        return True
    if not mysql_out and traj_out.strip() in ("[]", ""):
        return True
    m = mysql_out.strip()
    t = traj_out.strip()
    t = re.sub(r"^\[", "", t).rstrip("]")
    t = re.sub(r"Decimal\('([^']*)'\)", r"\1", t)
    # Flatten tuples to lines
    tuples = re.findall(r"\(([^)]*)\)", t)
    if tuples:
        t_lines = []
        for tp in tuples:
            vals = [v.strip().strip("'\"").rstrip(",").strip() for v in tp.split(",")]
            t_lines.append("\t".join(v for v in vals if v))
        t_joined = "\n".join(t_lines)
    else:
        t_joined = t.replace("'", "").replace('"', "").strip(",").strip()
    m_norm = " ".join(m.split())
    t_norm = " ".join(t_joined.split())
    if m_norm == t_norm:
        return True
    # Single value numeric
    try:
        return abs(float(m_norm.replace(",", "")) - float(t_norm.replace(",", ""))) < 0.01
    except Exception:
        pass
    return m_norm.lower() == t_norm.lower()


# ---------------------------------------------------------------------------
# Step 1: Download source data
# ---------------------------------------------------------------------------

def download_agentinstruct_db(dest_path):
    """Download THUDM/AgentInstruct db split and save as JSON."""
    if dest_path.exists():
        log(f"Source data already exists: {dest_path}")
        with open(dest_path) as f:
            return json.load(f)
    log("Downloading THUDM/AgentInstruct db split...")
    from datasets import load_dataset
    ds = load_dataset("THUDM/AgentInstruct", split="db")
    data = [{"id": row["id"], "conversations": row["conversations"]} for row in ds]
    with open(dest_path, "w") as f:
        json.dump(data, f)
    log(f"Downloaded {len(data)} rows → {dest_path}")
    return data


def download_bird_dev(bird_data_dir):
    """Download BIRD dev databases if not present."""
    if BIRD_DEV_DIR.exists() and any(BIRD_DEV_DIR.iterdir()):
        log(f"BIRD dev databases already present: {BIRD_DEV_DIR}")
        return
    log("Downloading BIRD dev databases...")
    from huggingface_hub import hf_hub_download
    zip_path = hf_hub_download(
        repo_id="nlile/BIRD-bench", repo_type="dataset",
        filename="dev_databases.zip", local_dir=str(bird_data_dir),
    )
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(bird_data_dir / "dev_databases")
    log("BIRD dev databases extracted.")


def download_bird_train_metadata(bird_data_dir):
    """Download BIRD training metadata (train.json) for table mapping."""
    train_json = BIRD_TRAIN_META / "train.json"
    if train_json.exists():
        log(f"BIRD train metadata already present: {train_json}")
        return
    log("Downloading BIRD train.json for table mapping...")
    from huggingface_hub import hf_hub_download
    hf_hub_download(
        repo_id="prem-research/birdbench", repo_type="dataset",
        filename="train/train.json", local_dir=str(bird_data_dir / "train_meta"),
    )
    log("BIRD train metadata downloaded.")


def download_bird_train_db(db_name, bird_data_dir):
    """Download a single BIRD training database."""
    dest = BIRD_TRAIN_DIR / db_name / f"{db_name}.sqlite"
    if dest.exists():
        return str(dest)
    alt = BIRD_TRAIN_ALT / db_name / f"{db_name}.sqlite"
    if alt.exists():
        return str(alt)
    log(f"  Downloading training DB: {db_name}...")
    from huggingface_hub import hf_hub_download
    try:
        dl_path = hf_hub_download(
            repo_id="prem-research/birdbench", repo_type="dataset",
            filename=f"train/train_databases/{db_name}/{db_name}.sqlite",
            local_dir=str(bird_data_dir / "train_dl"),
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dl_path, dest)
        return str(dest)
    except Exception as e:
        log(f"  Failed to download {db_name}: {e}")
        return None


def get_sqlite_path(db_name):
    """Find the SQLite file for a BIRD database (dev or training)."""
    for base in [BIRD_DEV_DIR, BIRD_TRAIN_DIR, BIRD_TRAIN_ALT]:
        p = base / db_name / f"{db_name}.sqlite"
        if p.exists():
            return str(p)
    return None


# ---------------------------------------------------------------------------
# Step 2: Classify and map tasks
# ---------------------------------------------------------------------------

def classify_tasks(data):
    """Classify all rows and extract fields."""
    tasks = []
    for row in data:
        fields = extract_task_fields(row)
        tid = fields["task_id"]
        no_sql = fields["n_sql_ops"] == 0
        all_errors = fields["has_error"] and fields["final_answer"] is None

        if no_sql:
            status = "blocked_no_sql"
        elif all_errors:
            status = "blocked_unresolved_errors"
        elif fields["task_type"] == "SELECT":
            status = "select"
        elif fields["task_type"] == "INSERT":
            status = "insert"
        elif fields["task_type"] in ("UPDATE", "DELETE"):
            status = "blocked_underdetermined_state"
        else:
            status = "needs_review"

        fields["status"] = status
        tasks.append(fields)
    return tasks


def build_bird_table_index():
    """Build table-name → BIRD-database mapping from SQLite files + train metadata."""
    db_tables = {}

    # Dev databases (from actual SQLite files)
    if BIRD_DEV_DIR.exists():
        for db_dir in BIRD_DEV_DIR.iterdir():
            sqlite_path = db_dir / f"{db_dir.name}.sqlite"
            if sqlite_path.is_file():
                try:
                    conn = sqlite3.connect(str(sqlite_path))
                    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                    tables = {r[0] for r in cur.fetchall()}
                    conn.close()
                    db_tables[db_dir.name] = tables
                except Exception:
                    pass

    # Training databases (from train.json metadata — SQL-extracted table names)
    train_json = BIRD_TRAIN_META / "train.json"
    if train_json.exists():
        with open(train_json) as f:
            train_data = json.load(f)
        for entry in train_data:
            db_id = entry["db_id"]
            sql = entry.get("SQL", "")
            tables = set()
            for m in re.findall(r'(?:FROM|JOIN|INTO|UPDATE)\s+`?(\w+)`?', sql, re.IGNORECASE):
                if m.upper() not in ("SELECT", "WHERE", "SET", "VALUES", "AS", "ON", "FROM"):
                    tables.add(m)
            if db_id not in db_tables:
                db_tables[db_id] = set()
            db_tables[db_id].update(tables)

    return db_tables


def map_tasks_to_bird(tasks, db_tables):
    """Map each SELECT task to its BIRD database by table-name matching."""
    mapping = {}
    for t in tasks:
        if t["status"] != "select" or not t["table_names"]:
            continue
        task_tables = set(t["table_names"])
        candidates = []
        for db_id, db_tbls in db_tables.items():
            if task_tables.issubset(db_tbls):
                candidates.append(db_id)
        if candidates:
            mapping[t["task_id"]] = sorted(candidates)[0]
    return mapping


# ---------------------------------------------------------------------------
# Step 3: MySQL runtime
# ---------------------------------------------------------------------------

def ensure_mysql():
    """Start MySQL container if not running."""
    # Check if running
    proc = subprocess.run(
        ["docker", "exec", MYSQL_CONTAINER, "mysqladmin", "ping",
         "-h", "localhost", "-u", "root", f"-p{MYSQL_PASSWORD}"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        log("MySQL container already running.")
        return

    # Start it
    log("Starting MySQL container...")
    subprocess.run(["docker", "rm", "-f", MYSQL_CONTAINER],
                   capture_output=True, text=True)
    subprocess.run([
        "docker", "run", "-d", "--name", MYSQL_CONTAINER,
        "-e", f"MYSQL_ROOT_PASSWORD={MYSQL_PASSWORD}",
        "-p", "3307:3306",
        "-v", "/tmp/interactive-dataset-mysql:/var/lib/mysql",
        "mysql:8.0",
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_unicode_ci",
        "--max-connections=100",
        "--innodb-buffer-pool-size=1G",
        "--max-allowed-packet=256M",
    ], check=True, capture_output=True, text=True)

    # Wait for ready
    for _ in range(60):
        proc = subprocess.run(
            ["docker", "exec", MYSQL_CONTAINER, "mysqladmin", "ping",
             "-h", "localhost", "-u", "root", f"-p{MYSQL_PASSWORD}"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            log("MySQL ready.")
            return
        time.sleep(3)
    raise RuntimeError("MySQL did not start within 3 minutes")


def load_bird_db_into_mysql(db_name, sqlite_path):
    """Load a BIRD SQLite database into the MySQL container."""
    # Check if already loaded
    stdout, _, rc = run_mysql("SELECT 1;", db_name)
    if rc == 0:
        return True
    sql = convert_sqlite_to_mysql_sql(sqlite_path, db_name)
    proc = subprocess.run(
        ["docker", "exec", "-i", MYSQL_CONTAINER,
         "mysql", "-u", "root", f"-p{MYSQL_PASSWORD}",
         "--default-character-set=utf8mb4"],
        input=sql, capture_output=True, text=True, timeout=600, errors="replace",
    )
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Step 4: Validate tasks
# ---------------------------------------------------------------------------

def validate_select_task(task, db_name):
    """Run the first SQL operation in MySQL and compare with trajectory."""
    sql_ops = task["sql_ops"]
    if not sql_ops:
        return "no_sql", None

    first_sql = sql_ops[0]["sql"]
    traj_result = sql_ops[0]["result"]

    # Try original SQL
    stdout, stderr, rc = run_mysql(first_sql, db_name)
    if rc != 0:
        # Try backtick repair
        fixed = fix_backtick_quoting(first_sql)
        if fixed != first_sql:
            stdout, stderr, rc = run_mysql(fixed, db_name)
            if rc == 0 and deep_match(stdout, traj_result):
                return "validated_backtick_repair", stdout

    if rc != 0:
        return "sql_error", stderr[:200]

    if deep_match(stdout, traj_result):
        return "validated", stdout
    else:
        return "data_mismatch", stdout[:200]


# ---------------------------------------------------------------------------
# Step 5: Pilot selection + emission + validation
# ---------------------------------------------------------------------------

def select_pilot(validated_tasks, mapping, n=5):
    """Select diverse pilot tasks."""
    by_db = {}
    for t in validated_tasks:
        db = mapping.get(t["task_id"])
        if db and db not in by_db:
            by_db[db] = t
    pilot = list(by_db.values())[:n]
    # If fewer than n databases, add more from the largest db group
    if len(pilot) < n:
        used_ids = {t["task_id"] for t in pilot}
        for t in validated_tasks:
            if t["task_id"] not in used_ids:
                pilot.append(t)
                used_ids.add(t["task_id"])
            if len(pilot) >= n:
                break
    return pilot[:n]


def emit_harbor_task_from_fields(fields, bird_db_dir, output_dir):
    """Emit a Harbor task directory from extracted fields."""
    from agenttuning_db_adapter import (
        generate_task_instruction, generate_verifier,
        generate_oracle, generate_docker_compose, generate_init_sql,
    )
    task_id = fields["task_id"]
    db_name = fields.get("bird_db")
    task_dir = os.path.join(output_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)

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
        "provenance": {
            "adapter": "agenttuning_db",
            "bird_db": db_name,
            "agentinstruct_id": task_id,
        },
    }
    with open(os.path.join(task_dir, "task.json"), "w") as f:
        json.dump(task_json, f, indent=2)

    if db_name:
        sqlite_path = get_sqlite_path(db_name)
        if sqlite_path:
            init_sql = convert_sqlite_to_mysql_sql(sqlite_path, "agentdb")
            with open(os.path.join(task_dir, "init.sql"), "w") as f:
                f.write(init_sql)

    verifier = generate_verifier(fields)
    with open(os.path.join(task_dir, "verifier.py"), "w") as f:
        f.write(verifier)
    os.chmod(os.path.join(task_dir, "verifier.py"), 0o755)

    oracle = generate_oracle(fields)
    with open(os.path.join(task_dir, "oracle.py"), "w") as f:
        f.write(oracle)
    os.chmod(os.path.join(task_dir, "oracle.py"), 0o755)

    compose = generate_docker_compose(db_name)
    with open(os.path.join(task_dir, "docker-compose.yml"), "w") as f:
        f.write(compose)

    return task_dir


def run_harbor_validation(task_dir, db_name):
    """Run oracle/verifier/no-op/incorrect checks against a pre-loaded MySQL DB."""
    task_json_path = os.path.join(task_dir, "task.json")
    with open(task_json_path) as f:
        task = json.load(f)

    ground_truth = task["ground_truth"]
    checks = {}

    # 1. Startup — verify DB accessible
    stdout, stderr, rc = run_mysql("SELECT 1;", db_name)
    checks["startup"] = rc == 0

    # 2. Reset — verify consistent state
    s1, _, _ = run_mysql(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE();",
        db_name)
    s2, _, _ = run_mysql(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE();",
        db_name)
    checks["reset"] = s1 == s2 and s1 != ""

    # 3. Oracle — replay SQL, verify answer
    oracle_path = os.path.join(task_dir, "oracle.py")
    with open(oracle_path) as f:
        oracle_code = f.read()
    sql_ops_match = re.search(r"SQL_OPS = (.+?)$", oracle_code, re.MULTILINE)
    sql_ops = json.loads(sql_ops_match.group(1)) if sql_ops_match else []
    for op in sql_ops:
        sql = fix_backtick_quoting(op["sql"])
        run_mysql(sql, db_name)

    verifier_path = os.path.join(task_dir, "verifier.py")
    proc = subprocess.run(
        ["python3", verifier_path, str(ground_truth)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        result = json.loads(proc.stdout.strip())
        checks["oracle"] = result.get("success", False)
    except Exception:
        checks["oracle"] = False

    # 4. No-op failure
    proc = subprocess.run(
        ["python3", verifier_path, "I don't know"],
        capture_output=True, text=True, timeout=30,
    )
    try:
        result = json.loads(proc.stdout.strip())
        checks["noop_rejected"] = not result.get("success", True)
    except Exception:
        checks["noop_rejected"] = False

    # 5. Incorrect attempt
    wrong = "WRONG_42_XYZ"
    try:
        clean = re.sub(r'[\[\]"\']', '', str(ground_truth)).strip()
        num = float(clean)
        wrong = str(int(num + 42))
    except Exception:
        pass
    proc = subprocess.run(
        ["python3", verifier_path, wrong],
        capture_output=True, text=True, timeout=30,
    )
    try:
        result = json.loads(proc.stdout.strip())
        checks["incorrect_rejected"] = not result.get("success", True)
    except Exception:
        checks["incorrect_rejected"] = False

    all_passed = all(checks.values())
    return {"task_id": task["id"], "checks": checks, "all_passed": all_passed}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="interactive_dataset pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", required=True,
                        help="Source name (e.g., agenttuning-db)")
    parser.add_argument("--output", default="harbor_tasks",
                        help="Output directory for Harbor tasks")
    parser.add_argument("--skip-training-dbs", action="store_true",
                        help="Skip downloading BIRD training databases (dev only)")
    parser.add_argument("--pilot-size", type=int, default=5)
    parser.add_argument("--unseen-size", type=int, default=10)
    parser.add_argument("--skip-mysql", action="store_true",
                        help="Skip MySQL validation (classification + mapping only)")
    args = parser.parse_args()

    if args.source != "agenttuning-db":
        log(f"Source '{args.source}' not yet supported. Available: agenttuning-db")
        sys.exit(1)

    REPORTS_DIR.mkdir(exist_ok=True)
    FINDINGS_DIR.mkdir(exist_ok=True)
    bird_data_dir = PROJECT_ROOT / "bird_data"
    bird_data_dir.mkdir(exist_ok=True)

    # ── Step 1: Download source data ──
    log("=" * 60)
    log("STEP 1: Download source data")
    data_path = PROJECT_ROOT / "data_agentinstruct_db.json"
    data = download_agentinstruct_db(data_path)
    log(f"Loaded {len(data)} rows")

    # ── Step 2: Download BIRD databases ──
    log("=" * 60)
    log("STEP 2: Download BIRD databases")
    download_bird_dev(bird_data_dir)
    if not args.skip_training_dbs:
        download_bird_train_metadata(bird_data_dir)

    # ── Step 3: Classify tasks ──
    log("=" * 60)
    log("STEP 3: Classify tasks")
    tasks = classify_tasks(data)
    status_counts = {}
    for t in tasks:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
    for k, v in sorted(status_counts.items(), key=lambda x: -x[1]):
        log(f"  {k}: {v}")

    # ── Step 4: Map SELECT tasks to BIRD databases ──
    log("=" * 60)
    log("STEP 4: Map tasks to BIRD databases")
    db_tables = build_bird_table_index()
    log(f"BIRD database index: {len(db_tables)} databases")
    mapping = map_tasks_to_bird(tasks, db_tables)
    log(f"Tasks mapped to BIRD databases: {len(mapping)}")

    # Save mapping
    with open(REPORTS_DIR / "bird_mapping.json", "w") as f:
        json.dump(mapping, f, indent=2)

    if args.skip_mysql:
        log("Skipping MySQL validation (--skip-mysql)")
        # Save classification report
        classification_report = {
            "total": len(tasks),
            "status_counts": status_counts,
            "mapped_to_bird": len(mapping),
        }
        with open(REPORTS_DIR / "classification.json", "w") as f:
            json.dump(classification_report, f, indent=2)
        log("Classification complete. Run without --skip-mysql for full validation.")
        return

    # ── Step 5: Start MySQL ──
    log("=" * 60)
    log("STEP 5: Start MySQL runtime")
    ensure_mysql()

    # ── Step 6: Load BIRD databases and validate tasks ──
    log("=" * 60)
    log("STEP 6: Load databases + validate tasks")

    # Determine which databases to load
    dev_db_names = {d.name for d in BIRD_DEV_DIR.iterdir() if d.is_dir()} if BIRD_DEV_DIR.exists() else set()
    needed_dbs = set(mapping.values())
    train_dbs_needed = needed_dbs - dev_db_names

    # Load dev databases
    for db_name in sorted(needed_dbs & dev_db_names):
        sqlite_path = get_sqlite_path(db_name)
        if sqlite_path:
            ok = load_bird_db_into_mysql(db_name, sqlite_path)
            log(f"  {db_name}: {'OK' if ok else 'FAILED'}")

    # Download + load training databases
    if not args.skip_training_dbs:
        for db_name in sorted(train_dbs_needed):
            sqlite_path = get_sqlite_path(db_name)
            if not sqlite_path:
                sqlite_path = download_bird_train_db(db_name, bird_data_dir)
            if not sqlite_path:
                continue
            if os.path.getsize(sqlite_path) > LARGE_DB_THRESHOLD:
                log(f"  {db_name}: SKIP (>{LARGE_DB_THRESHOLD // (1024*1024)} MB)")
                continue
            ok = load_bird_db_into_mysql(db_name, sqlite_path)
            log(f"  {db_name}: {'OK' if ok else 'FAILED'}")

    # Validate all mapped SELECT tasks
    log("Validating SELECT tasks...")
    validation_results = {}
    task_by_id = {t["task_id"]: t for t in tasks}

    for tid, db_name in mapping.items():
        t = task_by_id[tid]
        if t["status"] != "select":
            continue
        status, detail = validate_select_task(t, db_name)
        validation_results[tid] = status

    val_counts = {}
    for v in validation_results.values():
        val_counts[v] = val_counts.get(v, 0) + 1
    log("Validation results:")
    for k, v in sorted(val_counts.items(), key=lambda x: -x[1]):
        log(f"  {k}: {v}")

    with open(REPORTS_DIR / "validation.json", "w") as f:
        json.dump(validation_results, f, indent=2)

    # ── Step 7: Select pilot ──
    log("=" * 60)
    log("STEP 7: Select pilot tasks")
    validated_tasks = [task_by_id[tid] for tid, v in validation_results.items()
                       if v.startswith("validated")]
    pilot = select_pilot(validated_tasks, mapping, n=args.pilot_size)
    pilot_ids = [t["task_id"] for t in pilot]
    log(f"Pilot tasks: {pilot_ids}")

    pilot_map = {t["task_id"]: mapping[t["task_id"]] for t in pilot}
    with open(REPORTS_DIR / "pilot.json", "w") as f:
        json.dump(pilot_map, f, indent=2)

    # ── Step 8: Emit Harbor tasks for pilot ──
    log("=" * 60)
    log("STEP 8: Emit Harbor tasks")
    output_dir = str(PROJECT_ROOT / args.output)
    os.makedirs(output_dir, exist_ok=True)

    for t in pilot:
        t["bird_db"] = mapping[t["task_id"]]
        bird_db_dir = str(BIRD_DEV_DIR) if t["bird_db"] in dev_db_names else str(BIRD_TRAIN_DIR)
        task_dir = emit_harbor_task_from_fields(t, bird_db_dir, output_dir)
        log(f"  Emitted: {t['task_id']} → {task_dir}")

    # ── Step 9: Validate pilot through Harbor checks ──
    log("=" * 60)
    log("STEP 9: Validate pilot")
    pilot_results = []
    for t in pilot:
        task_dir = os.path.join(output_dir, t["task_id"])
        result = run_harbor_validation(task_dir, t["bird_db"])
        status = "PASS" if result["all_passed"] else "FAIL"
        failed = [k for k, v in result["checks"].items() if not v]
        extra = f" ({', '.join(failed)})" if failed else ""
        log(f"  {result['task_id']}: {status}{extra}")
        pilot_results.append(result)

    pilot_pass = sum(1 for r in pilot_results if r["all_passed"])
    log(f"Pilot: {pilot_pass}/{len(pilot_results)} passed")

    # ── Step 10: Generalization test ──
    log("=" * 60)
    log("STEP 10: Generalization test on unseen tasks")
    import random
    random.seed(42)
    unseen_pool = [task_by_id[tid] for tid, v in validation_results.items()
                   if v.startswith("validated") and tid not in set(pilot_ids)]
    unseen = random.sample(unseen_pool, min(args.unseen_size, len(unseen_pool)))
    unseen_ids = [t["task_id"] for t in unseen]
    log(f"Unseen tasks: {unseen_ids}")

    unseen_output = str(PROJECT_ROOT / "harbor_tasks_unseen")
    os.makedirs(unseen_output, exist_ok=True)
    unseen_results = []
    for t in unseen:
        t["bird_db"] = mapping[t["task_id"]]
        bird_db_dir = str(BIRD_DEV_DIR) if t["bird_db"] in dev_db_names else str(BIRD_TRAIN_DIR)
        task_dir = emit_harbor_task_from_fields(t, bird_db_dir, unseen_output)
        result = run_harbor_validation(task_dir, t["bird_db"])
        status = "PASS" if result["all_passed"] else "FAIL"
        log(f"  {result['task_id']}: {status}")
        unseen_results.append(result)

    unseen_pass = sum(1 for r in unseen_results if r["all_passed"])
    log(f"Unseen: {unseen_pass}/{len(unseen_results)} passed")

    # ── Step 11: Write final report ──
    log("=" * 60)
    log("STEP 11: Write reports")

    total_validated = sum(1 for v in validation_results.values() if v.startswith("validated"))

    report = {
        "source": "agenttuning-db",
        "total_rows": len(data),
        "classification": status_counts,
        "mapped_to_bird": len(mapping),
        "validation": val_counts,
        "total_validated": total_validated,
        "pilot": {
            "ids": pilot_ids,
            "passed": pilot_pass,
            "total": len(pilot_results),
        },
        "unseen": {
            "ids": unseen_ids,
            "passed": unseen_pass,
            "total": len(unseen_results),
        },
        "llm_cost_usd": 0.0,
    }

    with open(REPORTS_DIR / "pipeline_report.json", "w") as f:
        json.dump(report, f, indent=2)

    log(f"\n{'='*60}")
    log("PIPELINE COMPLETE")
    log(f"{'='*60}")
    log(f"Total rows: {len(data)}")
    log(f"Mapped to BIRD: {len(mapping)}")
    log(f"Validated: {total_validated}")
    log(f"Pilot: {pilot_pass}/{len(pilot_results)} passed")
    log(f"Unseen: {unseen_pass}/{len(unseen_results)} passed")
    log(f"Reports: {REPORTS_DIR}")
    log(f"Harbor tasks: {output_dir}")


if __name__ == "__main__":
    main()
