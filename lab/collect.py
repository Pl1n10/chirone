"""Collect verified samples from the lab.

For every VM x fault x rep:
  reset VM -> inject -> confirm the fault is real -> collect the category's
  probe bundle as the desktop user -> derive the expected params from the
  probes -> apply the expected fix with chirone itself -> record whether it
  verified. Only verified samples become training data.

The control fault collects every category's bundle on a healthy machine:
those snapshots teach the model to answer noop.no_issue_found.

    python -m lab.collect --config lab/config.yaml [--faults a,b] [--reps 3]
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import time
import uuid
from pathlib import Path

import yaml

from chirone.catalog import Capture, Catalog, Fault

from .pve import Lab, QmLab, make_lab


def expected_params(cat: Catalog, fault: Fault, probes: list[dict]) -> dict | None:
    by_id = {p["id"]: p["output"] for p in probes}
    pb = cat.playbooks[fault.expected.fix_id]
    out = {}
    for name, spec in pb.params.items():
        v = fault.expected.params.get(name, spec.default)
        if isinstance(v, Capture):
            m = re.search(v.regex, by_id.get(v.probe, ""), re.M)
            if not m:
                return None
            v = m.group(1)
        out[name] = int(v) if spec.type == "int" else str(v)
    return out


def collect_one(lab: Lab | QmLab, cfg: dict, cat: Catalog, vm: dict, fault: Fault, rep: int) -> list[dict]:
    vmid, as_user = vm["vmid"], fault.run_as == "user"
    lab.reset(vmid, cfg["snapshot"])
    # Lab artifact, not a real-world fault: with linger the user's WirePlumber
    # starts before the sound card is ready and can lose the ALSA sink
    # ("Object activation aborted"), so after a cold boot a VM randomly has
    # only auto_null. A desktop login starts it later. Restart it once so
    # every sample starts from the same audio state.
    # With the autologin desktop the sink can take longer than a fixed 3 s to
    # come back (audio_muted: "No such entity" on @DEFAULT_SINK@, 2026-11-08):
    # wait until a default sink resolves, up to 30 s.
    lab.exec(vmid, "systemctl --user restart wireplumber; for i in $(seq 30); do "
                   "pactl get-sink-mute @DEFAULT_SINK@ >/dev/null 2>&1 && break; sleep 1; done",
             as_user=True)
    base = {"vm": vm["name"], "os": vm["os"], "fault_id": fault.id, "rep": rep,
            "fidelity": fault.fidelity, "ts": int(time.time())}

    rc, out = lab.exec(vmid, fault.inject, as_user=as_user)
    rc, _ = lab.exec(vmid, fault.check_broken, as_user=as_user)
    if rc != 0:
        return [{**base, "sample_id": uuid.uuid4().hex, "status": "not_broken", "inject_out": out[-500:]}]

    categories = list(cat.categories) if fault.id.startswith("control") else [fault.category]
    samples = []
    for category in categories:
        rc, out = lab.exec(vmid, f"{cfg['chirone_bin']} probe --category {category} --json", as_user=True)
        try:
            probes = json.loads(out[out.index("["):])
        except ValueError:
            samples.append({**base, "sample_id": uuid.uuid4().hex, "status": "probe_error", "out": out[-500:]})
            continue
        sample = {**base, "sample_id": uuid.uuid4().hex, "category": category, "probes": probes}
        params = expected_params(cat, fault, probes)
        if params is None:
            samples.append({**sample, "status": "capture_failed"})
            continue
        sample["expected"] = {"fix_id": fault.expected.fix_id, "params": params}
        samples.append(sample)

    pb = cat.playbooks[fault.expected.fix_id]
    if not pb.steps:  # escalate / noop: correct by construction
        return [{**s, "status": s.get("status", "verified")} for s in samples]

    s = samples[0]
    if "expected" in s:
        args = " ".join(shlex.quote(f"{k}={v}") for k, v in s["expected"]["params"].items())
        rc, out = lab.exec(vmid, f"{cfg['chirone_bin']} apply {pb.id} {args} --yes --json", as_user=True, timeout=1200)
        try:
            outcome = json.loads(out[out.index("{"):])
        except ValueError:
            outcome = {"status": "apply_error", "notes": [out[-500:]]}
        s["status"] = "verified" if outcome.get("status") == "done" else f"fix_{outcome.get('status')}"
        s["apply_notes"] = outcome.get("notes", [])[-5:]
    return samples


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="lab/config.yaml")
    ap.add_argument("--faults", help="comma-separated fault ids (default: all)")
    ap.add_argument("--reps", type=int)
    ap.add_argument("--vm", help="only this VM name (run one process per VM to go in parallel)")
    a = ap.parse_args()

    cfg = yaml.safe_load(Path(a.config).read_text())
    cat, lab = Catalog(), make_lab(cfg)
    wanted = a.faults.split(",") if a.faults else list(cat.faults)
    reps = a.reps or cfg["reps"]
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    vms = [v for v in cfg["vms"] if not a.vm or v["name"] == a.vm]
    if not vms:
        raise SystemExit(f"no VM named {a.vm!r} in {a.config}")
    suffix = f"-{vms[0]['name']}" if a.vm else ""
    out = out_dir / f"samples-{time.strftime('%Y%m%d-%H%M%S')}{suffix}.jsonl"

    with out.open("a", encoding="utf-8") as f:
        # Rep-major: every fault gets one sample before any gets a second, so a
        # run cut short (the devbox sleeps at night) still covers the catalog.
        for vm in vms:
            for rep in range(reps):
                for fid in wanted:
                    try:
                        rows = collect_one(lab, cfg, cat, vm, cat.faults[fid], rep)
                    except Exception as e:  # keep the overnight run going
                        rows = [{"vm": vm["name"], "fault_id": fid, "rep": rep, "status": "lab_error", "error": str(e)}]
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                        f.flush()
                        print(f"{vm['name']:16} {fid:28} rep={rep} {r.get('category', '-'):9} {r['status']}")


if __name__ == "__main__":
    main()
