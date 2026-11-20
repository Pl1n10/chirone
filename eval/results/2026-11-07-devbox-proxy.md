# Speed proxy on the devbox — 2026-11-07

**What this is:** stock Qwen3.5 GGUFs (unsloth), `llama-bench`, 4 threads,
3 repetitions, on an Intel i5-4590 (Haswell, 3.3 GHz, DDR3), llama.cpp
`80d2c0c` (2026-11-07). Two builds of the same commit:

* `build-noavx`: AVX/AVX2/FMA/F16C/SSE4.2 off — the instruction set of the
  Core 2 Quad Q8300 (SSE4.1). **An optimistic bound for the Veriton, not its
  speed:** the i5 has higher IPC, a higher clock, more cache and faster RAM.
* `build`: native (AVX2), standing in for the "typical" target (6th–7th gen
  Intel excluded from Windows 11).

Tokens per second (pp = prompt processing / prefill, tg = generation):

| model | quant | no-AVX pp600 | no-AVX tg24 | AVX2 pp600 | AVX2 tg24 |
|---|---|---:|---:|---:|---:|
| 0.8B | Q8_0 | **28.9** | **14.8** | 116.8 | 16.7 |
| 0.8B | Q4_K_M | 11.3 | 7.0 | **170.1** | **20.7** |
| 2B | Q4_K_M | 4.4 | 2.5 | 75.2 | 10.6 |

pp128 and pp384 are within a few percent of pp600 for every row (raw output:
`data/bench-devbox.txt`, not versioned).

## What it means

* **The best quantization depends on the CPU.** Without AVX, Q8_0 is ~2.5×
  faster than Q4_K_M (dequantizing 4-bit blocks with SSE only costs more than
  the bandwidth it saves). With AVX2 it is the other way round. The installer
  should pick the GGUF from `/proc/cpuinfo`, not ship one file.
* **Estimated time per answer, 0.8B, no-AVX proxy:** step 1 (~100 tokens in,
  ~5 out) ≈ 4 s; step 2 (~300–600 in, ~20 out) ≈ 12–22 s. Total ≈ 15–25 s
  before probes. On the real Q8300 expect 2–3× that: **~30–60 s**, to be
  measured on the Veriton.
* **The 2B is out for the floor machine** (> 2 min of prefill at 600 tokens
  without AVX). It remains an option for AVX2 machines.
* Prefix caching of the constant system prompts can only shave the shared
  part; with Qwen3.5's hybrid layers it must be measured, not assumed
  (`docs/architecture.md`).
