"""Regression tests for the issues found in the first review (2026-11-07)."""
from pathlib import Path

import pytest

from chirone import config, executor
from chirone.catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cat():
    return Catalog()


# --- 1. root helper must not import from the caller's cwd -------------------
@pytest.mark.parametrize("path", ["deploy/install.sh", "lab/ansible/setup.yml"])
def test_root_helper_wrapper_runs_python_isolated(path):
    """`python -m` puts the cwd on sys.path and sudo keeps the cwd: without -I a
    ~/chirone/roothelper.py planted by any user process would run as root."""
    text = (ROOT / path).read_text()
    assert "python -m chirone.roothelper" not in text
    assert "python -I -m chirone.roothelper" in text


# --- 2. escalate.human must not claim a summary it did not save --------------
CONTEXT = {"complaint": "non salva niente", "category": "system", "diagnostics": "[root_mount rc=0]\n/dev/sda1 ext4 ro"}


def _escalate(cat, monkeypatch, state_dir):
    monkeypatch.setattr(config, "STATE_DIR", state_dir)
    pb, params = executor.resolve(cat, {"fix_id": "escalate.human", "params": {"reason": "disk_failure_suspected"}})
    return executor.execute(cat, pb, params, confirm=lambda p: True, lang="it", confidence="high", context=CONTEXT)


def test_escalate_saves_summary_with_complaint_and_diagnostics(cat, monkeypatch, tmp_path):
    o = _escalate(cat, monkeypatch, tmp_path)
    files = list(tmp_path.glob("riepilogo-*.txt"))
    assert o.status == "info" and len(files) == 1
    text = files[0].read_text()
    assert "non salva niente" in text and "/dev/sda1 ext4 ro" in text and "disk_failure_suspected" in text
    assert str(files[0]) in o.message


def test_escalate_on_readonly_disk_shows_summary_instead(cat, monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    o = _escalate(cat, monkeypatch, blocker / "state")  # mkdir under a file -> OSError
    assert "Ho salvato" not in o.message
    assert "Non sono riuscito a salvare" in o.message and "/dev/sda1 ext4 ro" in o.message


# --- 3. low confidence forces confirmation even on confirm: false ------------
@pytest.mark.parametrize("confidence,asked", [("high", False), ("medium", True), ("low", True)])
def test_confidence_gates_unconfirmed_playbooks(cat, monkeypatch, confidence, asked):
    calls = []
    monkeypatch.setattr(executor, "run_checks", lambda *a, **k: (True, []))
    monkeypatch.setattr(executor, "run_step", lambda *a: (0, ""))
    monkeypatch.setattr(executor, "_log", lambda o: o)
    pb, params = executor.resolve(cat, {"fix_id": "audio.unmute", "params": {}})
    assert not pb.confirm
    o = executor.execute(cat, pb, params, confirm=lambda p: calls.append(p) or False, confidence=confidence)
    assert bool(calls) is asked
    assert o.status == ("declined" if asked else "done")


# --- 4. probes with side effects are declared, and the set is pinned ---------
def test_only_declared_probes_have_side_effects(cat):
    assert {p.id for p in cat.probes.values() if p.side_effect} == {"apt_update"}
