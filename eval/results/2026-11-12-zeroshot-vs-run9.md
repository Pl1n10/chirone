# Zero-shot baselines vs run 9, same test set (2026-11-12)

**What this is:** stock models with no fine-tuning, given chirone's shipped prompts and the
same JSON grammar, against the fine-tuned run 9, on `data/dataset-run9/test.jsonl`: Ubuntu
24.04 held out (no Ubuntu sample in training), 663 step-1 messages (Italian and English) and
2,411 step-2 cases (complaint + real diagnostics from the fault-injection lab).

Backends: Qwen3.5 0.8B and 2B base and run 9 as Q4_K_M on llama.cpp (home GPU (RTX 5070),
an internal GPU eval script); qwen3:14b on Ollama with reasoning off (it is also the teacher that
wrote the complaints, which if anything flatters it). Driver `data/run-baseline9.py`, reports
`data/eval-zs-*-on-run9-report.json` and `data/eval-run9-on-run9-report.json`.

| | 0.8B base | 2B base | qwen3:14b | **run 9 (0.8B fine-tuned)** |
|---|---|---|---|---|
| step 1: right category (663) | 26.4% | 31.8% | 38.3% | **95.8%** |
| … Italian / English | 23.8 / 29.4% | 28.6 / 35.5% | 34.6 / 42.6% | **95.2 / 96.5%** |
| step 2: right fix (2,411) | 3.8% | 6.0% | 30.3% | **96.8%** |
| step 2: exact fix + params | 2.9% | 2.4% | 27.5% | **95.4%** |
| real repairs, exact (1,394) | 2.7% | 2.3% | 32.6% | **97.2%** |
| everyday actions, exact (337) | 9.5% | 8.0% | 15.1% | **87.5%** |
| escalation when the disk is failing | 0% | 65% | 24% | **100%** |
| **healthy PC: a fix that changes something** (784 rows whose answer is "nothing to do") | 41 (5.2%) | 32 (4.1%) | **258 (32.9%)** | **9 (1.1%)** |
| invalid JSON | 0% | 0% | 0% | 0% |

The "changes something" row excludes the harmless answers (`noop`, `escalate.human`,
`info.what_i_can_do`); `run_eval.py`'s own `false_fix_rate_healthy` counts
`info.what_i_can_do` as a fix and reads 100% / 80% / 50% / 4.4%.

## Reading

- **The small base models are harmless only because they are useless.** On a healthy PC the
  0.8B answers "here is what I can do" 743 times out of 784, and it does the same on broken
  ones: 3.8% right fixes. Nothing to build on without fine-tuning.
- **A 17× bigger model is the dangerous one.** qwen3:14b actually tries: 30% right fixes, but
  on one healthy PC in three it would run something, 90 times `apt.fix_broken` and 58 times
  a volume change, and it escalates a failing disk 24% of the time. A general model behind a
  prompt does not know when *not* to act on this catalog.
- **Run 9 is the only one that is both useful and careful:** 96.8% right fixes on an OS it never
  saw in training, every failing disk escalated, 9 healthy-PC answers out of 784 that would
  touch something (all `apt.wait_for_lock`, which only waits).
- **Everyday actions are where size helps least and fine-tuning most** (14B 15%, run 9 87.5%:
  the misses are mostly rephrased search queries, see `2026-11-12-run9-vs-8-vs-7.md`).
- **Italian stays harder than English for every stock model** (−6 to −8 points: 5.6, 6.9, 8.0); after
  fine-tuning the gap is 1.3 points.

## Caveats

- Test complaints are teacher-written, not real users. The hands-on check with our own
  phrases is in `2026-11-12-run9-hands-on.md` (18/18 right answers on the two tester VMs).
- Stock models see the shipped, terse prompts (category names only, no descriptions),
  because every prompt token costs seconds on the target CPU. With descriptions the 14B
  gained ~11 points on step 1 on 2026-11-08 (`2026-11-08-zeroshot-step1.md`): still far from 96%.
- The 14B is not a candidate for the target anyway: it does not fit a 4 GB PC.
