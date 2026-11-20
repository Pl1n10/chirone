# Third fine-tune, Ubuntu held out — 2026-11-09

**What this is:** LoRA on Qwen3.5-0.8B, same recipe as the second run, trained
on the RTX 5070 in 1 h 26 min (bundle `3243800b`, job `20261109072908`). Every
Ubuntu lab sample is still removed from training. Q8_0 GGUF, llama.cpp on the
devbox (Haswell, 4 threads).

What changed is the data mix (`ec9fdc4`): healthy negatives drawn per repair row
(`--healthy-negatives 0.5`) and everyday actions capped at a third of the step-2
rows (`--max-action-share 0.3333`). Training: 5,745 rows (4,199 step 1; 1,546
step 2: 688 repairs, 516 actions, **342 healthy**, against 14 in the second run).

Test: 531 step-1 messages; the first 800 of 1,412 step-2 cases (437 repairs,
129 actions, 234 healthy machines).

| Metric | Third run | Second run |
|---|---|---|
| Step 1, category | 95.3% | 95.7% |
| Step 2, right fix | 96.5% | 98.0% |
| Step 2, exact fix + parameters | 95.0% | 94.0% |
| Repairs, exact | **99.5%** (n=437) | 97.9% (n=380) |
| Everyday actions, exact | 89.1% (n=129) | 90.5% (n=243) |
| Healthy machine, right answer ("nothing to do") | **89.7%** (n=234) | 53.3% (n=15) |
| **False fix on a healthy machine** | **10.3%** | 46.7% |
| False fix that would run without asking | **0%** | 0% |
| Escalation to a person when needed | 83.3% | 100% |
| Invalid outputs | 0% | 0% |
| Latency, step 2 p50 / p95 (devbox) | 3.5 s / 6.0 s | 3.6 s / 5.7 s |

The two runs are not tested on identical sets (the test set grew with the
collection), so differences of a point or two are noise. The healthy-machine
row is the one that moved, and on 234 cases instead of 15.

## Reading

- **The "do nothing" weakness is mostly fixed by data.** With healthy rows
  actually in training, false fixes drop from 7 of 15 to 24 of 234, and none of
  them would run without a confirmation.
- **The remaining false fixes are one shortcut, not noise.** All 24 are
  `disk.apt_clean` on a healthy machine in the storage category: 24 of 27
  healthy storage cases, against almost none in the other categories. In the
  Debian training data the APT cache is in gigabytes only when the fault *is* a
  full APT cache (16–17 GB); healthy machines and the other faults show
  400–560 MB. The Ubuntu lab VMs carry 1.4 GB of APT cache when healthy, with the
  disk at 33%. The model learned "cache in GB → clean it" instead of reading
  disk usage. A real PC with years of updates has a cache of a few GB, so this
  must be fixed in the data before the pilot: healthy samples with a large APT
  cache and free disk, on both OSes.
- **Escalation missed twice.** `fs_root_readonly` (n=12) answered "nothing to
  do" twice instead of "call a person": with a read-only root the answer should
  be escalation. Low counts, but it is a safety case and goes in the next
  data review.
- **Actions** are unchanged in substance. Of 15 wrong actions, 7 are web-search
  rewordings ("ricetta facile con la pasta" for "ricetta facile con pasta"),
  2 are reminder texts reworded ("uscita" for "uscire"); the real errors are 4
  wrong sites or app (RaiPlay → a video player or the spreadsheet; INPS → tax
  agency; Libero mail → Gmail) and one calculator → spreadsheet.

Caveat as before: complaints and requests are teacher-written; lab VMs are not
real 2008 hardware. Wrong answers are in `data/errors-run3.jsonl` (not versioned).
