"""Generate user complaints for each fault with an open-weights teacher model
behind any OpenAI-compatible API (a hosted provider or your own vLLM).

The teacher writes *language only*. Labels come from the lab.

    export TEACHER_BASE_URL=https://.../v1 TEACHER_MODEL=... TEACHER_API_KEY=...
    python -m datagen.teacher --per-persona 6 --out data/complaints.jsonl

Local teacher used so far (decision D-001 in the lab notes): qwen3:14b (Apache-2.0) on the
home GPU (RTX 5070) through Ollama, no key, reasoning off:

    TEACHER_BASE_URL=http://gpu-host.lan:11434/v1 TEACHER_MODEL=qwen3:14b \
    TEACHER_API_KEY=ollama TEACHER_EXTRA='{"reasoning_effort": "none"}' \
    python -m datagen.teacher --per-persona 6 --out data/complaints.jsonl

Check the teacher's license allows using outputs to train other models
(Apache-2.0 / MIT weights are the clean choice).
"""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

import yaml

from chirone.catalog import Catalog
from chirone.llm import OpenAICompat

HERE = Path(__file__).parent


def parse_list(text: str) -> list[str]:
    t = text.strip()
    t = t[t.find("["): t.rfind("]") + 1]
    items = json.loads(t)
    return [s.strip() for s in items if isinstance(s, str) and 2 <= len(s.strip()) <= 400]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=6)
    ap.add_argument("--faults", help="comma-separated (default: all)")
    ap.add_argument("--out", default="data/complaints.jsonl")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--lang", default="it", choices=["it", "en"],
                    help="language of the complaints (en: prompts/complaints_en.md, personas_en.yaml)")
    a = ap.parse_args()

    random.seed(a.seed)
    cat = Catalog()
    teacher = OpenAICompat(os.environ["TEACHER_BASE_URL"], os.environ["TEACHER_MODEL"], os.environ["TEACHER_API_KEY"],
                           extra=json.loads(os.environ.get("TEACHER_EXTRA", "{}")))
    sfx = "" if a.lang == "it" else f"_{a.lang}"
    template = (HERE / f"prompts/complaints{sfx}.md").read_text(encoding="utf-8")
    personas = yaml.safe_load((HERE / f"personas{sfx}.yaml").read_text(encoding="utf-8"))
    faults = a.faults.split(",") if a.faults else list(cat.faults)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with out.open("a", encoding="utf-8") as f:
        for fid in faults:
            fault = cat.faults[fid]
            for pi, persona in enumerate(personas):
                prompt = template.format(n=a.per_persona, persona=persona, symptom=fault.symptom_it)
                try:
                    items = parse_list(teacher.chat([{"role": "user", "content": prompt}]))
                except (ValueError, json.JSONDecodeError) as e:
                    print(f"{fid} persona {pi}: unparsable ({e})")
                    continue
                kept = 0
                for c in items:
                    key = c.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    row = {"fault_id": fid, "lang": a.lang, "persona": pi, "complaint": c}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    kept += 1
                print(f"{fid:28} persona {pi}: {kept}")


if __name__ == "__main__":
    main()
