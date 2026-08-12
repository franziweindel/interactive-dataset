# Interactive Dataset Quickstart

`interactive_dataset` converts existing interactive-agent data into validated Harbor tasks.

```text
source → download → classify → map to upstream assets → validate in runtime → emit Harbor tasks → verify
```

## Run

```bash
python3 pipeline/run_pipeline.py --source agenttuning-db
```

Options:

```bash
# Dev databases only (faster, ~58 validated tasks):
python3 pipeline/run_pipeline.py --source agenttuning-db --skip-training-dbs

# Classification + mapping only (no Docker/MySQL needed):
python3 pipeline/run_pipeline.py --source agenttuning-db --skip-mysql

# Custom output directory:
python3 pipeline/run_pipeline.py --source agenttuning-db --output my_tasks
```

## Prerequisites

- Python 3.9+ with `datasets`, `huggingface_hub`
- Docker (for MySQL validation and Harbor task runtime)
- ~2 GB disk for BIRD dev databases; ~5 GB additional for training databases

## Sources

| Source | Validated | Cost/task | Status |
|---|---|---|---|
| `agenttuning-db` | ~196 SELECT tasks | $0.00 | Adapter complete |

## Outputs

- `reports/pipeline_report.json` — machine-readable summary
- `reports/validation.json` — per-task validation status
- `reports/bird_mapping.json` — task → BIRD database mapping
- `harbor_tasks_auto/` — emitted Harbor task directories
- `findings/agenttuning-db.md` — source-specific analysis
