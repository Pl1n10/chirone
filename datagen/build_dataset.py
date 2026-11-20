"""Join verified lab samples with teacher complaints into train/val/test.

Each row: {"step": 1|2, "prompt": [messages], "completion": "<json>", "meta": {...}}
The prompt is built with chirone.prompts, i.e. exactly what runs on the PC.

Splits are deterministic and leak-free: complaints and lab samples are each
split by hash, and test rows only combine test complaints with test samples.
`--holdout-os mint22` additionally keeps one OS out of train entirely, to
measure generalization to a distro the model never saw.

    python -m datagen.build_dataset --samples 'data/samples/*.jsonl' \
        --complaints data/complaints.jsonl data/complaints-en.jsonl --out data/dataset
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from chirone.catalog import Catalog
from chirone.probes import compact, diagnostics_block, from_json
from chirone.prompts import step1_messages, step2_messages
from chirone.schemas import step2_target


def split_of(key: str, val: float = 0.1, test: float = 0.1) -> str:
    h = int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if h < test else "val" if h < test + val else "train"


def confidence_for(fidelity: str) -> str:
    return {"high": "high", "medium": "high", "low": "medium"}[fidelity]


def action_params(req: dict, probes: dict[str, str], concepts: dict) -> dict | None:
    """Label of an action request on one PC, or None if it has no answer there."""
    if req["fix_id"] in ("app.open", "app.close"):
        installed = {ln.split(":", 1)[0] for ln in probes.get("apps_installed", "").splitlines()}
        app = next((i for i in concepts[req["concept"]]["ids"] if i in installed), None)
        return {"app": app} if app else None
    if req["fix_id"] in ("web.search", "web.open_site"):
        browser = probes.get("browser_default", "").strip().removesuffix(".desktop")
        if browser not in ("firefox", "firefox-esr"):
            return None
        given = {"query": req["query"]} if req["fix_id"] == "web.search" else dict(req["params"])
        return {**given, "browser": browser}
    if "params" in req:  # fixed or already checked against the request (datagen.requests)
        return dict(req["params"])
    raise ValueError(f"unknown action {req['fix_id']}")


def cap_actions(rows: list[dict], share: float, rng: random.Random) -> list[dict]:
    """Keep action rows to `share` of the step-2 rows, proportionally per fix_id.

    Step-1 rows and the other step-2 rows are never touched.
    """
    # off-topic rows under `actions` are not actions: they teach "do nothing" (F-018)
    actions = [r for r in rows if r["step"] == 2 and r["meta"]["category"] == "actions"
               and r["meta"]["fault_id"] != "offtopic"]
    others = sum(r["step"] == 2 and r["meta"]["category"] != "actions" for r in rows)
    keep_total = round(others * share / (1 - share))
    if len(actions) <= keep_total:
        return rows
    by_fix: dict[str, list[dict]] = defaultdict(list)
    for r in actions:
        by_fix[r["meta"]["fault_id"]].append(r)
    dropped: set[int] = set()
    for items in by_fix.values():
        keep = round(len(items) * keep_total / len(actions))
        rng.shuffle(items)
        dropped.update(id(r) for r in items[keep:])
    return [r for r in rows if id(r) not in dropped]


_MARKER = re.compile(r"^\.\.\. \(\+(\d+)(?: earlier)? lines\)$")


def recompact(cat: Catalog, probes: list[dict]) -> None:
    """Apply today's `fields`, `keep` and `max_lines` to an output saved by an older collector.

    Samples store the probe output already compacted; a probe that later gained
    `fields` (dns_lookup, F-019) or got a tighter `keep`/`max_lines` (run 10)
    would otherwise show the model two shapes of the same output. The old
    "... (+N lines)" marker is folded into the new count. Every step only
    removes lines, so this is idempotent.
    """
    for p in probes:
        probe = cat.probes.get(p["id"])
        if not probe:
            continue
        lines = p["output"].splitlines()
        extra = 0
        for i in (0, -1):
            m = _MARKER.match(lines[i]) if lines else None
            if m:
                extra += int(m.group(1))
                lines.pop(i)
        body = compact("\n".join(lines), probe.keep, 10**6, fields=probe.fields).splitlines()
        extra += max(0, len(body) - probe.max_lines)
        if extra and probe.tail:
            body = [f"... (+{extra} earlier lines)", *body[-probe.max_lines:]]
        elif extra:
            body = [*body[:probe.max_lines], f"... (+{extra} lines)"]
        p["output"] = "\n".join(body)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", required=True, help="glob of lab sample files")
    ap.add_argument("--complaints", required=True, nargs="+", help="one or more complaint files (e.g. it + en)")
    ap.add_argument("--out", default="data/dataset")
    ap.add_argument("--requests", nargs="*", default=[],
                    help="action requests from datagen.requests (category actions)")
    ap.add_argument("--offtopic", nargs="*", default=[],
                    help="datagen.offtopic messages -> category other, fix info.what_i_can_do")
    ap.add_argument("--complaints-as", nargs="*", default=[], metavar="FAULT=SOURCE",
                    help="step 2 rows of FAULT use SOURCE's complaints (same symptom, no complaints of its own)")
    ap.add_argument("--complaints-per-sample", type=int, default=4)
    ap.add_argument("--healthy-negatives", type=float, default=0.15,
                    help="extra rows per repair row: a real complaint with a healthy bundle -> noop")
    ap.add_argument("--max-action-share", type=float, default=None,
                    help="cap action rows to this share of step-2 rows in train/val (test keeps them all)")
    ap.add_argument("--holdout-os")
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args(argv)

    rng = random.Random(a.seed)
    cat = Catalog()

    complaints: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    lines = [ln for p in a.complaints for ln in Path(p).read_text(encoding="utf-8").splitlines()]
    lang_of: dict[str, str] = {}
    for line in lines:
        c = json.loads(line)
        complaints[c["fault_id"]][split_of("c:" + c["complaint"])].append(c["complaint"])
        lang_of[c["complaint"]] = c.get("lang", "it")  # the first Italian batch predates the field

    alias = dict(x.split("=", 1) for x in a.complaints_as)

    samples, healthy = [], defaultdict(list)
    partial = 0
    for path in glob.glob(a.samples):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                s = json.loads(line)
            except json.JSONDecodeError:  # a collector may be writing this file right now
                partial += 1
                continue
            if s.get("status") != "verified":
                continue
            recompact(cat, s["probes"])
            s["split"] = "test" if a.holdout_os and s["os"] == a.holdout_os else split_of("s:" + s["sample_id"])
            samples.append(s)
            if s["fault_id"].startswith("control"):
                healthy[(s["category"], s["split"])].append(s)

    if partial:
        print(f"samples: {partial} unreadable lines skipped")

    rows: dict[str, list[dict]] = defaultdict(list)

    # Step 1: complaint -> category (one row per complaint).
    for fid, by_split in complaints.items():
        category = cat.faults[fid].category
        for split, items in by_split.items():
            for c in items:
                rows[split].append({
                    "step": 1,
                    "prompt": step1_messages(c),
                    "completion": json.dumps({"category": category}),
                    "meta": {"fault_id": fid, "lang": lang_of.get(c, "it")},
                })

    # Step 2: complaint + diagnostics -> fix.
    no_complaints: dict[str, int] = defaultdict(int)
    for s in samples:
        fid, split = s["fault_id"], s["split"]
        pool = complaints[alias.get(fid, fid)].get(split, [])
        if fid.startswith("control") and s["category"] != "other":
            continue  # healthy bundles of real categories are used as negatives below
        if not pool:
            no_complaints[fid] += 1
            continue
        diag = diagnostics_block(from_json(s["probes"]))
        target = step2_target(s["expected"]["fix_id"], s["expected"]["params"], confidence_for(s["fidelity"]))
        for c in rng.sample(pool, min(a.complaints_per_sample, len(pool))):
            rows[split].append({
                "step": 2,
                "prompt": step2_messages(c, s["category"], diag),
                "completion": json.dumps(target, ensure_ascii=False),
                "meta": {"fault_id": fid, "sample_id": s["sample_id"], "os": s["os"], "category": s["category"],
                         "lang": lang_of.get(c, "it")},
            })
            # Healthy negative: same complaint, nothing broken -> do not invent a fix.
            if rng.random() < a.healthy_negatives and healthy.get((s["category"], split)):
                h = rng.choice(healthy[(s["category"], split)])
                rows[split].append({
                    "step": 2,
                    "prompt": step2_messages(c, s["category"], diagnostics_block(from_json(h["probes"]))),
                    "completion": json.dumps(step2_target("noop.no_issue_found", {}, "low")),
                    "meta": {"fault_id": "healthy_negative", "source_fault": fid, "sample_id": h["sample_id"],
                             "os": h["os"], "category": s["category"], "lang": lang_of.get(c, "it")},
                })

    # Actions: the request is the label source, the PC snapshot gives the ids.
    concepts = yaml.safe_load((Path(__file__).parent / "apps.yaml").read_text(encoding="utf-8"))
    skipped = 0
    for line in (ln for p in a.requests for ln in Path(p).read_text(encoding="utf-8").splitlines()):
        r = json.loads(line)
        split = split_of("r:" + r["request"])
        rows[split].append({"step": 1, "prompt": step1_messages(r["request"]),
                            "completion": json.dumps({"category": "actions"}),
                            "meta": {"fault_id": r["fix_id"], "lang": r.get("lang")}})
        bundles = list(healthy.get(("actions", split), []))
        rng.shuffle(bundles)
        for h in bundles:
            params = action_params(r, {p["id"]: p["output"] for p in h["probes"]}, concepts)
            if params is None:
                continue
            target = step2_target(r["fix_id"], params, "high")
            rows[split].append({
                "step": 2,
                "prompt": step2_messages(r["request"], "actions", diagnostics_block(from_json(h["probes"]))),
                "completion": json.dumps(target, ensure_ascii=False),
                "meta": {"fault_id": r["fix_id"], "sample_id": h["sample_id"], "os": h["os"],
                         "category": "actions", "lang": r.get("lang")},
            })
            break
        else:
            skipped += 1
    if a.requests:
        print(f"actions: {skipped} requests without a matching PC snapshot (program not installed or no bundle)")

    # Off-topic: greetings, questions about chirone, impossible requests. Step 1
    # says `other`; step 2 answers info.what_i_can_do both under `other` and
    # under `actions`, where a wrong step 1 sends them most (F-018).
    seen_offtopic: set[str] = set()
    for line in (ln for p in a.offtopic for ln in Path(p).read_text(encoding="utf-8").splitlines()):
        o = json.loads(line)
        if o["text"].lower() in seen_offtopic:  # the seeds are in every generated file
            continue
        seen_offtopic.add(o["text"].lower())
        split = split_of("o:" + o["text"])
        meta = {"fault_id": "offtopic", "kind": o["kind"], "lang": o["lang"]}
        rows[split].append({"step": 1, "prompt": step1_messages(o["text"]),
                            "completion": json.dumps({"category": "other"}), "meta": meta})
        category = rng.choice(["other", "actions"])
        bundles = healthy.get((category, split)) or healthy.get(("other", split))
        if not bundles:
            continue
        h = rng.choice(bundles)
        rows[split].append({
            "step": 2,
            "prompt": step2_messages(o["text"], category, diagnostics_block(from_json(h["probes"]))),
            "completion": json.dumps(step2_target("info.what_i_can_do", {}, "high")),
            "meta": {**meta, "sample_id": h["sample_id"], "os": h["os"], "category": category},
        })

    # Run 9 lost a whole new fault this way without a word (2026-11-11).
    for fid, n in sorted(no_complaints.items()):
        print(f"warning: {n} {fid} samples skipped, no complaints in their split", file=sys.stderr)

    if a.max_action_share is not None:
        for split in ("train", "val"):
            rows[split] = cap_actions(rows[split], a.max_action_share, rng)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for split, items in rows.items():
        rng.shuffle(items)
        with (out / f"{split}.jsonl").open("w", encoding="utf-8") as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        n1 = sum(r["step"] == 1 for r in items)
        healthy_rows = sum(r["meta"]["fault_id"] == "healthy_negative" for r in items)
        action_rows = sum(r["step"] == 2 and r["meta"]["category"] == "actions" for r in items)
        print(f"{split:5}: {len(items):6} rows (step1 {n1}, step2 {len(items) - n1}: "
              f"{healthy_rows} healthy, {action_rows} actions)")


if __name__ == "__main__":
    main()
