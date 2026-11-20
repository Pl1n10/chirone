# Lab

Throw-away VMs on Proxmox where faults are injected on purpose. Every fault in
`src/chirone/catalog/faults.yaml` declares the fix that is correct by
construction, so labels never come from a model.

## One-time setup

1. Create one VM per target OS (start with Debian 12 Xfce and Linux Mint 22
   Xfce), 2 vCPU, 4 GB RAM, 20 GB disk, QEMU guest agent enabled in the VM
   options. Keep the disk small: storage faults fill it.
2. `ansible-playbook -i lab/ansible/inventory.ini lab/ansible/setup.yml`
3. Shut the VM down and take a **disk-only** snapshot called `clean`.
   Disk-only on purpose: rollback becomes a cold boot, so the guest clock and
   every service start from a clean state (RAM snapshots resume with a stale
   clock and pollute `time_status`).
4. Create an API token restricted to the lab VMs and export it:
   `export CHIRONE_PVE_TOKEN=...`
5. `cp lab/config.example.yaml lab/config.yaml` and adjust.

## Collecting

    pip install -e '.[lab]'
    python -m lab.collect --config lab/config.yaml --faults audio_muted --reps 1   # smoke test
    python -m lab.collect --config lab/config.yaml                                 # overnight

Expect about a minute per sample (cold boot dominates): 24 faults x 8 reps x
2 VMs is roughly 6 hours.

Output: `data/samples/samples-*.jsonl`, one line per sample with the probe
bundle, the expected action and a `status`. Only `verified` rows are used
for training; the others are there to debug the catalog.

## Why the guest agent and not SSH

`net_networking_off`, `net_nm_stopped` and friends cut the VM's network.
The guest agent talks over a virtio serial channel, so injection,
probing and verification keep working.

## Fidelity

`fidelity: low` faults (Wi-Fi) cannot be reproduced faithfully in a VM.
Their samples are fine to bootstrap, but real-hardware samples from pilot
machines must be added before claiming results on them.
