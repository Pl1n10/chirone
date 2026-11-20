# First fine-tune — 2026-11-08

**What this is:** the first LoRA fine-tune of Qwen3.5-0.8B (revision
`2fc0636`), trained at home on an RTX 5070 (12 GB) through a private remote-run tool's
`chironetrain.ps1`, then merged and quantized to GGUF Q8_0 and evaluated with
llama.cpp on the devbox, with the same commands and test split as the
zero-shot baselines (`2026-11-08-zeroshot-step1.md`).

Training: 4,593 rows (4,199 step 1, 394 step 2), LoRA r=32/α=64 on all linear
layers, 3 epochs, lr 2e-4, bf16, 864 steps, **35 min**, 9.4 GB VRAM. The
dataset was partial: lab collection was still running, and there were no PC
snapshots for the everyday-actions category yet, so `actions` was trained for
step 1 only.

| | zero-shot 0.8B | zero-shot 14B (described categories) | **fine-tuned 0.8B** |
|---|---|---|---|
| Step 1 accuracy (531 messages) | 34.3% | 50.7% | **96.0%** |
| Italian / English | 31.9% / 36.9% | 46.1% / 55.8% | **94.7% / 97.6%** |
| Everyday actions | 0.4% | 17.7% | **99.6%** |
| Step 2 exact fix + params (43 lab cases) | — | — | **43 / 43** |
| Invalid outputs | 0% | 0% | **0%** |

Per category, step 1: printing 100%, actions 99.6%, network 98.8%, audio
96.9%, system 95.2%, updates 91.3%, storage 90.0%, apps 87.5%, other 46.2%.

Latency on the devbox (Haswell, AVX2, 3 threads), Q8_0: step 1 p50 0.58 s,
step 2 p50 3.2 s. The old-PC figure needs the no-AVX proxy and the pilot
machine.

## Caveats, stated plainly

- **Step 2 is in-distribution.** The 43 test cases come from the same lab VMs
  and the same fault types as training (different samples, split by hash).
  100% here means "learned the catalog", not "generalizes". Next: hold out a
  whole OS (`build_dataset --holdout-os`), then real hardware.
- **`other` is weak (46%)**: few examples and a vague boundary.
- Test messages are teacher-written, not real users (see the baseline note).
