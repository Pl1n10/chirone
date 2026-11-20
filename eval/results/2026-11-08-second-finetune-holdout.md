# Second fine-tune, Ubuntu held out — 2026-11-08

**What this is:** LoRA on Qwen3.5-0.8B (`2fc0636`), trained on the RTX 5070
(1,215 steps, 1 h 39 min) with **every Ubuntu lab sample removed from
training**: step 2 is tested on an OS the model never saw. Q8_0 GGUF, llama.cpp
on the devbox (Haswell, 4 threads).

Training data: 6,470 rows (4,199 step 1; 2,271 step 2, all Debian 13, of which
1,921 everyday actions). Test: 531 step-1 messages; 638 step-2 cases (611 on
Ubuntu 24.04, 27 on Debian).

| Metric | Result |
|---|---|
| Step 1, category | **95.7%** (first fine-tune: 96.0%) |
| Step 2, right fix | **98.0%** |
| Step 2, exact fix + parameters | **94.0%** |
| Escalation to a person when needed | 100% |
| Invalid outputs | 0% |
| **False fix on a healthy machine** | **46.7%** ← the weak spot |
| Latency, step 2 p50 / p95 (devbox) | 3.6 s / 5.7 s |

Exact match per fault family on the unseen OS: network, audio, printing,
updates, storage, system faults at 100% except Wi-Fi radio (80%), thumbnails
cache (83%), bad APT source (83%); everyday actions: open folder 100%, volume
100%, open website 95%, open program 94%, reminder 94%, **web search 65%**.

## Reading

- **It generalizes across the distribution.** The repair catalog transfers
  from Debian 13 to Ubuntu 24.04 almost intact: package names, NetworkManager
  connection names and sink names differ, and the parameters are still copied
  right from the diagnostics.
- **It does not yet know when to do nothing.** Shown a real complaint with
  diagnostics of a healthy machine, it proposes a fix in almost half the cases.
  This is the safety metric that matters most and the next run targets it
  (more healthy negatives, a balanced step-2 mix). Mitigations already in the
  product: risky fixes ask for confirmation, every fix verifies its effect, and
  nothing outside the closed catalog can run.
- **Web search queries** match the person's words exactly only 65% of the time;
  to be checked case by case (the model may pick a slightly different subset
  of the person's words, which is not necessarily a worse search).

## Correction, 2026-11-09

An earlier version said 15% of step-2 rows taught the "do nothing" answer. That
was the value of the option, not the data: a bug drew it once per sample, so
training had **14 healthy rows out of 2,271**. Also, the 46.7% is **7 cases out
of 15**, too few for a precise rate.

Broken down, exact match on the 638 cases: repairs 97.9% (n=380), everyday
actions 90.5% (n=243), healthy machines 53.3% (n=15).

Re-running this model on the weak cases with the wrong answers saved
(`--only web.search,healthy_negative`):

- All 7 false fixes came at `high` confidence, and all 7 are playbooks that ask
  for confirmation first: none would have run unasked. They would still have
  put a wrong proposal in front of a person, for example disabling a working
  APT source or terminating a process.
- All 13 wrong web searches are rewordings of the person's request ("meteo per
  domani" for "meteo domani"), and by reading them all are usable searches.
  Exact match is too strict for this field. This is a judgement on 13 cases,
  not a measurement.

Caveat as before: complaints and requests are teacher-written; lab VMs are not
real 2008 hardware.
