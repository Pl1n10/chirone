"""Evaluate a backend on the test split.

    # the student, served by llama-server on the target machine
    python eval/run_eval.py --data data/dataset/test.jsonl --llamacpp http://127.0.0.1:8080
    # a big open model through an API, same prompts and schemas (the baseline)
    python eval/run_eval.py --data data/dataset/test.jsonl --openai "$BASE_URL" --model "$MODEL"

Metrics: step-1 accuracy, step-2 fix accuracy, exact match (fix + params),
invalid-output rate, escalation recall, false-fix rate on healthy machines,
latency p50/p95 (and llama.cpp prompt/predict ms when available). Step 2 is
also broken down into repairs / actions / healthy, because one average over
such different groups hides the weak one. `--errors` saves the wrong answers.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chirone.catalog import Catalog  # noqa: E402
from chirone.llm import LlamaCpp, LLMError, OpenAICompat  # noqa: E402
from chirone.schemas import step1_schema, step2_schema  # noqa: E402

NOT_A_FIX = {"noop.no_issue_found", "escalate.human"}


def pct(values, q):
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))]


def group_of(meta: dict) -> str:
    if meta["fault_id"] == "healthy_negative":
        return "healthy"
    return "actions" if meta["category"] == "actions" else "repairs"


def would_run_unasked(cat: Catalog, fix_id: str, confidence: str) -> bool:
    """Same rule as executor.py: nobody is asked only on a no-confirm playbook at high confidence."""
    return fix_id not in NOT_A_FIX and not cat.playbooks[fix_id].confirm and confidence == "high"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--llamacpp")
    g.add_argument("--openai")
    g.add_argument("--rules", action="store_true", help="hand-written rules instead of a model (rules_baseline.py)")
    ap.add_argument("--model")
    ap.add_argument("--extra", default="{}", help='JSON body fields for --openai, e.g. {"reasoning_effort": "none"}')
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sample", type=int,
                    help="a fixed random sample of N rows (seed 0): the latency run on a slow CPU, "
                         "while accuracy runs on all rows on the GPU")
    ap.add_argument("--step", type=int, choices=[1, 2], help="only rows of this step")
    ap.add_argument("--describe-categories", action="store_true",
                    help="zero-shot variant: list each category's label in the step-1 system prompt "
                         "(the shipped prompt has names only, to save prefill time)")
    ap.add_argument("--only", help="comma-separated fault ids: evaluate only these step-2 rows")
    ap.add_argument("--report", default="eval/report.json")
    ap.add_argument("--errors", help="write the wrong step-2 answers here (jsonl)")
    a = ap.parse_args()

    cat = Catalog()
    if a.rules:
        from rules_baseline import Rules
        llm = Rules()
    else:
        key = os.environ.get("OPENAI_API_KEY", "")
        llm = LlamaCpp(a.llamacpp) if a.llamacpp else OpenAICompat(a.openai, a.model, key, extra=json.loads(a.extra))
    rows = [json.loads(line) for line in Path(a.data).read_text(encoding="utf-8").splitlines()]
    only = set(a.only.split(",")) if a.only else None
    rows = [r for r in rows if not a.step or r["step"] == a.step]
    rows = [r for r in rows if not only or (r["step"] == 2 and r["meta"]["fault_id"] in only)][: a.limit]
    if a.sample and a.sample < len(rows):
        rows = random.Random(0).sample(rows, a.sample)
    errors = []
    by_lang: dict[str, Counter] = defaultdict(Counter)
    by_cat: dict[str, Counter] = defaultdict(Counter)

    stats = defaultdict(Counter)
    per_fault = defaultdict(Counter)
    groups = defaultdict(Counter)
    lat = defaultdict(list)
    lat_cat = defaultdict(list)
    prompt_ms, predict_ms = [], []
    for i, r in enumerate(rows):
        step, meta, gold = r["step"], r["meta"], json.loads(r["completion"])
        schema = step1_schema(cat) if step == 1 else step2_schema(cat, meta["category"])
        st = stats[step]
        st["n"] += 1
        prompt = r["prompt"]
        if step == 1 and a.describe_categories:
            legend = "; ".join(f"{c.id} = {c.label['en']}" for c in cat.categories.values())
            prompt = [{**prompt[0], "content": f"{prompt[0]['content']} Categories: {legend}."}, *prompt[1:]]
        try:
            c = llm.complete_json(prompt, schema, max_tokens=16 if step == 1 else 64)
        except LLMError:
            st["invalid"] += 1
            if step == 2:
                per_fault[meta["fault_id"]]["n"] += 1
                groups[group_of(meta)]["n"] += 1
            continue
        lat[step].append(c.seconds)
        if c.timings:
            prompt_ms.append(c.timings.get("prompt_ms", 0))
            predict_ms.append(c.timings.get("predicted_ms", 0))
        if step == 1:
            ok = c.data["category"] == gold["category"]
            st["correct"] += ok
            for d, key in ((by_lang, meta.get("lang", "?")), (by_cat, gold["category"])):
                d[key]["n"] += 1
                d[key]["ok"] += ok
            if (i + 1) % 50 == 0:
                print(f"{i + 1}/{len(rows)}", file=sys.stderr)
            continue
        fault = meta["fault_id"]
        lat_cat[meta["category"]].append(c.seconds)
        pf = per_fault[fault]
        pf["n"] += 1
        fix_ok = c.data["fix_id"] == gold["fix_id"]
        exact = fix_ok and {k: str(v) for k, v in c.data["params"].items()} == {
            k: str(v) for k, v in gold["params"].items()
        }
        st["fix"] += fix_ok
        st["exact"] += exact
        pf["exact"] += exact
        gr = groups[group_of(meta)]
        gr["n"] += 1
        gr["exact"] += exact
        if not exact:
            errors.append({"fault_id": fault, "category": meta["category"], "os": meta.get("os"),
                           "user": prompt[-1]["content"], "gold": gold, "got": c.data})
        if gold["fix_id"] == "escalate.human":
            st["escalate_gold"] += 1
            st["escalate_hit"] += fix_ok
        if fault == "healthy_negative":
            st["healthy"] += 1
            st["false_fix"] += c.data["fix_id"] not in NOT_A_FIX
            st["false_fix_unasked"] += would_run_unasked(cat, c.data["fix_id"], c.data["confidence"])
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(rows)}", file=sys.stderr)

    s1, s2 = stats[1], stats[2]
    report = {
        "backend": "rules" if a.rules else a.llamacpp or f"{a.openai} {a.model}",
        "described_categories": a.describe_categories,
        "step1_accuracy": s1["correct"] / max(1, s1["n"]),
        "step2_fix_accuracy": s2["fix"] / max(1, s2["n"]),
        "step2_exact": s2["exact"] / max(1, s2["n"]),
        "invalid_rate": (s1["invalid"] + s2["invalid"]) / max(1, s1["n"] + s2["n"]),
        "escalation_recall": s2["escalate_hit"] / max(1, s2["escalate_gold"]) if s2["escalate_gold"] else None,
        "false_fix_rate_healthy": s2["false_fix"] / max(1, s2["healthy"]) if s2["healthy"] else None,
        "false_fix_unasked_rate_healthy": s2["false_fix_unasked"] / max(1, s2["healthy"]) if s2["healthy"] else None,
        "step2_groups": {k: {"n": v["n"], "exact": round(v["exact"] / v["n"], 3)} for k, v in sorted(groups.items())},
        "latency_s": {f"step{k}": {"p50": pct(v, 0.5), "p95": pct(v, 0.95)} for k, v in lat.items()},
        "latency_step2_by_category_s": {
            k: {"n": len(v), "p50": pct(v, 0.5), "p95": pct(v, 0.95)} for k, v in sorted(lat_cat.items())
        },
        "llamacpp_ms": {"prompt_p50": statistics.median(prompt_ms), "predict_p50": statistics.median(predict_ms)}
        if prompt_ms else None,
        "per_fault_exact": {f: round(c["exact"] / c["n"], 3) for f, c in sorted(per_fault.items())},
        "per_fault_n": {f: c["n"] for f, c in sorted(per_fault.items())},
        "step1_by_lang": {k: round(v["ok"] / v["n"], 3) for k, v in sorted(by_lang.items())},
        "step1_by_category": {k: round(v["ok"] / v["n"], 3) for k, v in sorted(by_cat.items())},
        "n": {"step1": s1["n"], "step2": s2["n"]},
    }
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text(json.dumps(report, indent=2))
    if a.errors:
        Path(a.errors).write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in errors), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if not k.startswith("per_fault")}, indent=2))


if __name__ == "__main__":
    main()
