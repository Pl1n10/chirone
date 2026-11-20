"""Dataset mix: the safety answer must not be drowned, and the ratio must be what it says."""
import json
import random

from chirone.catalog import Catalog
from datagen.build_dataset import cap_actions, main

CAT = Catalog()
FAULT = next(f for f in CAT.faults.values() if f.category == "audio" and not f.id.startswith("control"))


def sample(i, fault_id, fix_id):
    return {"vm": "v", "os": "debian13", "fault_id": fault_id, "rep": i, "fidelity": "high", "ts": "t",
            "sample_id": f"{fault_id}-{i}", "category": "audio", "status": "verified",
            "probes": [{"id": "audio_sinks", "rc": 0, "output": "x"}],
            "expected": {"fix_id": fix_id, "params": {}}, "apply_notes": ""}


def build(tmp_path, ratio):
    samples = tmp_path / "s.jsonl"
    rows = [sample(i, FAULT.id, "audio.unmute") for i in range(300)]
    rows += [sample(i, "control_nothing_broken", "noop.no_issue_found") for i in range(60)]
    samples.write_text("".join(json.dumps(r) + "\n" for r in rows) + '{"truncated', encoding="utf-8")
    complaints = tmp_path / "c.jsonl"
    complaints.write_text("".join(json.dumps({"fault_id": FAULT.id, "complaint": f"non sento {i}", "lang": "it"}) + "\n"
                                  for i in range(200)), encoding="utf-8")
    out = tmp_path / "out"
    main(["--samples", str(samples), "--complaints", str(complaints), "--out", str(out),
          "--healthy-negatives", str(ratio)])
    return [json.loads(ln) for ln in (out / "train.jsonl").read_text(encoding="utf-8").splitlines()]


def test_healthy_ratio_is_per_repair_row(tmp_path):
    rows = [r for r in build(tmp_path, 0.5) if r["step"] == 2]
    healthy = [r for r in rows if r["meta"]["fault_id"] == "healthy_negative"]
    repairs = len(rows) - len(healthy)
    assert 0.4 < len(healthy) / repairs < 0.6  # was a quarter of this: drawn once per sample, not per row
    assert all(json.loads(r["completion"])["fix_id"] == "noop.no_issue_found" for r in healthy)


def test_healthy_rows_have_healthy_probes_and_are_labelled(tmp_path):
    healthy = [r for r in build(tmp_path, 1.0) if r["meta"]["fault_id"] == "healthy_negative"]
    assert healthy and all(r["meta"]["sample_id"].startswith("control") and r["meta"]["lang"] == "it" for r in healthy)


def act(fix, n):
    return [{"step": 2, "meta": {"category": "actions", "fault_id": fix}} for _ in range(n)]


def test_cap_actions_keeps_share_and_proportions():
    repairs = [{"step": 2, "meta": {"category": "audio", "fault_id": "x"}} for _ in range(200)]
    step1 = [{"step": 1, "meta": {"fault_id": "x"}} for _ in range(50)]
    rows = cap_actions(repairs + step1 + act("web.search", 600) + act("app.open", 200), 1 / 3, random.Random(1))
    fixes = [r["meta"]["fault_id"] for r in rows if r["meta"].get("category") == "actions"]
    assert len(fixes) == 100
    assert fixes.count("web.search") == 75
    assert sum(r["step"] == 1 for r in rows) == 50
    assert sum(r["meta"].get("category") == "audio" for r in rows) == 200


def test_cap_actions_leaves_a_small_share_alone():
    rows = [{"step": 2, "meta": {"category": "audio", "fault_id": "x"}} for _ in range(90)] + act("app.open", 10)
    assert cap_actions(rows, 1 / 3, random.Random(1)) == rows
