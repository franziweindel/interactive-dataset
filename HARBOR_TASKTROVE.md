# Harbor and TaskTrove

This document defines project-specific requirements for Harbor task emission and TaskTrove packaging.

Do not use this file as a replacement for Harbor documentation. Before implementing or substantially modifying task emission, read the current documentation and inspect a few existing tasks.

## Required references

Read at least:

* Harbor Task Tutorial:
  https://www.harborframework.com/docs/tasks/task-tutorial
* Harbor Task Structure:
  https://www.harborframework.com/docs/tasks
* Harbor Agents:
  https://www.harborframework.com/docs/agents
* Harbor Terminus-2 agent:
  https://www.harborframework.com/docs/agents/terminus-2
* Harbor Getting Started / `harbor run`:
  https://www.harborframework.com/docs/getting-started
* TaskTrove dataset:
  https://huggingface.co/datasets/open-thoughts/TaskTrove

When format details matter, inspect the installed Harbor version and current implementation rather than relying on old examples.

## Harbor output

The final output must be a valid Harbor task, not merely an internal pipeline representation.

A task generally uses the current Harbor equivalents of:

```text
instruction.md
task.toml
environment/
solution/
tests/
```

Internal files such as `task.json`, `oracle.py`, or intermediate runtime definitions are fine during conversion, but an accepted task must execute and validate through Harbor.

Preserve the task semantics defined in `SYSTEM.md`.

## Environment reuse

Do not create an independent image or duplicate large identical assets for every task unless genuinely necessary.

Prefer:

1. shared runtime images across many tasks;
2. shared images/assets per heavy upstream environment where useful;
3. small task-specific initialization/configuration;
4. task-specific images only when the actual environment differs.

Separate:

* shared runtime: OS, packages, database server, interaction tools;
* shared heavy assets: databases, repositories, snapshots;
* task-specific state: instruction, initialization parameters, expected outcome, verifier configuration.

For example, multiple AgentInstruct tasks using the same BIRD database should not automatically each package another full copy of that database.

Measure storage/startup tradeoffs rather than assuming the first working architecture is final.

## Docker / Compose

Use the simplest Harbor-supported environment mechanism that faithfully reproduces the task.

For Harbor Compose tasks, follow the current documented convention:

```text
environment/docker-compose.yaml
```

with `main` as the agent container and services such as MySQL, APIs, or websites as sidecars.

Do not invent custom Harbor conventions. Verify against the installed Harbor version.

## Reset and isolation

Environment reuse must not imply shared mutable task state.

Each execution must begin from the validated initial state.

For stateful tasks such as DML:

```text
shared immutable runtime/assets
            +
fresh isolated task state per episode
```

Validate reset by modifying state, resetting/restarting, and confirming restoration.

## Verification

Use source trajectories as oracle/reference evidence, not as the only accepted solution.

Prefer outcome-based verification:

* SELECT: compare submitted result with validated expected result;
* DML: compare canonicalized final database state with validated expected state.

Where trusted state lives in a sidecar, use Harbor's current sidecar/artifact mechanisms where appropriate rather than trusting evidence written by the agent.

Require where applicable:

* oracle success;
* no-op failure;
* plausible incorrect-attempt failure;
* verifier failures to fail closed.

## Real-agent validation

After a pilot task passes deterministic Harbor checks, run at least one full end-to-end trial with a real agent/model through Harbor.

Use a configured provider/model available through the repository `.env`, while respecting the project LLM budget.

Conceptually:

```bash
harbor run \
  -p <task-path> \
  -a terminus-2 \
  -m <configured-model>
```

Before running, inspect `harbor run --help` and the relevant agent documentation for the installed Harbor version.

The purpose of this test is not to require the model to solve every task. It is to verify that:

* Harbor can launch the task normally;
* the agent receives the instruction;
* the agent can interact with the intended environment/service;
* observations are returned correctly;
* the episode terminates normally;
* the verifier runs;
* a reward/result is produced;
* the run can be inspected through Harbor logs/viewer.

A model failure to solve a genuinely difficult task is not automatically a conversion failure. Infrastructure, interaction, or verifier failures are.

Use only a small number of real-agent runs during pipeline development to control cost.

## TaskTrove packaging

TaskTrove stores valid Harbor tasks as compressed task binaries. A TaskTrove task archive is **not a Docker image**.

Conceptually:

```text
TaskTrove row
    ↓
compressed Harbor task
    ↓
extract
    ↓
Harbor resolves/builds/pulls environment
    ↓
run task
```

Do not embed exported Docker image tarballs into each task.

Do not treat per-task gzip compression as cross-task deduplication. Repeated large assets across many task archives are still duplicated.

Prefer shared images/assets where this materially reduces duplication while preserving reproducibility and portability.

## Final validation

For pilot tasks require:

1. valid Harbor structure;
2. clean startup;
3. deterministic reset;
4. oracle success;
5. no-op failure;
6. incorrect-attempt failure;
7. trusted verifier behavior;
8. at least one representative real-agent Harbor run;
9. TaskTrove pack;
10. fresh extraction;
11. Harbor revalidation after extraction.

Do not rely on undeclared files that happen to exist on the development machine.

Track enough storage information to detect obvious duplication, including number of distinct runtime images/environments and sizes of major shared assets.

During development, local images and caches are allowed. Do not push images, tasks, datasets, or branches unless explicitly authorized.
