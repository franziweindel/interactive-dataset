# Starting Pipeline

This is the initial algorithm to implement for `interactive_dataset`.

Every step below describes behavior that should be implemented in the pipeline itself. Manual investigation is allowed during development only to discover useful behavior that can then be encoded into the generic pipeline or a source adapter.

When manual investigation finds a working procedure, test whether the implemented pipeline can reproduce the same result automatically.

The architecture may evolve based on evidence, but the semantic rules in `SYSTEM.md` remain mandatory.

## 1. Onboard or load the source adapter

The pipeline takes a source descriptor such as a registered source name, Hugging Face dataset, GitHub repository, or other public dataset location.

For a new source, the pipeline must construct a source adapter.

It should use deterministic inspection where possible and invoke a source-analysis LLM/agent where semantic investigation is required.

The resulting adapter should capture:

* what source rows represent;
* task families;
* instruction/source IDs;
* upstream benchmarks or data sources;
* runtime and interaction protocol;
* required assets;
* initialization/reset behavior;
* reference solutions or trajectories;
* expected outcomes/verifier information;
* rules for mapping source rows to upstream tasks/assets.

The source-analysis agent may inspect dataset samples, repositories/history, papers/docs, and linked upstream resources.

Source-level LLM analysis should run once per source or task family where possible, not independently for every row.

The pipeline must persist/cache established adapter knowledge and provenance.

For an already onboarded source:

1. load the existing adapter;
2. use it normally;
3. if validation exposes a previously unsupported or incorrectly modeled source behavior, invoke source analysis again;
4. update the adapter;
5. verify that the revised adapter resolves the failure and generalizes beyond the triggering example.

## 2. Recover and validate source tasks

For each row, the pipeline must use the source adapter to recover, where possible:

* instruction;
* upstream task/assets;
* intended runtime;
* initial/reset state;
* reference/oracle;
* expected outcome;
* verifier information.

The pipeline then validates the recovered task by:

1. initializing it;
2. running the reference/oracle;
3. requiring the expected outcome;
4. requiring no-op failure;
5. where practical, requiring a plausible incorrect attempt to fail.

Cheap mapping and validation should run source-wide where practical.

Every row must receive an explicit status rather than being silently dropped.

## 3. Diagnose failed recovery or validation

When recovery or validation fails, the pipeline must first diagnose whether the failure comes from reconstruction rather than from the source task.

Generic diagnosis should cover where applicable:

* missing/wrong assets or versions;
* incorrect source mapping;
* wrong initialization/reset;
* runtime or dialect mismatch;
* missing dependencies/services/configuration;
* conversion/serialization errors;
* harmless output normalization differences;
* nondeterminism or stale state.

Run deterministic diagnostics first.

If deterministic diagnosis is insufficient, the pipeline may invoke an LLM diagnostic agent with the failure evidence and ask it for:

* likely root causes;
* missing evidence;
* the smallest deterministic experiment that distinguishes them.

The pipeline must execute/verify the proposed experiment; LLM output alone is not evidence.

When a recurring failure pattern is confirmed, encode the solution into the generic pipeline or source adapter so future rows do not require the same LLM diagnosis.

## 4. Repair recoverable operational failures

The pipeline may repair failures only after they have been diagnosed as operational or compatibility defects.

Prefer deterministic repair.

Use LLM-assisted repair only when deterministic repair is insufficient and task semantics are already established.

Never repair by changing:

* instruction;
* expected outcome/ground truth;
* task-defining initial state;
* accepted outcomes;
* verifier semantics or thresholds.

Any modification to upstream-derived artifacts must pass:

* deterministic integrity checks;
* complete diff review;
* semantic review;
* upstream revalidation.

Missing provenance, unrecoverable state, or uncertain semantics must be classified as unresolved/blocked rather than repaired.

## 5. Establish the usable subset

The pipeline must classify rows into:

* directly valid;
* valid after source/runtime recovery;
* deterministically repaired;
* LLM-repaired;
* unresolved;
* blocked.

Record counts, reasons, and relevant costs in findings/reports.

Do not bulk-convert the full usable subset during pipeline development.

## 6. Select the validation pilot

The pipeline/development workflow must freeze five varied usable tasks as the regression pilot.

Prefer diversity in:

* task behavior;
* state;
* action type;
* runtime requirements;
* verifier type;
* complexity.

If the source contains materially different task families, ensure each claimed supported family is exercised.

## 7. Build reusable runtime environments

The pipeline must group tasks that can share runtimes or heavy assets.

Follow `HARBOR.md`.

Prefer:

```text
shared runtime/assets
+
task-specific initialization
```

over unrelated per-task images.

Require:

* clean startup;
* health checks;
* deterministic reset;
* isolated task state.

## 8. Establish upstream-to-container parity

The pipeline must run the same trusted reference/oracle in:

```text
validated upstream runtime
→ outcome

containerized runtime
→ outcome
```

and require equivalent outcomes.

Parity failures must be routed back through the same diagnosis/repair stages rather than handled with task-ID-specific fixes.

## 9. Emit and validate Harbor tasks

For validated tasks, the pipeline must emit valid Harbor tasks following `HARBOR.md` and the current Harbor documentation.

Generate or reuse:

* instruction;
* task initialization/configuration;
* environment;
* interaction adapter;
* protected outcome-based verifier;
* oracle/solution;
* provenance.

Validate through Harbor with:

* startup/reset;
* oracle success;
* no-op failure;
* plausible incorrect-attempt failure;
* upstream outcome parity;
* verifier protection.

Run representative real-agent Harbor executions for materially different task/runtime families within the project LLM budget.

## 10. TaskTrove round trip and generalization

The pipeline must pack accepted Harbor tasks into TaskTrove, freshly extract them, and rerun Harbor validation.

Then run the unchanged pipeline on a small unseen sample from the same source.

Also test unseen failure cases where available to verify that automated recovery/diagnosis generalizes beyond the examples used to develop it.

If manual investigation was required during development, convert recurring useful behavior into pipeline/adapter logic and retest automatically.

When the fixed pilot and unseen sample satisfy `EVALUATION.md`, stop.

Do not convert the full dataset during pipeline development. Full-source conversion will be run separately.
