# Run 9 by hand on the tester VMs (2026-11-12)

Model `models/run-20261111220554/chirone-Q4_K_M.gguf` (SHA-256 `3584ada1…`) installed with
an internal tester-VM script on vm1 (Debian 13, VM 9111) and vm2 (Ubuntu 24.04, VM 9112), wheel
from 5a3ac51. 2 vCPU on a Proxmox node, CPU only, llama-server `--threads 2`.

## 1. The ten run 7 phrases, healthy PC

an internal script, logs an internal script, every confirmation answered "no".

- **vm1: same ten choices as run 7.**
- **vm2: one difference.** "non sento niente" → `audio.set_default_sink` with `sink: auto_null`,
  confidence `high` (run 7: `noop`, `low`). Cause: the script runs over ssh as the admin user, outside
  the graphical session, where PipeWire sees no card and the only sink is its `auto_null`,
  already the default. Asked again inside `nonna`'s session (the real case) run 9 answers
  `noop`, `low`, like run 7.
- The `auto_null` case can still happen to a real person (no driver, HDMI only), and the fix
  would change nothing. **Guard in 5a3ac51:** `audio.set_default_sink` now needs the sink to be
  listed and not already the default; `audio_wrong_default_sink` still passes (below).

## 2. Real faults, phrases written by us (not by the teacher)

an internal tester-VM script: reset to `clean`, inject, ask in `nonna`'s session answering "yes",
then run the fault's `check_broken` again. Logs kept privately.

| fault | phrase | vm1 Debian | vm2 Ubuntu |
|---|---|---|---|
| `net_wifi_radio_off` | "non mi trova più il wifi di casa, ieri andava" | ✅ fixed (32 s) | ✅ fixed (26 s) |
| `dns_manual_wrong` | "firefox dice che non trova il sito ma il cavo è attaccato" | ✅ fixed (43 s) | ✅ fixed (38 s) |
| `apt_bad_source_thirdparty` | "quando aggiorno esce una scritta rossa di errore" | ✅ right file, fixed (48 s) | ✅ right file, fixed (50 s) |
| `audio_wrong_default_sink` | "ho collegato il televisore e adesso dalle casse non esce più niente" | ✅ fixed (23 s) | ✅ fixed (19 s) |
| `printer_disabled` | "la stampante dice che è in pausa e non stampa" | ✅ fixed (14 s) | ✅ fixed (17 s) |
| `proc_runaway` | "è diventato lentissimo e la ventola fa un rumore tremendo" | ✅ fixed (119 s) | ✅ fixed (114 s) |
| `fs_root_readonly` | "non mi fa salvare niente, dice che è di sola lettura" | ✅ escalation | ✅ escalation |
| `control_thirdparty_source` (healthy) | "puoi controllare che gli aggiornamenti siano a posto?" | ✅ noop, `low` | ✅ noop, `low` |
| `disk_full_trash` | "dice che lo spazio è finito ma le foto vecchie le ho già buttate" | ✅ fixed, by hand over ssh (12 s) | lab error |
| `firefox_stale_lock` | "firefox non parte, dice che è già aperto ma non lo vedo" | ✅ fixed, by hand over ssh (12 s) | lab error |
| `net_networking_off` | "internet non va più, vicino all'orologio c'è una crocetta" | not testable | not testable |

**18/18 right answers where the case could be run (14 repairs verified, 2 escalations, 2 healthy-PC noops), 0 wrong**, including the two weak spots of the
run 9 test set (Wi-Fi on Ubuntu, third-party source next to the broken one).

- `wifi_radio_on` comes with confidence `medium`, so it asks before acting even though the
  playbook would not: correct behaviour, a little more friction.
- **`proc_runaway` takes ~2 minutes**: the runaway process eats one of the two vCPUs that
  llama-server uses. On an old PC the slow case is exactly the one where the person complains
  of slowness. Possible mitigation (not done): lower the runaway's priority, or chirone's
  `--threads`, while the model runs.
- Times are the full request (two model calls + probes + fix + verify) on the Proxmox node, not the target
  CPU: the target is in `2026-11-09-real-pc-bench.md`.

### Lab errors (not chirone)

Through `qm guest exec`, three cases always failed on both VMs, with
`qga command 'guest-exec' failed - got timeout`:
- `disk_full_trash` and `firefox_stale_lock` fail at the request step, but the same request over
  ssh in `nonna`'s environment picks the right fix and repairs (lock gone, disk from full to 23%).
- `net_networking_off`: on these VMs the guest agent stops running commands as soon as
  networking is off, before chirone is asked (a plain `curl` fails too), and ssh dies with the
  network. The lab VMs used for data collection verified `net.enable_networking` on every run;
  on the tester VMs it can only be tried from the screen (Guacamole).

## Not done

- No external testers yet: VMs left at `clean` and **stopped**, cloudflared not started.
