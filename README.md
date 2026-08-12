# interactive-dataset

> **Still under development.**

Converts interactive-agent datasets into validated [Harbor](https://harborframework.com) tasks for agentic RL training via [TaskTrove](https://huggingface.co/datasets/open-thoughts/TaskTrove).

## What it does

```
source dataset
  -> download + analyze
  -> recover upstream assets (databases, environments)
  -> classify + map tasks
  -> validate against runtime (MySQL, etc.)
  -> deterministic repair where safe
  -> emit Harbor tasks
  -> verify (oracle, no-op rejection, incorrect-attempt rejection)
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
| `agenttuning-os` | - | - | - | Not started |
| `agenttuning-kg` | - | - | - | Not started |

### agenttuning-db

196 of 538 tasks validated end-to-end (SELECT queries against BIRD benchmark databases). 5/5 pilot tasks and 10/10 unseen generalization tasks pass all Harbor checks. No LLM cost since the adapter runs fully deterministically.

172 DML tasks are blocked: 120 have underdetermined initial state, 49 INSERT tasks are partially recoverable, 3 have broken trajectories.

See [findings/agenttuning-db.md](findings/agenttuning-db.md) for the full breakdown.

### Pilot Harbor tasks

Two small demo tasks are included in [`pilot_harbor_tasks/`](pilot_harbor_tasks/):

- `db_5` - multi-table JOIN query on a retail orders database (0.2 MB)
- `db_20` - subquery + GROUP BY on a toxicology database (1.6 MB)

These are real validated Harbor tasks shipped as a demonstration. The full set of validated Harbor tasks will be uploaded to HuggingFace later (many tasks have databases over 100 MB so they don't fit in a git repo).
