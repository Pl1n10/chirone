"""Clone a lab VM from its `clean` snapshot, to collect on more VMs in parallel.

    python -m lab.clone --src 9101 --vmid 9103 --name lab-debian13-xfce-b \
        --address 192.168.1.153/24 [--memory 3072]

A clone is not usable as it comes out of `qm clone`: it has the source's
fixed lab address (ARP conflict with the source) and the source's machine-id,
from which NetworkManager's DHCP client id is derived, so the router would
hand both VMs the same lease. This boots the clone once, gives it its own
address, machine-id and hostname, shuts it down and takes its own `clean`.
Then add it to lab/config.yaml (and inventory.ini) and run one collector per VM.
"""
from __future__ import annotations

import argparse
import shlex

import yaml

from .pve import QmLab

CONN = "/etc/NetworkManager/system-connections/Connessione via cavo 1.nmconnection"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="lab/config.yaml")
    ap.add_argument("--src", type=int, required=True)
    ap.add_argument("--vmid", type=int, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--address", required=True, help="fixed lab address with prefix, e.g. 192.168.1.153/24")
    ap.add_argument("--memory", type=int, help="MiB, default: same as the source")
    ap.add_argument("--snapshot", default="clean")
    a = ap.parse_args()

    lab = QmLab(yaml.safe_load(open(a.config)))
    vmid = str(a.vmid)
    print(f"clone {a.src}@{a.snapshot} -> {vmid} {a.name}")
    lab._ok("clone", str(a.src), vmid, "--snapname", a.snapshot, "--full", "1", "--name", a.name, timeout=1800)
    if a.memory:
        lab._ok("set", vmid, "--memory", str(a.memory))
    lab._ok("start", vmid)
    lab._wait_agent(a.vmid)
    script = f"""set -e
sed -i 's|^address1=.*|address1={a.address}|' {shlex.quote(CONN)}
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup >/dev/null
ln -sf /etc/machine-id /var/lib/dbus/machine-id
rm -f /var/lib/NetworkManager/*.lease /var/lib/NetworkManager/internal-*
hostnamectl set-hostname {shlex.quote(a.name)}
sed -i 's/^127\\.0\\.1\\.1.*/127.0.1.1 {a.name}/' /etc/hosts
grep ^address1= {shlex.quote(CONN)}; cat /etc/machine-id; hostname"""
    rc, out = lab.exec(a.vmid, script)
    print(out.strip())
    if rc != 0:
        raise SystemExit(f"customisation failed (rc={rc}); clone {vmid} left running for inspection")
    lab._ok("shutdown", vmid, "--timeout", "180", timeout=240)
    lab._ok("snapshot", vmid, a.snapshot, timeout=600)
    print(f"{vmid} ready: snapshot {a.snapshot} taken")


if __name__ == "__main__":
    main()
