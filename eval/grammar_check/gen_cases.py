"""Emit cases for test-chirone: every allowed fix must be accepted by the
grammar llama.cpp compiles from our schema; injections and out-of-category
fixes must be rejected.

    python eval/grammar_check/gen_cases.py > /tmp/cases.json
    llama.cpp/build/bin/test-chirone /tmp/cases.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from chirone.catalog import Catalog  # noqa: E402
from chirone.schemas import step1_schema, step2_schema, step2_target  # noqa: E402

SAMPLE = {"iface": "enp1s0", "connection": "Wired connection 1", "file": "vecchio-programma.list",
          "printer": "HP_LaserJet", "profile": "a1b2c3.default-esr", "pid": 4242,
          "sink": "alsa_output.pci-0000_00_1b.0.analog-stereo", "percent": 60,
          "app": "org.gnome.Calculator", "query": "orari farmacia di turno, è aperta domenica?",
          "minutes": 30, "text": "prendere la pastiglia della pressione"}
BAD = [("print.clear_queue", {"printer": "; rm -rf /"}), ("print.clear_queue", {"printer": "-x"}),
       ("svc.restart", {"service": "sshd"}), ("audio.set_volume", {"percent": 500}),
       ("proc.terminate_user_process", {"pid": 1}), ("app.firefox_clear_stale_lock", {"profile": "../etc"}),
       ("apt.disable_source", {"file": "x.txt"}),
       ("app.open", {"app": "../../bin/sh"}), ("app.open", {"app": "-e"}),
       ("web.search", {"query": "-profile /tmp/x", "browser": "firefox"}),
       ("web.search", {"query": 'a" --new-instance', "browser": "firefox"}),
       ("web.search", {"query": "riga\nnuova", "browser": "firefox"}),
       ("web.search", {"query": "x" * 121, "browser": "firefox"}),
       ("web.search", {"query": "ciao", "browser": "chromium"}),
       ("web.open_site", {"site": "https://evil.example", "browser": "firefox"}),
       ("files.open_folder", {"folder": "/etc"}), ("files.open_folder", {"folder": "xdg:PICTURES"}),
       ("reminder.set", {"minutes": 0, "text": "x"}), ("reminder.set", {"minutes": 30, "text": "-x"})]

cat = Catalog()
cases = [{"name": "step1", "schema": step1_schema(cat), "pass": ['{"category": "audio"}'],
          "fail": ['{"category": "cooking"}']}]
for c in cat.categories:
    allowed = cat.fixes_for(c)
    passes = []
    for f in allowed:
        params = {n: (s.values[0] if s.type == "enum" else SAMPLE[n]) for n, s in cat.playbooks[f].params.items()}
        passes += [json.dumps(step2_target(f, params), ensure_ascii=False),
                   json.dumps(step2_target(f, params), separators=(",", ":"), ensure_ascii=False)]
    fails = [json.dumps(step2_target(f, p)) for f, p in BAD if f in allowed]
    fails += [json.dumps(step2_target(f, {})) for f in cat.playbooks if f not in allowed][:1]
    cases.append({"name": f"step2_{c}", "schema": step2_schema(cat, c), "pass": passes, "fail": fails})
print(json.dumps(cases))
