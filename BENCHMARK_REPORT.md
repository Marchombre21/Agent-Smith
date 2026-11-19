# Model Benchmark Report

Status: sections 1 to 4, 6 and 7 come from the final multi-model run
(2026-11-17). Section 5 was measured twice (2026-11-12 and 2026-11-18); the table reports the second one, with the final agent.

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

Ten distinct models from five providers (Mistral, Gemini, Cloudflare Workers
AI, Nvidia, OpenRouter), all on free tiers, with two keys per provider and
key rotation. `nemotron-3-ultra-550b-a55b` ran on two providers (Nvidia and
OpenRouter), which gives eleven runs of three tasks and ten distinct models.

| Provider | Models |
|---|---|
| Mistral | `codestral-latest`, `ministral-14b-latest`, `ministral-8b-latest` |
| Gemini | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite` |
| Cloudflare | `nemotron-3-120b-a12b`, `mistral-small-3.1-24b-instruct` |
| Nvidia | `nemotron-3-ultra-550b-a55b`, `laguna-xs-2.1`, `nemotron-3.5-bolt-e4b` |
| OpenRouter | `nemotron-3-ultra-550b-a55b:free` (same model as on Nvidia) |

Runs kept out of the results, and why:

- A first launch was stopped after five minutes. A check on `django-11066`
  showed that the prompt line reading the `run_tests` output hid the test
  result for `unittest` repositories. The prompt was fixed, tested on two
  tasks, and the whole run restarted. Nothing from the first launch is used.
- **Network access.** Until 2026-11-18 the task container could reach the
  network. A review of the steps found two models that used it, only to
  install packages with `pip`: `nemotron-3-ultra` (Nvidia) and
  `mistral-small-3.1` (Cloudflare). No model looked for a solution online:
  the steps of the other nine models contain no `pip install`, `curl`, `wget`,
  `git clone` or request to a URL. The container now starts with
  `--network none`, and a test with `codestral-latest` confirmed that the
  evaluation scripts still run without network.
  `nemotron-3-ultra` was run again without network. The new runs replace the
  old ones in sections 2 to 4 and in `benchmark/`: the first set solved 2 of 3
  tasks, the second solves 1 of 3 (it still tries `pip install numpy` on
  `scikit-learn-13439`, which fails). `mistral-small-3.1` could not be run
  again, because its Cloudflare quota was used up. Its three runs are kept,
  and on `django-11066` the model ran `pip install pytz` and
  `pip install sqlparse`.
- `llama-4-scout-17b-16e-instruct` and `glm-4.7-flash` (Cloudflare): every
  call returned HTTP 429, "daily free allocation of 10,000 neurons". The
  other Cloudflare models had used the quota earlier in the run. The runs
  have 1 iteration and 0 tokens, so they say nothing about the models, and
  they are not counted. A retry the next morning got the same error.
- `gemini-3.5-flash-lite` on `scikit-learn-13439`: the first run got six
  empty answers in a row from the server (`finish_reason: stop`, 0 tokens).
  It was run again, and the second run is the one reported.

Models tried and not kept, with the reason (measured):

| Model | Provider | Reason |
|---|---|---|
| `gpt-oss-20b` | Groq | 0 code blocks in 40 calls (native tool call refused, or reasoning with no text) |
| any model | Groq | 8,000 tokens per minute per key: too low for SWE-bench |
| `qwen2.5-coder-32b`, `llama-3.3-70b` | Cloudflare | context window of 32k and 24k tokens |
| `qwen3.8-27b`, `gemma-4-26b` | Cloudflare | long outputs (922 and 637 tokens for one step) and 15 to 26 s per call |
| `gpt-oss-120b` | Cloudflare | several code blocks per answer and an invented observation, so the stop sequence never fires |

## 2. Results per model and task

A task is solved when the official validation says `PASSED`. The number in
brackets is the iteration count (the limit is 30). Totals are over the three
tasks. Time is wall-clock time. Models are sorted by tasks solved, then by
input tokens.

| Model | Provider | django-11066 | scikit-learn-13439 | xarray-4629 | Solved | Input tokens | Output tokens | Time (s) |
|---|---|---|---|---|---|---|---|---|
| `ministral-8b-latest` | Mistral | PASS (8) | PASS (9) | PASS (5) | **3/3** | 98,800 | 2,198 | 301 |
| `codestral-latest` | Mistral | PASS (7) | PASS (4) | PASS (30) | **3/3** | 205,284 | 2,108 | 575 |
| `nemotron-3.5-bolt-e4b` | Nvidia | PASS (5) | FAIL (19) | PASS (4) | **2/3** | 140,869 | 3,056 | 121 |
| `ministral-14b-latest` | Mistral | PASS (5) | FAIL (21) | PASS (5) | **2/3** | 163,628 | 10,840 | 489 |
| `gemini-3.5-flash-lite` | Gemini | PASS (18) | FAIL (30) | PASS (12) | **2/3** | 318,073 | 3,233 | 373 |
| `laguna-xs-2.1` | Nvidia | PASS (16) | FAIL (30) | PASS (17) | **2/3** | 331,474 | 4,487 | 245 |
| `nemotron-3-ultra-550b-a55b` | Nvidia | PASS (9) | FAIL (30) | FAIL (30) | **1/3** | 366,110 | 5,261 | 341 |
| `mistral-small-3.1-24b` | Cloudflare | FAIL (30) | PASS (12) | FAIL (30) | **1/3** | 478,511 | 11,053 | 346 |
| `gemini-3.1-flash-lite` | Gemini | FAIL (3) | FAIL (12) | FAIL (4) | **0/3** | 91,292 | 5,369 | 329 |
| `nemotron-3-ultra-550b-a55b:free` | OpenRouter | FAIL (30) | FAIL (30) | FAIL (30) | **0/3** | 418,370 | 4,839 | 266 |
| `nemotron-3-120b-a12b` | Cloudflare | FAIL (30) | FAIL (30) | FAIL (30) | **0/3** | 495,109 | 23,616 | 527 |

### Every run

One line per model and task, with the five measures of the subject: result,
iterations, input tokens, output tokens and wall-clock time. The same data is
in `benchmark/results.tsv`.

| Model | Task | Result | Iterations | Input tokens | Output tokens | Time (s) |
|---|---|---|---|---|---|---|
| `ministral-8b-latest` | django-11066 | PASS | 8 | 33,927 | 728 | 92 |
| `ministral-8b-latest` | scikit-learn-13439 | PASS | 9 | 44,288 | 1,093 | 137 |
| `ministral-8b-latest` | xarray-4629 | PASS | 5 | 20,585 | 377 | 72 |
| `codestral-latest` | django-11066 | PASS | 7 | 27,583 | 373 | 86 |
| `codestral-latest` | scikit-learn-13439 | PASS | 4 | 14,375 | 273 | 25 |
| `codestral-latest` | xarray-4629 | PASS | 30 | 163,326 | 1,462 | 464 |
| `nemotron-3.5-bolt-e4b` | django-11066 | PASS | 5 | 21,032 | 362 | 28 |
| `nemotron-3.5-bolt-e4b` | scikit-learn-13439 | FAIL | 19 | 102,370 | 2,320 | 64 |
| `nemotron-3.5-bolt-e4b` | xarray-4629 | PASS | 4 | 17,467 | 374 | 29 |
| `ministral-14b-latest` | django-11066 | PASS | 5 | 20,160 | 398 | 73 |
| `ministral-14b-latest` | scikit-learn-13439 | FAIL | 21 | 122,762 | 10,000 | 344 |
| `ministral-14b-latest` | xarray-4629 | PASS | 5 | 20,706 | 442 | 72 |
| `gemini-3.5-flash-lite` | django-11066 | PASS | 18 | 101,854 | 916 | 125 |
| `gemini-3.5-flash-lite` | scikit-learn-13439 | FAIL | 30 | 156,182 | 1,866 | 143 |
| `gemini-3.5-flash-lite` | xarray-4629 | PASS | 12 | 60,037 | 451 | 105 |
| `laguna-xs-2.1` | django-11066 | PASS | 16 | 75,840 | 888 | 66 |
| `laguna-xs-2.1` | scikit-learn-13439 | FAIL | 30 | 168,729 | 2,170 | 111 |
| `laguna-xs-2.1` | xarray-4629 | PASS | 17 | 86,905 | 1,429 | 68 |
| `nemotron-3-ultra-550b-a55b` | django-11066 | PASS | 9 | 45,487 | 1,014 | 95 |
| `nemotron-3-ultra-550b-a55b` | scikit-learn-13439 | FAIL | 30 | 192,594 | 3,162 | 164 |
| `nemotron-3-ultra-550b-a55b` | xarray-4629 | FAIL | 30 | 128,029 | 1,085 | 82 |
| `mistral-small-3.1-24b` | django-11066 | FAIL | 30 | 288,488 | 9,321 | 243 |
| `mistral-small-3.1-24b` | scikit-learn-13439 | PASS | 12 | 45,970 | 489 | 41 |
| `mistral-small-3.1-24b` | xarray-4629 | FAIL | 30 | 144,053 | 1,243 | 62 |
| `gemini-3.1-flash-lite` | django-11066 | FAIL | 3 | 14,253 | 1,766 | 26 |
| `gemini-3.1-flash-lite` | scikit-learn-13439 | FAIL | 12 | 57,659 | 2,010 | 117 |
| `gemini-3.1-flash-lite` | xarray-4629 | FAIL | 4 | 19,380 | 1,593 | 186 |
| `nemotron-3-ultra-550b-a55b:free` | django-11066 | FAIL | 30 | 128,209 | 1,310 | 75 |
| `nemotron-3-ultra-550b-a55b:free` | scikit-learn-13439 | FAIL | 30 | 157,681 | 2,289 | 102 |
| `nemotron-3-ultra-550b-a55b:free` | xarray-4629 | FAIL | 30 | 132,480 | 1,240 | 89 |
| `nemotron-3-120b-a12b` | django-11066 | FAIL | 30 | 133,936 | 4,576 | 84 |
| `nemotron-3-120b-a12b` | scikit-learn-13439 | FAIL | 30 | 176,210 | 9,951 | 153 |
| `nemotron-3-120b-a12b` | xarray-4629 | FAIL | 30 | 184,963 | 9,089 | 290 |

### What the numbers show

- **Two models solve all three tasks**, both from Mistral. `ministral-8b`
  does it with half the input tokens (98,800 against 205,284) and half the
  time (301 s against 575 s). `codestral` needed all 30 iterations on
  `xarray-4629`, so that pass was one step from the limit.
- **Four models solve two tasks**, and every one of them fails
  `scikit-learn-13439`. Two of the four (`gemini-3.5` and `laguna`) reach the
  30-iteration limit there.
- **The same model gives different results on two providers.**
  `nemotron-3-ultra-550b-a55b` solves 1/3 on Nvidia and 0/3 on OpenRouter.
  On `django-11066` the OpenRouter run calls `search_code(...)` and
  `list_files(...)` without `print(...)` and reads "printed nothing" until the
  limit. The same habit ends the Cloudflare `nemotron-3-120b` run on the same
  task.
- **Loops are the main way to fail.** Of the 33 runs, 16 pass and 17 fail.
  Twelve of the 17 failures end at the 30-iteration limit. `mistral-small-3.1`
  used 288,488 input tokens on `django-11066` and 144,053 on `xarray-4629`
  before reaching it.
- **The five other failures stop before the limit.** `gemini-3.1-flash-lite`
  stops after 3, 4 and 12 iterations. `nemotron-3.5-bolt` submits a wrong
  patch at iteration 19 on `scikit-learn-13439`. `ministral-14b` reaches the
  output limit (10,000 tokens) on the same task.

## 3. Provider reliability

Every one of the 33 runs wrote its `solution.json`, so the agent never
crashed. The table counts requests to the LLM over the three tasks.
**Availability** is the number of runs in which every request got an answer
from the provider, with no `LLM failure` in the run.

| Model | Provider | Requests | Average s per request | Retries | Availability |
|---|---|---|---|---|---|
| `codestral-latest` | Mistral | 41 | 12.2 | 18 | 3/3 |
| `ministral-14b-latest` | Mistral | 31 | 13.9 | 13 | 3/3 |
| `ministral-8b-latest` | Mistral | 22 | 10.7 | 8 | 3/3 |
| `gemini-3.1-flash-lite` | Gemini | 19 | 15.8 | 1 | 3/3 |
| `gemini-3.5-flash-lite` | Gemini | 60 | 3.9 | 4 | 3/3 after a rerun (2/3 at the first launch) |
| `nemotron-3-120b-a12b` | Cloudflare | 90 | 4.6 | 1 | 3/3 |
| `mistral-small-3.1-24b` | Cloudflare | 72 | 4.1 | 3 | 3/3 |
| `llama-4-scout-17b-16e` | Cloudflare | 3 | 120.9 | 15 | **0/3** (HTTP 429, daily quota) |
| `glm-4.7-flash` | Cloudflare | 3 | 120.5 | 15 | **0/3** (HTTP 429, daily quota) |
| `nemotron-3-ultra-550b-a55b` | Nvidia | 69 | 2.5 | 0 | 3/3 |
| `laguna-xs-2.1` | Nvidia | 63 | 2.4 | 0 | 3/3 |
| `nemotron-3.5-bolt-e4b` | Nvidia | 28 | 1.6 | 0 | 3/3 |
| `nemotron-3-ultra-550b-a55b:free` | OpenRouter | 90 | 2.5 | 3 | 3/3 |

`llama-4-scout` and `glm-4.7-flash` are listed here because they measure the
provider, but they are not in section 2: no request got an answer, so they
say nothing about the models.

- **Speed.** Nvidia is the fastest (1.6 to 3.6 s per request, no retry).
  Mistral is the slowest of the working providers (10.7 to 13.9 s) and has
  the most retries (8 to 18), which the key rotation absorbed.
- **Cloudflare quota.** The free plan gives 10,000 neurons per day. Two
  models fit in the quota (`nemotron-3-120b` and `mistral-small-3.1`), and
  the next two (`llama-4-scout`, `glm-4.7-flash`) got HTTP 429 on every attempt, with both keys, 6 attempts per call. The
  agent reported the error in `solution.json` and exited cleanly.
- **Gemini.** One run got six empty answers in a row on `scikit-learn-13439`
  (section 1). `gemini-3.5-flash` answered HTTP 503 "high demand" on every
  try on 2026-11-17, and `3.7` and `3.8` timed out, so they were not used.
- **OpenRouter.** The free plan allows 100 requests per day on the account
  used, which is enough for one model and three tasks but not for more.

## 4. Intermediary metrics

Two metrics from the subject, measured on the steps of each `solution.json`.

### Exploration efficiency

The step at which the agent first reads or edits a file that appears in its
final patch. A step counts when the code it sent to the sandbox names the
file (its path or its name). A dash means the final patch is empty.

| Model | django-11066 | scikit-learn-13439 | xarray-4629 |
|---|---|---|---|
| `ministral-8b-latest` | 2 | 2 | 2 |
| `codestral-latest` | 2 | 2 | 2 |
| `nemotron-3.5-bolt-e4b` | 2 | 2 | 1 |
| `ministral-14b-latest` | 2 | - | 2 |
| `laguna-xs-2.1` | 2 | - | 3 |
| `nemotron-3-ultra-550b-a55b` | 2 | - | - |
| `gemini-3.5-flash-lite` | 1 | - | 1 |
| `mistral-small-3.1-24b` | - | 2 | - |
| `gemini-3.1-flash-lite` | - | - | - |
| `nemotron-3-120b-a12b` | - | - | - |
| `nemotron-3-ultra-550b-a55b:free` | - | - | - |

When a model ends with a patch, it reaches the right file at step 1 to 3. The
differences between models are not in finding the file. They are in what
happens after: the runs with no patch never fixed anything, and the
iterations go into the loops described in section 2.

### Submission discipline

The number of steps between the first `run_tests` call whose result shows
the tests passing and `final_answer` (0 is ideal). A result counts as
passing when it ends with `OK` (Django) or reports only passed tests (pytest,
sympy).

| Model | django-11066 | scikit-learn-13439 | xarray-4629 |
|---|---|---|---|
| `ministral-8b-latest` | 0 | 0 | 0 |
| `codestral-latest` | 0 | 0 | 0 |
| `nemotron-3.5-bolt-e4b` | 0 | never passed | 0 |
| `ministral-14b-latest` | 0 | no answer | 0 |
| `laguna-xs-2.1` | **3** | no answer | **2** |
| `nemotron-3-ultra-550b-a55b` | **3** | no answer | no answer |
| `gemini-3.5-flash-lite` | **no tests** | no answer | **no tests** |
| `mistral-small-3.1-24b` | no answer | 0 | no answer |
| `gemini-3.1-flash-lite` | **no tests** | **no tests** | **no tests** |
| `nemotron-3-120b-a12b` | no answer | no answer | no answer |
| `nemotron-3-ultra-550b-a55b:free` | no answer | no answer | no answer |

- **no tests**: the agent never called `run_tests`.
- **never passed**: it called `run_tests`, and the result never showed the
  tests passing.
- **no answer**: no `final_answer` before the end of the run (iteration limit,
  or output limit for `ministral-14b`).

Reading:

- 16 runs passed validation. 14 of them ran the tests, and 11 of those 14
  submitted at once after the tests passed.
- Three passing runs waited after the tests passed: `laguna` on
  `django-11066` (3 steps) and `xarray-4629` (2 steps), and `nemotron-3-ultra`
  on `django-11066` (3 steps). They kept testing or reading before they
  submitted.
- Two runs passed with **no tests**: `gemini-3.5` on `django-11066` and
  `xarray-4629`. The patch was right, but the agent had not checked it.
- `gemini-3.1-flash-lite` never ran the tests and submitted with an empty
  patch after 3, 12 and 4 steps. On `django-11066` and `xarray-4629` its
  code blocks were malformed (a `Thought:` line inside the fence), so the
  code did not run.
- `nemotron-3-120b` on `xarray-4629` saw the tests pass at step 7 and never
  submitted: it ran to the iteration limit.

## 5. Ablation study

Model: `codestral-latest`. Tasks: six SWE-bench Verified tasks (the three
of section 1, plus `sympy__sympy-13480`, `sympy__sympy-18189` and
`sympy__sympy-14711`), with `sympy__sympy-14711` run three times because it is unstable (8 runs per
condition). Only one thing changes per condition.

Each condition was measured twice. The first measurement is from 2026-11-12.
After it, two things changed in the agent: the prompt line that reads the
output of `run_tests`, and the tools, which now return a string instead of a
dictionary. All four conditions were then measured again on 2026-11-18 with
the final agent. The table reports the second measurement. The first one is
in the last column.

| Condition | Change | Pass (of 8) | `sympy-14711` (of 3) | Stable tasks (of 5) | Input tokens, 4 clean tasks | First measurement (pass of 8) |
|---|---|---|---|---|---|---|
| R | reference | 6 | 1 | 5 | 21,964 | 6 |
| A1 | remove `find_references` and `list_files` | 5 | 0 | 5 | 19,079 | 5 |
| A2 | `max_observation_chars` 6,000 to 12,000 | 5 | 1 | 4 | 22,113 | 5 |
| A3 | repeat detector off | 6 | 1 | 5 | 29,300 | 7 |

The four clean tasks are the ones that pass in every condition:
`sympy-13480`, `sympy-18189`, `scikit-learn-13439` and `xarray-4629`. The
input tokens are their mean per run.

How to read it:

- Each condition has eight runs, and each task ran once, so a gap of one
  pass is not evidence. The two measurements of the same condition give the
  same number of passes for R, A1 and A2, and differ by one for A3 (7, then
  6). That gap is the noise of this setup.
- The input tokens move in both directions between the two measurements.
  Against R, A3 used 11% fewer tokens the first time (19,321 against 21,641)
  and 33% more the second time (29,300 against 21,964). A2 went from 17%
  fewer to 1% more. A change that flips sign from one measurement to the
  next is noise.
- A2 loses one stable task each time, and it is a different one: the first
  time `scikit-learn-13439`, because the model wrote 10,000 output tokens in
  one answer, the second time `django-11066`, because the model sent the same
  `search_code` call 27 times with a malformed code fence. Neither failure
  comes from the observation limit.
- The repeat detector stays silent on the stable tasks that pass. It fires
  27 times in the one stable run that loops (`django-11066` in A2). On
  `sympy-14711` it fires 1 to 27 times per run, and the four runs where it
  fires 19 times or more all end at 30 iterations: the model ignores the
  warning. With the detector off (A3), `sympy-14711` passes once in three,
  like R.

The data shows three things: removing two tools costs nothing measurable,
raising the observation limit gains nothing, and the repeat detector warns
but does not stop a loop. It does not show that any of the three changes
improves the pass rate.

## 6. Conclusions

### What differs between models

- **The pass rate separates the models less than the way they fail.**
  Twelve of the 17 failed runs end at the 30-iteration limit. A model that
  repeats the same call 28 times is not helped by the repeat warning: the
  detector warns, the model ignores it (`mistral-small-3.1` on
  `xarray-4629`, 26 warnings ignored, in an earlier test; `gemini-3.5` on
  `scikit-learn-13439`, "Same code and same result as step 15" at step 29).
- **Provider and model are not the same variable.** `nemotron-3-ultra`
  scores 1/3 on Nvidia and 0/3 on OpenRouter, so a ranking of models also
  ranks the way each provider serves them.
- **Small models do well on this setup.** The best result per input token
  comes from `ministral-8b` (3/3 for 98,800 tokens), and `nemotron-3.5-bolt`
  solves two tasks in 121 s, the shortest time of all.
- **Two passes were not verified by the agent.** Models that submit
  without running the tests succeed only when the first patch is right.

### Models to disregard

- `nemotron-3-120b-a12b` (Cloudflare): 0/3, every run at the 30-iteration
  limit, 495,109 input tokens and 23,616 output tokens, the highest of all
  models. On `xarray-4629` it saw the tests pass at step 7 and still did not
  submit.
- `nemotron-3-ultra-550b-a55b:free` (OpenRouter): 0/3, three runs at the
  limit. The same model solves one task on Nvidia, so the two providers do not
  give the same results with it.
- `gemini-3.1-flash-lite`: 0/3. It submits after 3 to 12 iterations with an
  empty patch and never calls `run_tests`.
- `mistral-small-3.1-24b` (Cloudflare): 1/3, and the most expensive of the
  working models (478,511 input tokens), because two of its runs loop.

### Selected model

`codestral-latest` stays the default model of the SWE-bench agent. It solves
3/3 and it is the model on which the ablations were run, so the ablation
results apply to it. `ministral-8b-latest` solves 3/3 as well, at half the cost, and
is the better choice if tokens or time matter more than consistency with the
ablations. Three tasks per model do not separate two models that both solve
all of them.

### Limits of this benchmark

- Three tasks per model: one task more or less moves a model by 33 points.
- One run per model and task. The noise measured in section 5 is 15 to 20%.
- The three tasks were chosen because the reference model passes them, so
  the benchmark has no task that nobody solves.

## 7. Raw data

The `solution.json` files behind sections 2 to 5 are in `benchmark/`:

```
benchmark/<model>/<task>/solution.json                  sections 2 to 4
benchmark/results.tsv                                   one line per run
benchmark/ablations/<condition>/<date>/<task>/solution.json   section 5
```

`results.tsv` has one line per run: model, task, verdict, iterations, input
tokens, output tokens, seconds, error.

In `benchmark/ablations/`, each condition has eight runs per date: the six
tasks, and `sympy__sympy-14711` two more times
(`sympy__sympy-14711-run1` to `-run3`). Dates are `2026-11-12` for the first
measurement and `2026-11-18` for the second, both with the four conditions.
