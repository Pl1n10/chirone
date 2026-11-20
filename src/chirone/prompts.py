"""Prompt formatting. Used verbatim at inference AND when building the
dataset: any change here requires retraining.

Kept deliberately terse: on a 2008 CPU without AVX every prompt token costs
real time. The system prompts are constant so llama.cpp can cache them.
"""
from __future__ import annotations

SYSTEM_STEP1 = (
    "You route PC support requests from non-technical users of a Debian-family "
    "Linux desktop. Read the complaint (Italian or English) and answer with the "
    "category as JSON."
)

SYSTEM_STEP2 = (
    "You fix Debian-family Linux desktops for non-technical users. Given the "
    "complaint and diagnostics, choose exactly one fix and its params as JSON. "
    "Take param values from the diagnostics. If nothing is broken choose "
    "noop.no_issue_found; if it looks like hardware or is unsafe choose "
    "escalate.human; if it is not about this PC or asks for something no fix "
    "does, choose info.what_i_can_do."
)


def step1_messages(complaint: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_STEP1},
        {"role": "user", "content": complaint.strip()},
    ]


def step2_messages(complaint: str, category: str, diagnostics: str) -> list[dict]:
    # Complaint last: everything before it is a prefix llama.cpp can reuse from
    # its prompt cache. For `actions` the diagnostics (installed programs) do
    # not change on a PC, so after the first request only the person's words
    # cost prefill time on an old CPU.
    user = f"category: {category}\ndiagnostics:\n{diagnostics}\ncomplaint: {complaint.strip()}"
    return [
        {"role": "system", "content": SYSTEM_STEP2},
        {"role": "user", "content": user},
    ]
