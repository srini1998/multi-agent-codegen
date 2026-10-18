# Local coding strategies, measured rather than assumed

Compare a single Coder, execution-feedback revisions, and Planner → Coder → Reviewer roles using local Ollama. All strategies solve the same HumanEval functions; only the final independent checker sees the hidden tests. This is a bounded function-generation experiment, not an unrestricted coding assistant.

## What the recorded example establishes

The frozen first-36-task cohort in `examples/cohort36/` was generated with local qwen2.5:3b and independently regraded in the fixed local container:

| Strategy | Final solutions passing hidden tests | Recorded model calls / task |
|---|---:|---:|
| Single coder | 30 / 36 | 1.00 |
| Execution feedback | 29 / 36 | 1.33 |
| Planner / coder / reviewer | 25 / 36 | 6.72 |

More roles did not automatically improve this cohort. The full-role versus single-coder difference has a paired bootstrap interval that includes zero; this small, ordered sample is not evidence about all coding tasks. Strategies receive different numbers of model calls, shown explicitly. The legacy report field `pass_at_1` means final-solution solve rate here: revision strategies can make up to two revisions, so it is not a one-shot sampling estimate for those strategies.

These are saved generation outputs, not a fresh agent run. The original generation durations/token usage remain historical; regrading did not call a model. The complete HumanEval corpus has 164 tasks, but the frozen comparison deliberately contains 36. Separate ongoing/completed local generation logs must not be confused with that fixed cohort. Model pretraining exposure to HumanEval is unknown.

## Actual execution and evaluator boundaries

Generated Python runs in a fixed local container, with **no host directory or Docker socket mounted**, networking disabled, a read-only root, a bounded writable temporary filesystem, an unprivileged user, CPU/memory/PID/output/time limits, and no extra capabilities. Missing container infrastructure fails closed; code never falls back to executing on the host. Only the reviewed executor controls Docker flags. The model supplies Python source, not container configuration or shell commands.

Image: `python@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c` (Python 3.12.12). Current support: a local Colima `breakroom` socket on macOS or `/var/run/docker.sock` on Linux. The image must be present locally; experiments use `--pull=never`. Colima, Docker Engine and this image do not require a cloud service.

The checker uses a separate namespace for its trusted helpers. A negative control that replaced the checker's `poly` helper with `return 0` used to pass; it now fails. This is not a claim of immunity to every adversarial Python program or container escape. HumanEval evaluation assumes ordinary benchmark implementations rather than a malicious model attacking the checker.

## What review found

- The previous macOS `allow default` sandbox blocked writes/networking but allowed reading host files. An authored non-secret outside-run canary demonstrated this. Actual container tests now reject that read.
- A bounded-output test exposed a cleanup deadlock; cleanup now closes the output pipe and terminates the owned container/client.
- A checker helper could be overwritten by candidate code. The separate checker namespace rejects the authored incorrect candidate.
- One saved `find_zero` result differs consistently between native macOS Python 3.12.10 and pinned Linux Python 3.12.12 (three replays each). Both observations are preserved in `docs/runtime-difference.json`. This is runtime-sensitive numerical behavior, not a newly claimed model improvement.

`docs/container-rescore.json` records the broader saved-output replay snapshot and the one changed result. Original run files were not rewritten. The frozen example files retain `original_hidden` alongside their current container grading.

## Run locally, with free tools

```sh
# Start the supported local Docker Engine / Colima profile first.
docker --host unix://$HOME/.colima/breakroom/docker.sock pull python@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c
uv sync
uv run pytest
uv run mac compare --runs-dir examples/cohort36 --report docs/cohort36-comparison.json
uv run mac rescore --runs-dir examples/cohort36

# Fresh generation needs the existing local Ollama provider, not a paid API.
ollama pull qwen2.5:3b
uv run mac run single --limit 36
uv run mac run exec-feedback --limit 36
uv run mac run full --limit 36 --max-revisions 2
```

On Linux, pull the image using the same local `/var/run/docker.sock` engine that the executor will use. No cloud credentials, automatic merge, deployment or paid inference is used.

## Provenance

HumanEval is by OpenAI under MIT; the pinned full dataset checksum is validated before use. The required licence is included at `data/HUMANEVAL-LICENSE.txt`. Model role prompts are public in `mac/agents.py`; tool/evaluator outputs and model usage are saved. There is no custom model training.
