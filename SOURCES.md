# Sources and References

This is a navigation file, not a source of truth. Inspect current repositories/datasets directly and pin immutable revisions before relying on them.

Source-specific discoveries belong in `findings/<source>.md`.

## Target sources

Develop adapters in this initial order:

1. `agenttuning-db`
2. `agenttuning-os`
3. `agenttuning-kg`
4. `agenttuning-alfworld`
5. `agenttuning-webshop`
6. `agenttuning-mind2web`
7. `go-browse-wa`
8. `synatra`
9. `nnetnav-live`

Do not assume all are convertible. The source audit must determine whether a reproducible runtime, reset mechanism, interaction interface, and defensible verifier exist.

## AgentTuning

- Repository: `https://github.com/THUDM/AgentTuning`
- Paper: `https://arxiv.org/abs/2310.12823`

Candidate third-party representations such as DCAgent datasets may be useful for identifiers or packing examples, but are not automatically the semantic source of truth.

## AgentBench

- Repository: `https://github.com/THUDM/AgentBench`
- Paper: `https://arxiv.org/abs/2308.03688`

Expected upstream runtime for:

- `agenttuning-db`
- `agenttuning-os`
- `agenttuning-kg`

Verify exact mapping, initialization, interaction, reset, evaluator, and ground truth per source.

## ALFWorld

- Repository: `https://github.com/alfworld/alfworld`
- Project: `https://alfworld.github.io`
- Paper: `https://arxiv.org/abs/2010.03768`

Expected upstream runtime for `agenttuning-alfworld`.

## WebShop

- Repository: `https://github.com/princeton-nlp/WebShop`
- Project: `https://webshop-pnlp.github.io`
- Paper: `https://arxiv.org/abs/2207.01206`

Expected upstream runtime for `agenttuning-webshop`.

## Mind2Web

- Repository: `https://github.com/OSU-NLP-Group/Mind2Web`
- Project: `https://osu-nlp-group.github.io/Mind2Web/`
- Paper: `https://arxiv.org/abs/2306.06070`

May not provide a straightforward resettable live runtime. Determine this from evidence rather than synthesizing a replacement.

## Go-Browse-WA

Inspect the current Go-Browse release and its WebArena dependencies.

Determine whether task-specific WebArena state/reset and an outcome-level verifier can be recovered. A successful trajectory alone is not automatically a verifier.

## Synatra

Determine whether examples correspond to executable tasks or mainly static/snapshot trajectory supervision.

If a faithful resettable runtime cannot be recovered, classify it as unsupported rather than inventing one.

## NNetNav-Live

Determine whether live-site state, reset, assets, and an outcome-level success condition are reproducible.

Historical successful trajectories alone are insufficient for faithful Harbor conversion.

## Repo2RLEnv

- Repository: `https://github.com/huggingface/Repo2RLEnv`
- Docs: `https://huggingface.github.io/Repo2RLEnv/`

Use a fork/feature branch as the implementation host.

Inspect and reuse where practical:

- pipeline protocol/registry;
- options/configuration;
- bootstrap/environment helpers;
- model-provider plumbing;
- command execution;
- caching;
- cost accounting;
- Harbor emission;
- validation;
- provenance;
- Hugging Face integration.

## Harbor

- Repository: `https://github.com/laude-institute/harbor`
- Docs: `https://harborframework.com/docs/tasks`

Use the current Harbor specification and Harbor itself for task execution/validation.

## TaskTrove

- Dataset: `open-thoughts/TaskTrove`

Inspect the current schema and extraction workflow. Required development validation is a local pack → fresh extract → Harbor rerun.

## Useful design references

### OpenSWE
- Repository: `https://github.com/GAIR-NLP/OpenSWE`
- Useful for environment/repository inspection and iterative repair.

### TMAX
- Repository: `https://github.com/hamishivi/tmax`
- Useful for environment synthesis, state testing, verifier construction, and oracle validation.

### RepoLaunch
- Repository: `https://github.com/microsoft/RepoLaunch`
- Useful for dependency/build discovery.

Prefer reuse over reimplementation when licenses and interfaces permit.
