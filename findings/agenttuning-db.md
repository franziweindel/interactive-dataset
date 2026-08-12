# agenttuning-db - Source Findings

Last updated: 2026-08-12

## Source

- **Dataset:** `THUDM/AgentInstruct` HuggingFace, `db` split
- **Total rows:** 538
- **Format:** Conversation trajectories with `id` and `conversations` fields
- **Upstream benchmark:** NOT AgentBench (despite SOURCES.md assumption). SELECT tasks come from **BIRD text-to-SQL benchmark** databases. DML tasks are **GPT-4 self-instruct** with no source database.
- **Upstream paper:** arXiv:2310.12823 (AgentTuning)

## Automated pipeline

All findings below are reproduced automatically by:

```bash
python3 pipeline/run_pipeline.py --source agenttuning-db
```

No manual pre-mapping, pre-classification, or task-specific fixes are required. The pipeline downloads data, builds the BIRD mapping, starts MySQL, validates tasks, selects a pilot, emits Harbor tasks, and runs generalization tests.

## Key structural findings

1. The AgentInstruct db split is **SFT training data**. Ground truth is implicit in the demonstrated trajectory's final answer - there are no separate labels.

2. Task descriptions contain table column headers but **NOT row data**. Database contents are recovered from BIRD benchmark SQLite files.

3. **All 172 DML tasks are synthetic self-instruct**, not BIRD-derived. Column-level schema verification showed 0% genuine matches against BIRD databases.

4. The BIRD databases used for trajectory generation appear to be a **mix of dev and training set versions**, and possibly older snapshots. This creates schema and data mismatches against the current BIRD release.

## Task classification

| Category | Count | Status |
|---|---|---|
| SELECT (BIRD-derived) | 360 | See validation below |
| Synthetic INSERT | 49 | Partially recoverable |
| Synthetic UPDATE | 63 | Blocked - underdetermined initial state |
| Synthetic DELETE | 57 | Blocked - underdetermined initial state |
| Blocked (no SQL execution) | 5 | Broken trajectory |
| Blocked (unresolved errors) | 3 | Broken trajectory |
| Needs review | 1 | |

## SELECT task validation (360 tasks)

### Automated validation results

From the automated pipeline (single command, no manual intervention):

| Metric | Value |
|---|---|
| Tasks mapped to BIRD databases | 358 |
| Validated (SQL matches trajectory) | 182 |
| Validated via backtick repair | 14 |
| **Total validated** | **196** |
| Data mismatch | 47 |
| SQL error | 115 |

The previous manual investigation validated 170 (later expanded to 199 with INSERT tasks). The automated pipeline validates 196 SELECT tasks - comparable coverage with minor differences from BIRD table-name mapping approach.

### Backtick repair

A deterministic, semantics-preserving repair: `` `table.column` `` → `` `table`.`column` ``

The pipeline applies this automatically. No semantic changes - the intended column reference is preserved.

### Root causes of remaining failures

- **SQL errors:** Schema mismatches between current BIRD databases and the version used by AgentTuning (missing columns/tables), plus genuine trajectory SQL bugs (ambiguous columns, unquoted identifiers)
- **Data mismatches:** Same SQL produces different results against current BIRD databases vs. older snapshots

## DML tasks (172)

### Provenance

Exhaustive investigation confirmed no source databases exist for any DML task. All were generated via GPT-4 self-instruct with schema-only descriptions.

### INSERT recovery

INSERT tasks into empty tables have deterministically recoverable initial state. The pipeline classifies these as `insert` (49 tasks). Full DML verification requires further adapter work.

### UPDATE/DELETE (120 tasks) - BLOCKED

Initial state cannot be uniquely determined. The trajectory provides no information about pre-existing rows.

## Pipeline validation

### Automated pilot (5 tasks, auto-selected)

All 5 pilot tasks pass: startup, reset, oracle, no-op rejection, incorrect-attempt rejection.

### Automated generalization test (10 unseen tasks)

10/10 unseen tasks pass all checks without task-specific fixes.

### Runtime architecture

- MySQL 8.0 container (auto-started by pipeline)
- BIRD SQLite databases converted to MySQL via `load_sqlite.py`
- Tasks share the MySQL instance; each BIRD database loaded once
- Backtick repair applied automatically
- Verifier: answer normalization + numeric tolerance (0.01)
- Oracle: replay exact trajectory SQL

## LLM cost

**Adapter execution: $0.00** - Once constructed, the adapter runs entirely deterministically.

**Adapter construction: not yet automated.** The current adapter encodes knowledge discovered during manual investigation - that BIRD is the upstream source, that table-name matching is the correct mapping strategy, that backtick quoting is the dominant repairable defect, that all DML tasks are synthetic self-instruct, etc. This investigation was performed by the developer, not by an LLM source-analysis agent.

For a genuinely new source, the pipeline's step 1 ("Onboard or load the source adapter") should invoke an LLM to discover this kind of structural knowledge. That agent workflow is not yet implemented - the `agenttuning-db` adapter is hand-authored from manual findings. This means the adapter is correct and validated, but the *construction* cost is not reflected in the $0 figure. An honest estimate for LLM-based source analysis to reach equivalent adapter knowledge would be roughly $0.50–$2.00 (a few thousand tokens of dataset inspection + upstream repo analysis + paper reading), amortized across all 538 rows.

## Automated vs. manual results

| Metric | Manual investigation | Automated pipeline |
|---|---|---|
| Total rows | 538 | 538 |
| Mapped to BIRD | 388 | 358 |
| Validated SELECT | 170 | 196 |
| Backtick repairs | 14 | 14 |
| Pilot passed | 5/5 | 5/5 |
| Unseen passed | 10/10 | 10/10 |

**Mapping difference (388 → 358):** The manual count included 28 false-positive DML→BIRD mappings based on coincidental table-name overlap. The automated pipeline doesn't attempt to map DML tasks to BIRD (they are classified separately), so it correctly excludes these. 358 + ~2 unmapped edge cases = ~360 SELECT tasks.

**Validation improvement (170 → 196):** The automated pipeline applies the improved `deep_match()` normalization consistently to all tasks, recovering formatting-difference false negatives that the manual process handled in separate passes. The backtick repair (14 tasks) is also applied inline rather than as a separate step.

## Summary

| Category | Count | Validated | Blocked |
|---|---|---|---|
| SELECT (validated) | 196 | 196 | - |
| SELECT (data mismatch) | 47 | - | 47 |
| SELECT (SQL error) | 115 | - | 115 |
| INSERT | 49 | - | 49 (not yet in pipeline) |
| UPDATE/DELETE | 120 | - | 120 |
| Broken trajectory | 8 | - | 8 |
| Other | 3 | - | 3 |
| **Total** | **538** | **196** | **342** |
