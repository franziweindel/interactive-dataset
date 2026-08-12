# interactive-dataset

> **Status: In Development** — This pipeline is under active construction. The architecture is functional but not yet production-ready.

Converts existing interactive-agent datasets into validated, reproducible [Harbor](https://harborframework.com) tasks suitable for agentic RL training via [TaskTrove](https://huggingface.co/datasets/open-thoughts/TaskTrove).

## What it does

```
source dataset
  → download + analyze
  → recover upstream assets (databases, environments)
  → classify + map tasks
  → validate against runtime (MySQL, etc.)
  → deterministic repair where safe
  → emit Harbor tasks
  → verify (oracle, no-op rejection, incorrect-attempt rejection)
```

## Quick start

```bash
pip install datasets huggingface_hub
python3 pipeline/run_pipeline.py --source agenttuning-db
```

Requires Docker (for MySQL runtime). See [QUICKSTART.md](QUICKSTART.md) for options.

## Current state

| Source | Tasks | Validated | Cost/task | Status |
|---|---|---|---|---|
| `agenttuning-db` | 538 | 196 SELECT | $0.00 | Adapter complete |
| `agenttuning-os` | — | — | — | Not started |
| `agenttuning-kg` | — | — | — | Not started |

### agenttuning-db results

- **196 / 538** tasks validated end-to-end (SELECT queries from BIRD benchmark databases)
- **5/5** pilot tasks pass all Harbor checks
- **10/10** unseen generalization tasks pass
- **$0.00** LLM cost (all deterministic after adapter construction)
- 172 DML tasks blocked (120 underdetermined initial state, 49 INSERT partially recoverable, 3 broken)
- See [findings/agenttuning-db.md](findings/agenttuning-db.md) for details

### Pilot Harbor tasks

Two small demo tasks are included in [`pilot_harbor_tasks/`](pilot_harbor_tasks/):

- `db_5` — multi-table JOIN query on a retail orders database (0.2 MB)
- `db_20` — subquery + GROUP BY on a toxicology database (1.6 MB)

These are real validated Harbor tasks. Larger tasks are generated at runtime by the pipeline (databases can be 100+ MB).

Full-scale conversion outputs will be uploaded to HuggingFace separately.

## Project structure

```
pipeline/
  run_pipeline.py        # Main entry point
  agenttuning_db_adapter.py  # agenttuning-db source adapter
  load_sqlite.py         # SQLite → MySQL converter
  validate_task.py       # Harbor validation harness

pilot_harbor_tasks/      # Demo Harbor tasks (small, committed)
  db_5/
  db_20/

findings/                # Source-specific empirical findings
reports/                 # Machine-readable pipeline outputs

SYSTEM.md                # Project rules and objectives
STARTING_PIPELINE.md     # Pipeline architecture
EVALUATION.md            # Acceptance criteria
SOURCES.md               # Target datasets and references
HARBOR_TASKTROVE.md      # Harbor/TaskTrove requirements
QUICKSTART.md            # User-facing run instructions
```

## Design principles

- **Semantic preservation**: Never change task instructions, ground truth, or verifier semantics to make tasks pass
- **Deterministic first**: Prefer deterministic inspection and repair over LLM calls
- **Reusable adapters**: Source-specific knowledge in adapters, generic logic in pipeline
- **Evidence-based**: Every finding backed by executed validation, not assumptions
- **Fail closed**: Unresolvable tasks are blocked, not silently dropped

## License

TBD
