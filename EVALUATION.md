# Pipeline Evaluation

Evaluation answers two questions:

1. Is the source data actually convertible?
2. Does the conversion pipeline work reliably and cheaply?

## 1. Source audit

Run the upstream-validation stage across all rows when reasonably cheap.

Report:

- total rows;
- successfully mapped rows;
- directly valid rows;
- operational failures;
- semantic/ground-truth/verifier failures;
- missing-runtime/assets/reset failures;
- blocked rows by reason;
- usable-row yield.

A row is usable only when its original task semantics can be defended and validated.

## 2. Repair experiment

Evaluate deterministic and LLM-assisted repair separately.

Report:

- repair-eligible rows;
- deterministic repair successes;
- LLM repair attempts;
- LLM repair successes;
- rejected/uncertain repairs;
- rescue rate overall and by failure class;
- total LLM repair cost;
- cost per repair attempt;
- cost per successfully rescued row;
- semantic-audit rejection rate.

Use these results to decide whether model-assisted repair is worth retaining for that source.

Do not count a semantic change as a rescue.

## 3. Five-task conversion pilot

Select five representative usable tasks and freeze them.

Each must pass:

- reproducible source/upstream acquisition;
- runtime startup;
- deterministic reset;
- interaction smoke test;
- upstream-to-container oracle parity;
- Harbor validation;
- oracle success;
- no-op failure;
- incorrect-attempt failure;
- verifier protection;
- TaskTrove packing;
- fresh extraction and revalidation.

Report every task individually.

## 4. Generalization test

After all five pass, run a small unseen sample of usable rows without changing the pipeline specifically for them.

Report:

- number attempted;
- number accepted;
- failures by stage;
- any generic fixes required;
- whether the fixed five-task regression suite still passes afterward.

Task-ID-specific hidden fixes count as failure to generalize.

## 5. Efficiency

Track where practical:

- LLM calls;
- total LLM spend;
- LLM spend per accepted task;
- runtime/image builds;
- runtime reuse/cache hits;
- repair attempts;
- wall-clock time by major stage.

Primary optimization target:

> maximize faithfully accepted-task yield while minimizing manual intervention and LLM cost per accepted task.

## 6. Adapter completion

A source adapter is ready when:

- the source audit is complete enough to define its usable subset;
- the repair strategy has been evaluated;
- all five fixed pilot tasks pass end to end;
- a small unseen sample passes without task-specific hacks;
- total development cost remains within the budget in `SYSTEM.md`.

At that point stop. Full-source conversion is a separate operation.
