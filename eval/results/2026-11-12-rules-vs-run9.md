# Hand-written rules vs run 9, same test set (2026-11-12)

**The question (Roberto, after trying run 9 on vm1):** if we end up deciding the cases
ourselves, does a model make sense at all? So: how far do keywords plus checks on the
diagnostics go, with no model?

**How:** `eval/rules_baseline.py`, plugged into `run_eval.py --rules` (same prompts in, same
JSON out). Written in about half a day, in three rounds, looking **only at the training
split** (Debian): step 1 = keyword scores per category, step 2 = checks on the probe output
(the facts a playbook precondition reads) and, for everyday actions, verbs and object words
with numbers read by regex. Then run on `data/dataset-run9/test.jsonl` (Ubuntu, held out).

One fix after the first test run, declared: on Ubuntu `browser_default` still reads
`firefox-esr.desktop` while the installed browser is `firefox`, so every site and search got
the wrong browser name. The rule now takes the installed one. First run: step 2 exact 89.4%,
actions 49.3% (`data/eval-rules-on-run9-firstrun-report.json`); everything else unchanged.

| | rules | **run 9** | qwen3:14b (for reference) |
|---|---|---|---|
| step 1: right category (663) | 79.3% | **95.8%** | 38.3% |
| … Italian / English | 76.5 / 82.6% | **95.2 / 96.5%** | 34.6 / 42.6% |
| step 2: right fix (2,411) | 92.7% | **96.8%** | 30.3% |
| step 2: exact fix + params | 92.0% | **95.4%** | 27.5% |
| **real repairs, exact (1,394)** | **96.3%** | **97.2%** | 32.6% |
| everyday actions, exact (337) | 68.0% | **87.5%** | 15.1% |
| escalation when the disk is failing | 100% | 100% | 24% |
| healthy PC: a fix that changes something (784) | 9 (1.1%, all `apt.wait_for_lock`) | 9 (1.1%, same) | 258 |

Step 2 is scored with the right category given, for every backend. In use a step-1 miss
sends step 2 to the wrong category, so end to end the gap is wider: roughly 0.79 × 0.92 ≈ 73%
for the rules against 0.96 × 0.95 ≈ 91% for run 9 (a rough product, not measured).

## Reading

- **Choosing the repair from the diagnostics does not need a model.** 96.3% against 97.2%,
  same escalations, same 9 healthy-PC slips. Once the category is known, the probes say what
  is broken, and the rules are short (one function per category, ~15 lines each).
- **Understanding the person is where the model earns its place.** Step 1: 79% vs 96%, and the
  rules are weakest exactly where it matters, Italian and dialect (76.5%) and vague
  complaints ("premo il pulsante ma niente", "schermo rosso e non so come risolvere").
  Updates is the worst category for rules (54%): people describe the symptom, never apt.
- **Everyday actions: 68% vs 87.5%.** Rules miss requests without a command verb ("mi serve
  il programma che mostra i problemi", "can you start the account sheet") and cannot rewrite
  a search query the way a person meant it (web.search 43% exact).
- **Where rules are better:** numbers. The reminder minutes come from a regex, so "tra 1
  minuto" is 1, never 15 (the run 9 slip on vm1 today).

## What it suggests (not done, needs Roberto)

A split: **the model reads the person** (step 1, everyday actions, out-of-catalog requests),
**rules read the machine** (step 2 for the repair categories) and numbers come from code.
- Same accuracy on repairs (−0.9 points), but a new fault becomes one rule plus a playbook,
  not a new collection and a new training run.
- **No second model call on repairs**: the step-2 prompt is the long one (p50 ~1,000
  characters of diagnostics), so on the target CPU this removes most of the waiting on the
  fault cases (estimate, not measured on the 2009 PC).
- Risk: rules are brittle to probe output the lab never produced (another distro, another
  language of the tools). The model was not tested on that either.
