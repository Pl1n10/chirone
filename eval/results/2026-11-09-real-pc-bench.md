# Benchmark on the real target PC — 2026-11-09

**What this is:** the third fine-tune (`run-20261109072908`, see
`2026-11-09-third-finetune-holdout.md`) running on an Acer Veriton
M275 from 2009: Core 2 Quad Q8300 (no AVX), 3.8 GB RAM, Debian 13. This is the
class of machine chirone is meant for, and someone's daily PC, not a lab VM.

Run with a private remote-run tool's `chironebench.py` (`5f22910`): no-AVX llama.cpp binaries
from an internal packing script (bundle `d4394e91`), 4 threads, lowest CPU and I/O
priority, in a `DynamicUser` unit with no network and no access to home
directories. Nothing was compiled or installed on the machine, and everything
was removed afterwards. 35 minutes in total. Raw result:
`2026-11-09-real-pc-bench.json`.

## Speed (llama-bench, tokens/s)

| Model | Prefill 128 | Prefill 384 | Prefill 600 | Generation |
|---|---|---|---|---|
| Q8_0 | 10.4 | 10.3 | 10.0 | **5.2** |
| Q4_K_M | 6.9 | 7.0 | 6.8 | 3.7 |

Q8_0 beats Q4_K_M without AVX, as measured on the devbox proxy (F-006). The
devbox with the same no-AVX binaries does about 29 and 14 t/s: the 2009 PC is
roughly **2.8× slower** than the proxy, within the 30–60 s estimate made on
2026-11-07 for step 2.

## Real requests (Q8_0 served, 36 requests from the test set)

| | n | p50 | p95 | max | right answer |
|---|---|---|---|---|---|
| Step 1 (category) | 12 | **3.5 s** | 4.3 s | 6.5 s | 11 |
| Step 2 (fix + params) | 24 | **33 s** | 67 s | 72 s | 21 |

Step-2 time is almost all prefill: the diagnostics run to 200–680 tokens and
the answer is 21–46 tokens. Time grows linearly with diagnostics length (about
10 tokens/s), so shorter probe output is the lever, not a smaller model.

Model load 4.1 s; peak memory of the server 1.75 GB; available memory never
went below 1.3 GB (the run stops at 600 MB). Load before the run was 0.5 and
nobody was using the PC heavily during it.

## Reading

- **It runs on the target, with room to spare in memory.** A 0.8B Q8_0 model
  fits in a 4 GB PC from 2009 next to a desktop session.
- **Step 1 is interactive** (3–4 s). **Step 2 is not**: half a minute typical,
  over a minute for long diagnostics. For a person waiting, the product has to
  say what it is doing during that time, or cut the diagnostics sent to the
  model (dropping lines that carry no signal, e.g. healthy `du` lines).
- Correctness on 36 requests (32 right) is a sanity check that the no-AVX
  build gives the same answers, not an accuracy measure: that is in the
  held-out evaluation.
