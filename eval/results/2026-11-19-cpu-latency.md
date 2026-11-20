# Latency on a CPU without AVX — 2026-11-19

**What this is:** the shipped model (run 10, `run-20261115103204`, Q8_0) served the way
`deploy/chirone-llm.service` serves it (`--ctx-size 2048 --parallel 1 --jinja`, 4 threads),
by the no-AVX llama.cpp build (`build-noavx`, the instruction set of a Core 2 Quad) on the
devbox (i5-4590). 200 rows of the held-out test set, a fixed sample (`run_eval.py --sample 200`,
seed 0): 40 step-1 and 160 step-2 requests, in random order, one at a time.
Raw reports: `2026-11-19-cpu-latency/`.

**This is a proxy, not the target PC.** On 2026-11-09 a real Core 2 Quad Q8300 (a family PC) ran the
same no-AVX binaries **~2.8× slower** than the devbox (`2026-11-09-real-pc-bench.md`). The last
column below applies that factor: it is an estimate, not a measurement.

## Run 10, short diagnostics

| | p50 | p95 | Core 2 estimate (p50 ×2.8) |
|---|---:|---:|---:|
| Step 1 (which category) | **1.3 s** | 2.2 s | ~3.5 s |
| Step 2 (fix or action + parameters) | **9.9 s** | 20.8 s | ~28 s |

Step 2 is ~75% prefill (llama.cpp p50: prompt 7.4 s, generation 1.5 s). 0 invalid answers;
accuracy on 200 rows is a sanity check only (step 2 exact 98.1%), the accuracy figures are in
`2026-11-15-run10-vs-run9.md`.

## Shorter diagnostics: what they bought

Same 200 rows (the run 9 and run 10 test sets are aligned row by row; only the probe
compaction of 9db91c0 differs). Run 9 with the long diagnostics against run 10 with the short
ones; run 9 on the short ones gives the same times as run 10 (p50 9.9 s), so the difference is
the prompt, not the model.

| Step 2 category | n | p50 long → short | p95 long → short |
|---|---:|---:|---:|
| system | 12 | 23.1 → **19.9 s** | 32.4 → **22.1 s** |
| updates | 27 | 11.8 → 9.9 s | 15.3 → 13.3 s |
| storage | 11 | 11.0 → 9.0 s | 11.4 → 9.6 s |
| network | 34 | 12.0 → 12.0 s | 12.4 → 12.8 s |
| audio | 27 | 8.8 → 8.9 s | 12.1 → 12.0 s |
| printing | 8 | 5.2 → 5.4 s | 10.1 → 9.9 s |
| other | 15 | 3.9 → 3.8 s | 4.4 → 4.5 s |
| actions | 25 | 20.1 → 20.0 s | 22.1 → 22.0 s |
| **all step 2** | 160 | **11.3 → 9.9 s** | **23.0 → 20.8 s** |

About 2 s less on the categories whose probes were trimmed, 3 s on `system` at the median and
10 s on its tail (the longest kernel logs). On a Core 2 that is ~5–9 s at the median, ~28 s on
the `system` tail. Untouched categories are unchanged, as expected.

## What it means

- **Step 1 is interactive, step 2 is a wait.** On the target class of PC a typical answer is
  about half a minute. The product must say what it is doing while the person waits.
- **The two slow categories are `system` and `actions`** (~20 s here, ~55 s estimated on a
  Core 2). `system` is long diagnostics; `actions` is the list of installed apps in the prompt.
- **The action prompt is not cached in practice.** With one slot, llama-server keeps only the
  previous request: in real use that is step 1 of the same request, so the long action prefix
  is re-read every time (log: 645-token prompt, 519 evaluated, 17.9 s of prefill). Saving and
  restoring a slot with the action prefix, or a second slot kept warm, is the lever there:
  not done, to be measured.
