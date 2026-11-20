"""Execute a playbook chosen by the model.

The model never produces commands. It produces {fix_id, params}; this module
re-validates both against the catalog, checks preconditions, asks the person,
runs the fixed steps, verifies the result and logs everything locally.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from . import config
from .catalog import Catalog, ParamError, Playbook
from .probes import run_checks
from .runner import is_root, render_argv, run, run_via_helper


class ActionError(ValueError):
    pass


@dataclass
class Outcome:
    fix_id: str
    params: dict
    status: str  # done | verified_failed | declined | precondition_failed | step_failed | info
    message: str
    notes: list[str] = field(default_factory=list)
    confidence: str = "high"
    # complaint / category / diagnostics, when the action came from the model
    context: dict = field(default_factory=dict)


def resolve(cat: Catalog, action: dict, category: str | None = None) -> tuple[Playbook, dict[str, str]]:
    fix_id = action.get("fix_id")
    if fix_id not in cat.playbooks:
        raise ActionError(f"unknown fix_id {fix_id!r}")
    if category is not None and fix_id not in cat.fixes_for(category):
        raise ActionError(f"{fix_id} not allowed for category {category}")
    pb = cat.playbooks[fix_id]
    try:
        return pb, pb.coerce_params(action.get("params"))
    except ParamError as e:
        raise ActionError(str(e)) from e


def message(pb: Playbook, key: str, params: dict[str, str], lang: str = config.LANG, **extra: str) -> str:
    msgs = pb.messages.get(lang) or pb.messages["en"]
    return getattr(msgs, key).format(**params, **extra)


_SUMMARY_LABELS = {
    "it": ("Riepilogo di chirone", "Data", "Cosa ha scritto la persona", "Categoria",
           "Decisione", "Diagnostica raccolta"),
    "en": ("chirone summary", "Date", "What the person wrote", "Category",
           "Decision", "Diagnostics collected"),
}


def handover_summary(pb: Playbook, params: dict[str, str], confidence: str, context: dict,
                     lang: str = config.LANG, now: float | None = None) -> str:
    """Plain-text summary for the trusted person who will look at the PC."""
    title, date, wrote, category, decision, diag = _SUMMARY_LABELS.get(lang, _SUMMARY_LABELS["en"])
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    reason = ", ".join(f"{k}={v}" for k, v in params.items()) or "-"
    return "\n".join([
        f"== {title} ==",
        f"{date}: {when}",
        f"{wrote}: {context.get('complaint', '-')}",
        f"{category}: {context.get('category', '-')}",
        f"{decision}: {pb.id} ({reason}), confidence={confidence}",
        "",
        f"-- {diag} --",
        context.get("diagnostics") or "-",
        "",
    ])


def _handover(pb: Playbook, params: dict[str, str], confidence: str, context: dict, lang: str) -> tuple[str, list[str]]:
    """Write the summary and return the message that tells the truth about it.

    If the disk is read-only (one of the reasons to escalate) the summary
    cannot be saved: it is shown on screen instead, never claimed as saved.
    """
    text = handover_summary(pb, params, confidence, context, lang)
    plan = message(pb, "plan", params, lang)
    path = config.STATE_DIR / f"riepilogo-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        return f"{plan}\n{message(pb, 'failure', params, lang)}\n\n{text}", [f"summary not saved: {e}"]
    return f"{plan}\n{message(pb, 'success', params, lang, summary_path=str(path))}", [f"summary {path}"]


def run_step(pb: Playbook, index: int, params: dict[str, str]) -> tuple[int, str]:
    step = pb.steps[index]
    if step.wait is not None:
        time.sleep(step.wait)
        return 0, f"waited {step.wait}s"
    if pb.root and not is_root():
        res = run_via_helper(["step", pb.id, str(index), json.dumps(params)], step.timeout)
    else:
        try:
            argv = render_argv(step.argv or [], pb.command_values(params), allow_home=not pb.root)
        except ValueError as e:
            return 1, str(e)
        res = run(argv, timeout=step.timeout, env=step.env, detach=step.detach)
    return res.rc, res.output


def execute(
    cat: Catalog,
    pb: Playbook,
    params: dict[str, str],
    confirm: Callable[[str], bool],
    lang: str = config.LANG,
    assume_yes: bool = False,
    confidence: str = "high",
    context: dict | None = None,
) -> Outcome:
    context = context or {}

    def out(status: str, msg: str, notes: list[str] | None = None) -> Outcome:
        return _log(Outcome(pb.id, params, status, msg, notes or [], confidence, context))

    plan = message(pb, "plan", params, lang)
    if pb.handover:
        msg, notes = _handover(pb, params, confidence, context, lang)
        return out("info", msg, notes)
    if not pb.steps:  # noop: information only
        return out("info", plan)
    ok, notes = run_checks(cat, pb.preconditions, params)
    if not ok:
        msgs = pb.messages.get(lang) or pb.messages["en"]
        key = "not_needed" if msgs.not_needed else "failure"
        return out("precondition_failed", message(pb, key, params, lang), notes)
    # Playbooks that normally skip confirmation still ask when the model
    # is not sure: a harmless fix applied for the wrong reason is still wrong.
    needs_confirm = pb.confirm or confidence != "high"
    if needs_confirm and not assume_yes and not confirm(plan):
        return out("declined", "", notes)
    if not needs_confirm:
        print(plan)
    for i in range(len(pb.steps)):
        rc, step_out = run_step(pb, i, params)
        notes.append(f"step {i} rc={rc} {step_out[-300:]}")
        if rc != 0:
            return out("step_failed", message(pb, "failure", params, lang), notes)
    ok, vnotes = run_checks(cat, pb.verify, params)
    notes += vnotes
    status, key = ("done", "success") if ok else ("verified_failed", "failure")
    return out(status, message(pb, key, params, lang), notes)


def _log(o: Outcome) -> Outcome:
    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.STATE_DIR / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), **asdict(o)}, ensure_ascii=False) + "\n")
    except OSError:
        pass  # read-only filesystem is itself a fault we must survive
    return o
