# Safety

A model that changes someone's computer must be boring and auditable.

## Guarantees

* **Closed action space.** The model picks a `fix_id` from the catalog; it
  cannot produce commands. Steps are fixed argv lists, never run through a
  shell.
* **Typed params, validated three times.** By the decoding grammar, by the
  executor, and again by the root helper. Patterns are anchored, cannot start
  with `-` (no option injection), no control characters. Root playbooks
  accept no `~` paths.
* **Least privilege.** One sudoers line for one helper. Root playbooks are
  few and listed in `docs/catalog.md`. The helper's wrapper runs Python with
  `-I` (isolated mode): `sudo` keeps the caller's working directory and plain
  `python -m` would import a `chirone/` package planted there, as root. A
  test pins the flag in both wrappers (`deploy/`, `lab/ansible/`).
* **Consent.** Every playbook that changes state or loses data asks first,
  in plain language, saying what may be lost (`confirm: true`). Only
  harmless, reversible ones (unmute, volume, waiting) skip confirmation,
  and only when the model answers `confidence: high`: anything less asks.
* **Preconditions.** e.g. never kill a desktop/session process, never touch
  Firefox's lock while Firefox runs.
* **Verification.** Every fix is followed by probe checks; failures are
  reported honestly with a way out (ask a person, reboot).
* **Escalation is a first-class answer.** Read-only filesystem, suspected
  hardware failure, anything unclear → `escalate.human`. It writes a
  plain-text summary (complaint, decision, diagnostics) to
  `~/.local/state/chirone/riepilogo-*.txt` for whoever comes to help. When
  it cannot be saved (a read-only disk is one reason to escalate) it is shown
  on screen instead, and the message says so: it never claims a save that
  did not happen.
* **Probes are read-only, with declared exceptions.** A probe that changes
  state must say so in `side_effect`; `docs/catalog.md` lists them and a test
  pins the set. Today there is one: `apt_update`, because a broken software
  source only shows up when apt tries to fetch it.
* **Local only.** No network calls besides what a fix itself needs (apt).
  Logs stay in `~/.local/state/chirone/actions.jsonl`, readable by the
  person and whoever they choose to show them to.

## Known gaps (v0)

* The helper trusts the installed catalog; integrity depends on the install
  being root-owned (it is, under `/opt/chirone`).
* `apt.fix_broken` and `apt.dpkg_configure` can pull packages from the
  network: acceptable, but they are `risk: medium` and confirmed.
* No rate limiting of repeated fixes yet.
* The `updates` bundle always runs `apt_update` (root, network, up to 120 s).
  On a 2008 PC it is the slowest part of a diagnosis: measure it on the
  target PC before deciding whether to keep it in the bundle.
