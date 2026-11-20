"""The two-step loop.

  1. complaint -> category            (model, tiny prompt, ~5 tokens out)
  2. category  -> probe bundle        (code, deterministic)
  3. complaint + diagnostics -> fix   (model, constrained, ~20 tokens out)
  4. fix -> confirm -> steps -> verify (code, from the catalog)
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from . import config
from .catalog import Catalog
from .executor import ActionError, Outcome, execute, resolve
from .llm import LLMError
from .probes import ProbeResult, collect, diagnostics_block
from .prompts import step1_messages, step2_messages
from .schemas import step1_schema, step2_schema

FALLBACK = "info.what_i_can_do"
# A reply to a question chirone never asked: no meaning on its own, never sent
# to the model (it read "s" as a request and opened the settings, F-018).
BARE_REPLIES = {"s", "si", "sì", "no", "ok", "okay", "va bene", "y", "yes", "n", "boh", "?", "grazie",
                "thanks", "thank you"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def is_bare_reply(complaint: str) -> bool:
    t = complaint.strip().lower().strip(".!? ")
    return t in BARE_REPLIES or not _words(t)


def query_from_person(action: dict, complaint: str) -> bool:
    """A web search only with words the person wrote (the rule of every training label)."""
    if action.get("fix_id") != "web.search":
        return True
    return _words(str((action.get("params") or {}).get("query", ""))) <= _words(complaint)


@dataclass
class Diagnosis:
    category: str
    probes: list[ProbeResult]
    action: dict
    seconds: float


def diagnose(cat: Catalog, llm, complaint: str) -> Diagnosis:
    c1 = llm.complete_json(step1_messages(complaint), step1_schema(cat), max_tokens=16)
    category = c1.data["category"]
    results = collect(cat, category)
    c2 = llm.complete_json(
        step2_messages(complaint, category, diagnostics_block(results)),
        step2_schema(cat, category),
        max_tokens=64,
    )
    return Diagnosis(category, results, c2.data, c1.seconds + c2.seconds)


def handle(
    cat: Catalog,
    llm,
    complaint: str,
    confirm: Callable[[str], bool],
    lang: str = config.LANG,
    assume_yes: bool = False,
) -> tuple[Diagnosis | None, Outcome | None, str]:
    if is_bare_reply(complaint):
        pb = cat.playbooks[FALLBACK]
        return None, execute(cat, pb, {}, confirm, lang=lang), ""
    try:
        d = diagnose(cat, llm, complaint)
    except LLMError as e:
        return None, None, f"model error: {e}"
    if not query_from_person(d.action, complaint):
        d.action = {"fix_id": FALLBACK, "params": {}, "confidence": "low",
                    "rejected": d.action}
    try:
        pb, params = resolve(cat, d.action, d.category)
    except ActionError as e:
        return d, None, f"rejected action: {e}"
    context = {"complaint": complaint, "category": d.category, "diagnostics": diagnostics_block(d.probes)}
    outcome = execute(
        cat, pb, params, confirm, lang=lang, assume_yes=assume_yes,
        confidence=d.action.get("confidence", "low"), context=context,
    )
    return d, outcome, ""
