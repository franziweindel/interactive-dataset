# Interactive Dataset Integration

You are the lead engineer responsible for building a reusable Repo2RLEnv pipeline that converts existing interactive-agent datasets into reproducible, resettable, verifiable Harbor tasks that can be packed into TaskTrove.

Work directly in a fork or feature branch of Repo2RLEnv and reuse its existing infrastructure where practical. Inspect code and datasets, implement changes, run environments and tests, diagnose failures, and iteratively improve the pipeline. Do not stop at architectural proposals.

## Objective

Implement an experimental Repo2RLEnv pipeline named `interactive_dataset`.

Development targets are:

* `agenttuning-db`
* `agenttuning-os`
* `agenttuning-kg`
* `agenttuning-alfworld`
* `agenttuning-webshop`
* `agenttuning-mind2web`
* `go-browse-wa`
* `synatra`
* `nnetnav-live`

The goal is **not** to manually convert these datasets one by one.

The goal is to design, implement, and validate a reusable pipeline that can automatically:

* analyze and onboard a source;
* construct or load a source adapter;
* recover executable tasks from source data and upstream resources;
* validate, diagnose, repair, or reject problematic tasks;
* construct reusable runtime environments;
* emit and verify Harbor tasks;
* pack them into TaskTrove;
* and generalize to unseen tasks with minimal manual intervention.

Dataset-specific knowledge should live in adapters or configuration. Generic source analysis, acquisition, validation, diagnosis, repair, runtime construction, Harbor emission, verification, packing, caching, and reporting should remain reusable.

Expensive source-level LLM analysis should happen once per source or task family where possible and be distilled into reusable adapter or pipeline logic rather than repeated independently for every row.

Begin with `agenttuning-db`. Do not proceed to another source until its adapter passes `EVALUATION.md`.

Do not convert full datasets during pipeline development. Run cheap source-wide mapping and validation where useful, but use small pilots for expensive conversion stages. Full-scale conversion will be run separately by the user.

### Trajectory-based sources

A source may consist primarily of successful SFT or interaction trajectories rather than packaged executable tasks. This is not by itself a reason to reject it.

The pipeline may use released trajectories as evidence to recover:

* task instruction;
* upstream task or asset;
* interaction protocol;
* reference solution;
* expected outcome;
* task-defining state.

Trajectory evidence may be combined with upstream datasets, repositories, generation artifacts, papers, documentation, and other released resources.

Recovery is allowed when the reconstructed information is supported by source evidence and can be validated.

Do not invent missing task-defining state, expected outcomes, or verifier semantics merely because they are absent from the released trajectory.

## Project organization

Use these project documents:

* `QUICKSTART.md` — minimal user-facing instructions for running `interactive_dataset`.
* `STARTING_PIPELINE.md` — current algorithm implemented by `interactive_dataset`.
* `EVALUATION.md` — experiments and acceptance criteria for source onboarding, recovery, repair, conversion, and generalization.
* `SOURCES.md` — target datasets, upstream resources, and useful reference projects.
* `HARBOR_TASKTROVE.md` — Harbor construction, environment reuse, isolation, verification, real-agent validation, and TaskTrove packaging requirements.
* `findings/<source>.md` — evolving source-specific empirical findings.
* `reports/` — generated run-specific and machine-readable evidence.

Create `findings/` and `reports/` if absent.

Maintain one findings file per source when work begins:

```text
findings/
├── agenttuning-db.md
├── agenttuning-os.md
├── agenttuning-kg.md
├── agenttuning-alfworld.md
├── agenttuning-webshop.md
├── agenttuning-mind2web.md
├── go-browse-wa.md
├── synatra.md
└── nnetnav-live.md
```

Before implementing or substantially modifying Harbor task emission, read `HARBOR_TASKTROVE.md` and the current Harbor and TaskTrove documentation referenced there.

### QUICKSTART requirements

Create and maintain `QUICKSTART.md` as the simplest accurate entry point for a new user.

Keep it intentionally very short and easy to scan.

It should contain only:

* a one-line description of the pipeline;
* a very brief high-level pipeline flow;
* the primary command for running it;
* 2–3 representative source examples;
* where outputs/reports are written.

Prefer one obvious source-oriented entry point, conceptually:

```bash
<command> --source agenttuning-db

<command> \
  --source https://huggingface.co/datasets/THUDM/AgentInstruct \
  --subset db

<command> \
  --source https://github.com/example/project
```

The pipeline should support a source abstraction broad enough for registered source names, Hugging Face datasets, GitHub repositories, supported public URLs, and local sources where practical.

These commands are illustrative. `QUICKSTART.md` must always document the **actual implemented Repo2RLEnv CLI**, not stale examples.

Do not duplicate architecture, evaluation rules, Harbor documentation, or source-specific findings in `QUICKSTART.md`.

Also for each dataset give a current estimate of how much it costs to convert into harbor format per task. 
## Living documentation

Treat the project documentation as part of the implementation, not as immutable initial instructions.

Update it when experiments establish a better design or disprove an existing assumption.

In particular:

* evolve `STARTING_PIPELINE.md` from the initial proposal into the pipeline architecture that works best empirically;
* keep `QUICKSTART.md` synchronized with the actual CLI and main workflow;
* improve `EVALUATION.md` when better tests or acceptance criteria are discovered;
* correct `SOURCES.md` when provenance or upstream assumptions are disproven;
* update `HARBOR_TASKTROVE.md` when current Harbor/TaskTrove behavior or better packaging strategies are established;
* update source findings as hypotheses are confirmed or rejected.

Do not preserve outdated documentation merely because it was provided initially.

When manual investigation reveals a useful recurring procedure, implement it in the generic pipeline or source adapter where practical and update the documentation accordingly.

Verify that the automated implementation reproduces the manually established results.

If the procedure involves LLM-based source analysis, construct and execute the corresponding prompt/agent workflow rather than leaving the knowledge only in manually written adapter logic.

Functional equivalence should be established by executing and validating the resulting pipeline/adapter behavior, not merely by asking another LLM whether two approaches look equivalent.

Generalization to unseen tasks and failures is tested separately according to `EVALUATION.md`.

Existing findings are evidence and a way to avoid duplicated work, not unquestionable truth. Reverify load-bearing claims before relying on them.

Do not weaken or remove the core objective, semantic-integrity rules, cost limit, or local-only restrictions below unless explicitly instructed by the user.

## Non-negotiable semantic rules

* Preserve original task semantics. Never change the instruction, ground truth, task-defining initial state, accepted outcomes, evaluator semantics, or grading thresholds merely to make a task pass.
* Prefer the original released runtime, assets, initialization, interaction semantics, and evaluator when they can be recovered.
* Do not invent replacement runtimes, task state, or verifiers merely to force a source into Harbor. If faithful conversion is not defensible, classify the task or source as unresolved or blocked.
* Any successful repair that changes upstream-derived artifacts requires deterministic integrity checks and a complete diff audit. Semantic, verifier-weakening, or uncertain changes are rejected.
* Use demonstrated trajectories as reference solutions/oracles, not as required action sequences. Prefer verification of the intended final outcome or state so that alternative valid solutions can pass.
* Fail closed: unresolved mappings, unavailable services/assets, failed initialization, verifier errors, malformed results, missing state, timeouts, or semantic uncertainty must not count as success.
* Do not accumulate hidden task-ID-specific fixes merely to make pilot examples pass.

## Cost-aware development

Prefer deterministic inspection, diagnosis, and repair before LLM calls.

Reuse source-level analysis, adapters, shared runtimes/assets, and cached work. Do not repeatedly invoke an LLM for information already established by validated adapter or pipeline logic.

LLM-assisted source onboarding, diagnosis, construction, repair, and semantic review are allowed when useful.

Model credentials are provided through the repository-root `.env`:

```env
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
```

Currently intended options include configured OpenAI models and DeepSeek V4 Flash.

Never print, log, commit, embed in generated artifacts, or otherwise expose credentials.

Track LLM cost throughout development.

Combined LLM spend must remain below **USD 20**.

Spend this budget on validating and improving the reusable pipeline, not on bulk conversion.

## Working behavior

For each source:

1. onboard or validate the source adapter;
2. run source/upstream recovery and validation;
3. diagnose failures and evaluate whether repair is useful;
4. establish the usable subset;
5. freeze a small representative regression pilot;
6. make the complete pipeline pass the pilot;
7. test the unchanged pipeline/adapter on unseen tasks and relevant failure cases;
8. stop once the adapter passes `EVALUATION.md`.

Manual investigation is allowed while developing a source, but recurring useful behavior should be converted into reusable pipeline or adapter logic and retested automatically.

Proceed to the next source only after the current adapter is validated.

After meaningful generic changes, run the smallest relevant test first and then rerun the affected regression pilot.

Prefer:

1. generic pipeline fixes;
2. source-adapter logic;
3. only when unavoidable, narrowly scoped source-specific handling.

Do not use task-ID-specific fixes to make examples pass.

## Local-only operation

Downloading and inspecting public inputs is allowed.

Do not upload generated datasets, publish Harbor tasks, push branches, push container images, create remote repositories, or modify upstream projects remotely unless explicitly authorized by the user.

All generated outputs remain local.

## Success criterion

A successful project outcome is not a large number of generated task directories.

It is a reusable, evaluated pipeline that can:

* expose a simple source-oriented CLI for normal use;
* onboard and understand a source with limited repeated manual or LLM effort;
* recover executable tasks from datasets including trajectory-only sources;
* determine which source tasks are valid;
* safely recover, repair, reject, or block problematic tasks;
* reproduce their intended interactive runtime;
* reuse environments and heavy assets efficiently;
* convert validated tasks into Harbor;
* preserve upstream semantics and verifier integrity;
* execute representative real-agent Harbor runs;
* survive TaskTrove packing and fresh extraction;
* generalize beyond the examples used to construct the adapter;
* and do so with reasonable manual effort and LLM cost per accepted task.
