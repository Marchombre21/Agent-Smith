# Model Benchmark Report

Status: draft. Sections 1, 5 and part of 6 come from measured runs.
Sections 2 to 4 will come from the final multi-model run.

## 1. Setup

### Agent

One agent, frozen for the whole benchmark: the same prompt, the same tools
and the same limits for every model (30 iterations, 300,000 input tokens,
10,000 output tokens, 900 s per task). Only `--model-name` and
`--provider-url` change between runs. Every run goes through the subject's
commands: `dump`, then `run-agent`, then `validate`.

### Tasks

Three SWE-bench Verified tasks, each from a different repository:

| Task | Repository | Reference run (codestral) |
|---|---|---|
| `django__django-11066` | django | PASS, 5 iterations |
| `scikit-learn__scikit-learn-13439` | scikit-learn | PASS, 12 iterations |
| `pydata__xarray-4629` | xarray | PASS, 6 iterations |

Why these three:

- They pass reliably with the reference model, so a failure says something
  about the model being tested, not about an unstable task.
- They come from three different codebases, so a model cannot succeed by
  knowing one library well.
- `sympy__sympy-13480` is left out: its hints give the fix
  ("`cotm` should be `cothm`"), so it does not separate models.
- `sympy__sympy-14711` is left out: it is unstable even for the reference
  model (1 pass in 3 runs). It is still used as the noise gauge in the
  ablation study (section 5).

### Models and providers

To be completed with the final list: 10 models from 5 providers (Mistral,
Gemini, Cloudflare Workers AI, Nvidia, OpenRouter), all on free tiers, with
two keys per provider and key rotation.

Models tried and not kept, with the reason (measured):

| Model | Provider | Reason |
|---|---|---|
| `gpt-oss-20b` | Groq | 0 code blocks in 40 calls (native tool call refused, or reasoning with no text) |
| any model | Groq | 8,000 tokens per minute per key: too low for SWE-bench |
| `qwen2.5-coder-32b`, `llama-3.3-70b` | Cloudflare | context window of 32k and 24k tokens |
| `qwen3.8-27b`, `gemma-4-26b` | Cloudflare | long outputs (922 and 637 tokens for one step) and 15 to 26 s per call |
| `gpt-oss-120b` | Cloudflare | several code blocks per answer and an invented observation, so the stop sequence never fires |
| `kimi-k2.6`, `glm-5.2`, `deepseek-v4-flash` | Cloudflare | HTTP 403, not available on the free plan |
| `mistral-large-4`, `mistral-medium`, `magistral` | Mistral | HTTP 403 (`tier_not_allowed`) or HTTP 429 on every call |
| `gemini-3.5-flash`, `3.7-flash`, `3.8-flash` | Gemini | timeouts at 60 s, then HTTP 503 "high demand" at 120 s |

## 2. Results per model and task

To be completed from `tableau.tsv` of the final run: pass or fail, iterations,
total input tokens, total output tokens, wall-clock time, for each model and
task.

## 3. Provider reliability

To be completed: per model and provider, the average response time per
request, the number of retries (rate limits, timeouts, errors) and the
availability (runs that produced a `solution.json`). One case already
observed: `gemini-3.5-flash` answered HTTP 503 "high demand" on every try
on 2026-11-17.

## 4. Intermediary metrics

To be completed from the `solution.json` files. Two metrics are planned:

- **Exploration efficiency**: the step at which the agent first calls
  `edit_file`.
- **Submission discipline**: the number of steps between the last
  `run_tests` call and `final_answer` (zero is ideal).

One case of missing discipline is already documented: with
`nemotron-3-ultra-550b-a55b` on `sympy__sympy-13480`, the model fixes the
bug at step 2 with an exact `edit_file`, then never submits. It calls
`run_command` without `print`, gets "printed nothing" four times, and ends
at the 30-iteration limit after installing a package in the container.

## 5. Ablation study

Model: `codestral-latest`. Tasks: the six tasks of the exam pool, with
`sympy__sympy-14711` run three times because it is unstable (8 runs per
condition). Only one thing changes per condition.

| Condition | Change | Pass (of 8) | `sympy-14711` (of 3) | Stable tasks (of 5) | Input tokens, 4 clean tasks |
|---|---|---|---|---|---|
| R | reference | 6 | 1 | 5 | 21,641 |
| A1 | remove `find_references` and `list_files` | 5 | 0 | 5 | 16,698 |
| A2 | `max_observation_chars` 6,000 to 12,000 | 5 | 1 | 4 | 17,878 |
| A3 | repeat detector off | 7 | 2 | 5 | 19,321 |

How to read it:

- Each condition has eight runs, and each task ran once, so a gap of one
  pass is not evidence. Two passes of the same agent differ by 15 to 20%
  in input tokens, so the 21% drop in A1 and the 17% drop in A2 are within
  noise.
- A2 lost one stable task (`scikit-learn-13439`) because the model wrote
  10,000 output tokens in one answer before seeing any observation. That is
  model variance, not an effect of the setting.
- The repeat detector never fires on the five stable tasks. On
  `sympy-14711` it fires 4 to 23 times per run, and the runs where it
  speaks 15 to 23 times still end at 30 iterations: the model ignores the
  warning.

The data shows three things: removing two tools costs nothing measurable,
raising the observation limit gains nothing, and the repeat detector warns
but does not stop a loop. It does not show that any of the three changes
improves the pass rate.

## 6. Conclusions

### Models to disregard (data so far)

- `mistral-small-3.1-24b` (Cloudflare): on `xarray-4629` it sent the same
  `search_code` call 28 times in a row (steps 3 to 30), ignored the repeat
  warning 26 times, and failed at the iteration limit with 142,643 input
  tokens and no patch. One run: to be confirmed on the three tasks.

### Selected model

To be completed from sections 2 to 4.

## 7. Raw data

The `solution.json` files behind sections 2 to 4 are in the repository, in
`benchmark/` (to be added after the final run).
