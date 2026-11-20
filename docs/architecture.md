# Architecture

## Design constraints

1. **Runs on the PC it repairs.** Floor: Core 2 Quad Q8300 (2008), no AVX,
   4 GB RAM, SATA SSD. Typical: Intel 6th–7th gen (excluded from Windows 11),
   AVX2, 4–8 GB.
2. **Prefill is the bottleneck.** Without AVX, reading the prompt costs far
   more than generating. Every design choice below shrinks the prompt or the
   output.
3. **No free-form actions.** The model selects; code acts.

## The two calls

| step | input | output | budget |
|---|---|---|---|
| 1 | complaint only | `{"category": ...}` | ~60 prompt tokens, ~5 out |
| 2 | complaint + filtered diagnostics | `{"fix_id", "params", "confidence"}` | ~300–600 prompt tokens, ~20 out |

Between the two, code runs the category's probe bundle. Probes run with
`LC_ALL=C.UTF-8` (stable English output whatever the desktop language),
are filtered with a per-probe regex, deduplicated and capped
(`DIAG_BUDGET`, default 1800 chars).

Constant system prompts let llama.cpp reuse the cached prefix. Note: for
hybrid/recurrent architectures (e.g. Qwen3.5's Gated DeltaNet layers) prefix
reuse is more limited than for pure attention models: measure, don't assume.

Decoding is constrained with a JSON Schema (`chirone schema`) that llama.cpp
compiles to a grammar: step 2's schema is an `anyOf` with one branch per fix
allowed in the category, each with its own param types (enums, integers with
bounds, anchored patterns). Invalid output is impossible by construction; the
same schema validates outputs in Python.

The schemas are checked against llama.cpp's own converter and grammar
matcher (`eval/grammar_check/`): every allowed fix is accepted, while
out-of-category fixes, option/shell injection in params and out-of-range
integers are rejected at decoding time.

## Catalog

`src/chirone/catalog/` is the single source of truth used by the agent, the
root helper, the lab and the dataset builder.

* **probes**: read-only commands, never through a shell.
* **playbooks**: the closed set of fixes. Steps, preconditions, verification,
  risk level, whether confirmation is needed, user messages (it/en).
* **categories**: what the person perceives, mapped to a probe bundle and the
  fixes reachable from it. Perception, not cause: a wrong clock shows up as
  "websites are broken", so `time.enable_ntp` is reachable from `network`.
* **faults**: lab injections with the correct fix declared up front.

`chirone validate` cross-checks everything (placeholders, regexes, probes
referenced, every fix reachable, every fault's expected fix allowed in its
category). The tests also require every playbook to be exercised by at least
one lab fault: a fix without verified data does not ship.

## Data pipeline

1. **Lab** (`lab/collect.py`): reset VM (disk-only snapshot, cold boot) →
   inject → check the fault is real → collect the bundle as the desktop user →
   capture expected params from probe output → apply the expected fix with
   chirone itself → keep only `verified` samples.
2. **Teacher** (`datagen/teacher.py`): an open-weights model behind any
   OpenAI-compatible API writes complaints from the *symptom* (never the
   cause), rotating personas. It writes language, never labels.
3. **Dataset** (`datagen/build_dataset.py`): joins the two with the exact
   prompt functions used at inference. Leak-free hash splits; optional
   held-out OS. Adds *healthy negatives* (real complaint + healthy machine →
   `noop`) so the model learns not to invent fixes.
4. **Train** (`train/sft.py`): completion-only SFT, full FT for 0.8B, LoRA
   above. Teacher distillation is sequence-level: APIs don't expose full
   logits. Logit distillation needs a same-tokenizer teacher run locally.
5. **Eval** (`eval/run_eval.py`): the same test set against the student on
   the target machine and against a large open model via API, so the
   proposal can state "the 0.8B reaches X% of the large model at Y seconds on
   a 2008 PC".

## Privilege model

The agent runs as the desktop user. Root-only probes and steps go through
`sudo -n /usr/local/libexec/chirone-root-helper`, the only sudoers entry.
The helper reloads the catalog from the root-owned install, refuses anything
not marked `root`, re-validates params and renders argv itself. See
[safety.md](safety.md).
