# Roadmap

## Status (2026-11-20)

Working pre-alpha: 10 fine-tunes, a catalog of 43 probes / 33 playbooks /
9 categories / 27 lab faults, Debian family. Evaluated on a held-out OS
(Ubuntu 24.04) and benchmarked once on a real 2009 Core 2 Quad without AVX.
No daily users yet: the next step is a pilot with a local End of 10 / LUG
community, in propose-only mode on other people's PCs.

## Three-year arc

* **Year 1.** Debian family, 60–100 playbooks, catalog maintained in the
  open, pilots with 2–3 partner communities, real-hardware samples (Wi-Fi,
  printers, audio). Published lab, dataset, model and eval.
* **Year 2.** Same framework, second platform: Android via ADB
  (different probes and playbooks, same two-step model design).
* **Year 3.** Community-maintained catalog: volunteers at install parties add
  playbooks and faults through PRs; the lab retrains automatically.
