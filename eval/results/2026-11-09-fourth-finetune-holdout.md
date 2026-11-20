# Fourth fine-tune, Ubuntu held out — 2026-11-09

**What this is:** LoRA on Qwen3.5-0.8B, same recipe and data mix as the third
run, trained on the RTX 5070 in 1 h 37 min (bundle `a92fda26`, job
`20261109140657`, 1,170 steps, eval loss 0.0224). Every Ubuntu lab sample is
still removed from training. Q8_0 GGUF, llama.cpp on the devbox (Haswell,
4 threads).

What changed is only the data:

- the lab VMs were refreshed with the current wheel, so `firefox_stale_lock`
  (Firefox 147+ profile path, F-009/F-016) and the audio faults now inject and
  verify (12/12 each in the verification run);
- a new healthy control, `control_large_apt_cache` (2e7b846): a healthy machine
  with 1.5–4 GB of APT cache and more than 3 GB free, collected for every
  category (108/108 verified). It targets the third run's shortcut
  (`disk.apt_clean` whenever the cache is in GB).

Training: 6,229 rows (4,199 step 1; 2,030 step 2, of which 457 healthy and
677 actions). Large-cache healthy rows in training: 14 of 41 in storage, 20 of
67 in updates.

Test: **the whole step-2 test set this time**, 2,118 cases (1,232 repairs,
243 actions, 643 healthy machines), plus 531 step-1 messages. The third run was
scored on the first 800 cases only, so the columns are not the same set.

| Metric | Fourth run | Third run |
|---|---|---|
| Step 1, category | 96.0% | 95.3% |
| Step 2, right fix | 98.9% | 96.5% |
| Step 2, exact fix + parameters | 97.6% | 95.0% |
| Repairs, exact | 98.4% (n=1,232) | 99.5% (n=437) |
| Everyday actions, exact | 87.7% (n=243) | 89.1% (n=129) |
| Healthy machine, right answer ("nothing to do") | **100%** (n=643) | 89.7% (n=234) |
| **False fix on a healthy machine** | **0%** | 10.3% |
| False fix that would run without asking | 0% | 0% |
| **Escalation to a person when needed** | **63.6%** | 83.3% |
| Invalid outputs | 0% | 0% |
| Latency, step 2 p50 / p95 (devbox) | 3.2 s / 5.6 s | 3.5 s / 6.0 s |

## Reading

- **The APT-cache shortcut is gone.** 0 false fixes on 643 healthy machines,
  including the 28 storage and 47 updates cases with a large cache. In the third
  run it was 24 of 27 healthy storage cases.
- **Escalation got worse, and the cause is in the data, not the model.** All
  16 misses are `fs_root_readonly` on Ubuntu, answered "nothing to do" with
  confidence `low`. They are 4 whole lab samples (all 4 complaints each), and
  those 4 samples have one thing in common: **no EXT4 write errors in the kernel
  log**, because the probes ran before anything tried to write. The read-only
  flag is there (`ro` on `/` in `root_mount`) in every case. Every training
  sample (32 train, 8 val, all Debian) has the EXT4 errors, so the model learned
  "EXT4 errors → call a person" instead of "root mounted `ro` → call a person".
  The third run's 2 misses of 12 were probably the same thing on a smaller set.
  **Fix before the pilot:** read-only-root samples without kernel errors in
  training (probe right after the remount, before writeback), on Debian.
  A real failing disk logs errors, but a user can report the problem minutes
  after the remount, before anything has written.
  Confidence `low` means the answer is shown and not acted on, but here the
  answer is "nothing to do", which leaves a person with a dying disk without
  help: this is a safety case.
- **Repairs** are flat (98.4% on almost three times the cases). Besides the
  escalations, 4 `net_wifi_radio_off` cases answered `net.enable_networking`.
- **Actions**: 30 wrong. 15 of the 16 `web.search` errors are rewordings of the
  query ("meteo per domani" for "meteo domani"). The exact match is too strict
  for queries, as noted for the second run. The real errors: one back-pain search
  turned into opening the task manager, 3 `app.open` with the wrong app, 3 wrong
  sites, 2 folders opened as an app, 6 reminders.
- **Step 1**: the `other` category is weak (46%) on few cases; the rest is
  between 88% and 100%.

Caveat as before: complaints and requests are teacher-written; lab VMs are not
real 2008 hardware. Wrong answers are in `data/errors-run4.jsonl` and the report
in `data/eval-run4-report.json` (not versioned).
