"""chirone CLI.

  chirone ask "non stampa più niente"      full loop against the local model
  chirone chat                             the same, in a loop, for a desktop icon
  chirone probe --category printing --json collect a probe bundle (lab uses this)
  chirone apply print.clear_queue printer=HP --yes --json
  chirone validate | schema | doc | sudoers | list
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import config
from .catalog import Catalog


def _confirm(plan: str) -> bool:
    print(plan)
    try:
        return input("Procedo? [s/N] ").strip().lower() in {"s", "si", "sì", "y", "yes"}
    except EOFError:
        return False


def cmd_ask(cat: Catalog, a) -> int:
    from .agent import handle
    from .llm import LlamaCpp

    d, outcome, err = handle(cat, LlamaCpp(a.llm), a.complaint, _confirm, lang=a.lang, assume_yes=a.yes)
    if a.verbose and d:
        print(f"[category={d.category} action={json.dumps(d.action)} {d.seconds:.1f}s]", file=sys.stderr)
    if err:
        print(err, file=sys.stderr)
        return 1
    if outcome.message:
        print(outcome.message)
    return 0 if outcome.status in {"done", "info", "declined"} else 1


CHAT_INTRO = {
    "it": "Ciao, sono chirone. Scrivimi cosa non va nel computer, o cosa vuoi fare.\n"
          "Per esempio: \"non sento niente\" oppure \"aprimi la calcolatrice\".\n"
          "Per uscire chiudi la finestra.",
    "en": "Hi, I'm chirone. Tell me what's wrong with the computer, or what you want to do.\n"
          "For example: \"I can't hear anything\" or \"open the calculator\".\n"
          "Close the window to quit.",
}
CHAT_PROMPT = {"it": "\nScrivi qui: ", "en": "\nType here: "}
CHAT_WAIT = {"it": "Ci penso un momento...", "en": "Let me think..."}


def chat_record(complaint: str, d, outcome, err: str) -> dict:
    """One chat turn as the local log keeps it (never leaves the PC)."""
    import time

    return {
        "ts": int(time.time()),
        "complaint": complaint,
        "category": d.category if d else None,
        "action": d.action if d else None,
        "seconds": round(d.seconds, 1) if d else None,
        "status": outcome.status if outcome else None,
        "error": err or None,
    }


def cmd_chat(cat: Catalog, a) -> int:
    from .agent import handle
    from .llm import LlamaCpp

    llm = LlamaCpp(a.llm)
    lang = a.lang if a.lang in CHAT_INTRO else "it"
    print(CHAT_INTRO[lang])
    while True:
        try:
            complaint = input(CHAT_PROMPT[lang]).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not complaint:
            continue
        print(CHAT_WAIT[lang], flush=True)
        d, outcome, err = handle(cat, llm, complaint, _confirm, lang=a.lang)
        if err:
            print("Qualcosa non ha funzionato da parte mia. Riprova tra poco." if lang == "it"
                  else "Something went wrong on my side. Please try again shortly.")
        elif outcome and outcome.message:
            print(outcome.message)
        try:
            config.STATE_DIR.mkdir(parents=True, exist_ok=True)
            with open(config.STATE_DIR / "chat.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(chat_record(complaint, d, outcome, err), ensure_ascii=False) + "\n")
        except OSError:
            pass  # read-only disk: the person still gets the answer


def cmd_close_app(cat: Catalog, a) -> int:
    """Step of app.close: SIGTERM to the program's processes, wait until they are gone."""
    import os
    import signal
    import time

    from .builtins import app_pids

    pids = app_pids(a.app)
    if not pids:
        print(f"{a.app}: not running")
        return 1
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(30):
        if not app_pids(a.app):
            return 0
        time.sleep(0.5)
    print(f"{a.app}: still running (waiting for the person?)")
    return 1


def cmd_probe(cat: Catalog, a) -> int:
    from .probes import collect, diagnostics_block, run_probe, to_json

    if a.category:
        results = collect(cat, a.category)
    else:
        ids = list(cat.probes) if a.all else a.ids
        results = [run_probe(cat, i) for i in ids if not cat.probes[i].params]
    print(to_json(results) if a.json else diagnostics_block(results, budget=10**6))
    return 0


def cmd_apply(cat: Catalog, a) -> int:
    from .executor import ActionError, execute, resolve

    raw = {}
    for kv in a.params:
        k, _, v = kv.partition("=")
        raw[k] = v
    try:
        pb, params = resolve(cat, {"fix_id": a.fix_id, "params": raw})
    except ActionError as e:
        print(f"rejected: {e}", file=sys.stderr)
        return 2
    o = execute(cat, pb, params, _confirm, lang=a.lang, assume_yes=a.yes)
    print(json.dumps(asdict(o), ensure_ascii=False) if a.json else o.message)
    return 0 if o.status in {"done", "info"} else 1


def cmd_validate(cat: Catalog, a) -> int:
    errs = cat.validate()
    for e in errs:
        print(f"ERROR {e}")
    print(
        f"{len(cat.probes)} probes, {len(cat.playbooks)} playbooks, "
        f"{len(cat.categories)} categories, {len(cat.faults)} faults: "
        + ("OK" if not errs else f"{len(errs)} problems")
    )
    return 1 if errs else 0


def cmd_schema(cat: Catalog, a) -> int:
    from .schemas import step1_schema, step2_schema

    s = step1_schema(cat) if a.step == 1 else step2_schema(cat, a.category)
    print(json.dumps(s, indent=2))
    return 0


def cmd_doc(cat: Catalog, a) -> int:
    out = ["# Catalog", "", "Generated by `chirone doc`. Do not edit by hand.", ""]
    out += ["## Categories", "", "| id | probes | fixes |", "|---|---|---|"]
    for c in cat.categories.values():
        out.append(f"| {c.id} | {', '.join(c.probes)} | {', '.join(c.fixes) or '-'} |")
    out += ["", f"Global fixes (every category): {', '.join(cat.global_fixes)}", ""]
    effects = [p for p in cat.probes.values() if p.side_effect]
    if effects:
        out += ["## Probes that are not read-only", "", "| probe | side effect |", "|---|---|"]
        out += [f"| `{p.id}` | {p.side_effect} |" for p in effects]
        out.append("")
    out += ["## Playbooks", "", "| fix_id | risk | root | confirm | params | title |", "|---|---|---|---|---|---|"]
    for p in cat.playbooks.values():
        params = ", ".join(f"{n}:{s.type}" for n, s in p.params.items()) or "-"
        root, confirm = ("yes" if p.root else "no"), ("yes" if p.confirm else "no")
        out.append(f"| `{p.id}` | {p.risk} | {root} | {confirm} | {params} | {p.title} |")
    out += ["", "## Lab faults", "", "| fault | category | expected fix | fidelity | run as |", "|---|---|---|---|---|"]
    for f in cat.faults.values():
        out.append(f"| `{f.id}` | {f.category} | `{f.expected.fix_id}` | {f.fidelity} | {f.run_as} |")
    print("\n".join(out))
    return 0


def cmd_sudoers(cat: Catalog, a) -> int:
    print(f"# /etc/sudoers.d/chirone  (validate with: visudo -cf <file>)\n"
          f"%chirone ALL=(root) NOPASSWD: {config.HELPER}")
    return 0


def cmd_list(cat: Catalog, a) -> int:
    for c in cat.categories.values():
        print(f"{c.id}: {', '.join(cat.fixes_for(c.id))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="chirone")
    p.add_argument("--lang", default=config.LANG)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ask")
    s.add_argument("complaint")
    s.add_argument("--llm", default=config.LLM_URL)
    s.add_argument("--yes", action="store_true")
    s.add_argument("-v", "--verbose", action="store_true")

    s = sub.add_parser("chat")
    s.add_argument("--llm", default=config.LLM_URL)

    s = sub.add_parser("close-app")
    s.add_argument("app", help="desktop id, e.g. firefox-esr")

    s = sub.add_parser("probe")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--category")
    g.add_argument("--all", action="store_true")
    g.add_argument("--ids", nargs="+")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("apply")
    s.add_argument("fix_id")
    s.add_argument("params", nargs="*", help="name=value")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--json", action="store_true")

    sub.add_parser("validate")
    s = sub.add_parser("schema")
    s.add_argument("--step", type=int, choices=[1, 2], default=2)
    s.add_argument("--category", default="network")
    sub.add_parser("doc")
    sub.add_parser("sudoers")
    sub.add_parser("list")

    a = p.parse_args(argv)
    cat = Catalog()
    handler = globals()[f"cmd_{a.cmd.replace('-', '_')}"]
    return handler(cat, a)


if __name__ == "__main__":
    sys.exit(main())
