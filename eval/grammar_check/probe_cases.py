"""Differential probe: Python jsonschema verdict vs llama.cpp grammar on edge cases.

"pass"/"fail" are what jsonschema says; test-chirone reports every disagreement.
SHOULD PASS = grammar stricter than Python (safe). SHOULD FAIL = grammar looser (bug).
The last case is an inverted control and must report exactly 2 mismatches.

    .venv/bin/python eval/grammar_check/probe_cases.py > /tmp/probe.json
    ~/src/llama.cpp/build/bin/test-chirone /tmp/probe.json
"""
import json
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from chirone.catalog import Catalog  # noqa: E402
from chirone.schemas import step1_schema, step2_schema  # noqa: E402


def t(fix_id, params, confidence="high"):
    return json.dumps({"fix_id": fix_id, "params": params, "confidence": confidence})


def raw(params_json, fix_id="audio.set_volume"):
    return f'{{"fix_id": "{fix_id}", "params": {params_json}, "confidence": "high"}}'


cat = Catalog()
probe = {
    "audio": [t("audio.set_volume", {"percent": v}) for v in [9, 10, 100, 101, 0, -5, 55]]
    + [raw('{"percent": 050}'), raw('{"percent": 50.0}'), raw('{"percent": 1e2}'), raw('{"percent": "50"}'),
       t("audio.set_default_sink", {"sink": "a" * 128}), t("audio.set_default_sink", {"sink": "a" * 129}),
       t("audio.set_default_sink", {"sink": "a\nb"}), t("audio.set_default_sink", {"sink": "a b"}),
       t("audio.unmute", {}, "maybe"),
       '{"fix_id": "audio.unmute", "params": {}}',
       '{"params": {}, "fix_id": "audio.unmute", "confidence": "high"}',
       '{"fix_id": "audio.unmute", "params": {}, "confidence": "high", "extra": 1}',
       '{"fix_id": "audio.unmute", "params": {"x": 1}, "confidence": "high"}',
       '{"fix_id": "audio.unmute", "params": {}, "confidence": "high", "confidence": "low"}',
       '{"fix_id":"audio.unmute","params":{},"confidence":"low"}',
       '{ "fix_id" : "audio.unmute" , "params" : { } , "confidence" : "medium" }',
       raw('{"sink": "a\\u002eb"}', "audio.set_default_sink"),
       raw('{"sink": "a\\nb"}', "audio.set_default_sink"),
       '{"fix_id": "audio.unmute", "params": {}, "confidence": "high"} trailing'],
    "apps": [t("proc.terminate_user_process", {"pid": v}) for v in [1, 2, 4194304, 4194305, 99999999]]
    + [t("app.firefox_clear_stale_lock", {"profile": p})
       for p in ["..", "a/../b", "a..", ".a", "a" * 64, "a" * 65, "é"]],
    "network": [t("net.connect_device", {"iface": i}) for i in ["a" * 15, "a" * 16, "eth0:1", "-eth", "wlan0"]]
    + [t("dns.reset_to_auto", {"connection": c})
       for c in ["Wired connection 1", " x", "x;y", "Rete (casa)", "a$(id)"]]
    + [t("svc.restart", {"service": s}) for s in ["cups", "NetworkManager", "networkmanager"]]
    + [t("escalate.human", {"reason": "needs_password"}), t("escalate.human", {"reason": "x"})],
    "updates": [t("apt.disable_source", {"file": f})
                for f in ["a.list", "a.sources", ".list", "a.list.bak", "a/b.list", "a..list",
                          "x" * 81 + ".list", "x" * 82 + ".list"]],
}

cases = []
for category, strs in probe.items():
    schema = step2_schema(cat, category)
    ok, ko = [], []
    for s in strs:
        try:
            jsonschema.validate(json.loads(s), schema)
        except (json.JSONDecodeError, jsonschema.ValidationError):
            ko.append(s)
        else:
            ok.append(s)
    cases.append({"name": f"probe_{category}", "schema": schema, "pass": ok, "fail": ko})

s1 = step1_schema(cat)
cases.append({"name": "probe_step1", "schema": s1,
              "pass": ['{"category":"other"}', '{ "category" : "network" }'],
              "fail": ['{"category": "audio", "x": 1}', "{}", '{"category": "Audio"}',
                       '{"category": "audio"}\n\n{"category": "audio"}']})
# Inverted control: proves the harness reports mismatches at all.
cases.append({"name": "control_inverted", "schema": s1,
              "pass": ['{"category": "cooking"}'], "fail": ['{"category": "audio"}']})
print(json.dumps(cases))
