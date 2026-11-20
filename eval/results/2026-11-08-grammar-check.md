# Grammar check — 2026-11-08

Checks that llama.cpp turns the JSON schemas of both steps
(`src/chirone/schemas.py`) into a valid GBNF grammar, and that the grammar
accepts all and only the allowed outputs. No model involved: llama.cpp's
grammar engine is driven directly (`llama_grammar_accept_token`, one
character at a time), so the result does not depend on the GGUF.

- llama.cpp `80d2c0c`, `test-chirone` built from
  `eval/grammar_check/test-chirone.cpp` inside the llama.cpp tree.
- Catalog: 8 categories, 23 playbooks (as of commit `697dc8b`).

## 1. Scaffold cases (`gen_cases.py`)

    .venv/bin/python eval/grammar_check/gen_cases.py > /tmp/cases.json
    ~/src/llama.cpp/build/bin/test-chirone /tmp/cases.json

9 grammars (step 1, plus step 2 for each of the 8 categories), **101 cases**:
83 must be accepted (every allowed fix of the category, pretty and compact
JSON), 18 must be rejected (injections in parameters, enum/range violations,
a fix from another category). **Result: 101/101, `failures: 0`.** Every
grammar converts and builds (271 to 5,517 bytes).

## 2. Differential probe (`probe_cases.py`)

The scaffold cases only use convenient values. The probe compares, on 69 edge
cases, the verdict of `jsonschema` (what `llm.py` uses) with the grammar's:
integer range bounds (`percent` 9/10/100/101, `pid` 1/2/4194304/4194305),
maximum pattern lengths (iface 15/16, sink 128/129, profile 64/65, file
81/82 + `.list`), `..`, `/`, `;`, `$(id)`, newlines, unicode, extra /
duplicate / missing keys, key order, trailing text after the JSON, plus an
inverted control that must fail.

    .venv/bin/python eval/grammar_check/probe_cases.py > /tmp/probe.json
    ~/src/llama.cpp/build/bin/test-chirone /tmp/probe.json

Result: 8 disagreements. Two are the inverted control (expected: it proves
the harness reports failures). The other 6 all go **the safe way**, the
grammar being stricter than Python:

| Input (step 2, `audio`) | jsonschema | grammar |
|---|---|---|
| `"percent": 50.0` and `"percent": 1e2` | accepts (mathematical integer) | rejects |
| keys out of order (`params` before `fix_id`) | accepts | rejects |
| duplicate key (`"confidence"` twice) | accepts (last wins) | rejects |
| `"params" : { }` (empty object with a space inside) | accepts | rejects |
| `.`-style escape in a parameter | accepts | rejects |

**No case where the grammar accepts what Python rejects.** Every injection and
every out-of-range or out-of-pattern value is rejected by both.

## Conclusion

The grammars of both steps load in llama.cpp and constrain the output as
designed; no bug in `schemas.py`. The differences with `jsonschema` only make
the grammar stricter, so they open no hole. The one practical consequence:
training targets must stay canonical JSON (`json.dumps` of `step2_target`,
key order `fix_id` / `params` / `confidence`), as they already are.

Re-run both checks when the catalog changes or llama.cpp is updated
(`test-chirone` lives in the llama.cpp tree and must be rebuilt).
