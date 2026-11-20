"""Prompt layout matters for speed on old CPUs: llama.cpp reuses the longest
cached prefix, so the part that is stable on a PC must come first."""
from chirone.prompts import step2_messages


def test_step2_complaint_is_last_so_diagnostics_are_a_cacheable_prefix():
    diag = "[apps_installed rc=0]\ngalculator: Galculator\nthunar: Thunar"
    a = step2_messages("aprimi la calcolatrice", "actions", diag)[1]["content"]
    b = step2_messages("voglio vedere le foto", "actions", diag)[1]["content"]
    prefix = f"category: actions\ndiagnostics:\n{diag}\ncomplaint: "
    assert a.startswith(prefix) and b.startswith(prefix)
    assert a.endswith("aprimi la calcolatrice")
