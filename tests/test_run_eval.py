"""The harm metric must follow the executor's confirmation rule."""
import importlib.util
from pathlib import Path

from chirone.catalog import Catalog

spec = importlib.util.spec_from_file_location("run_eval", Path(__file__).parents[1] / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)
CAT = Catalog()


def test_groups():
    assert run_eval.group_of({"fault_id": "healthy_negative", "category": "audio"}) == "healthy"
    assert run_eval.group_of({"fault_id": "web.search", "category": "actions"}) == "actions"
    assert run_eval.group_of({"fault_id": "audio_muted", "category": "audio"}) == "repairs"


def test_would_run_unasked():
    silent = next(p.id for p in CAT.playbooks.values() if not p.confirm and p.id not in run_eval.NOT_A_FIX)
    asking = next(p.id for p in CAT.playbooks.values() if p.confirm and p.id not in run_eval.NOT_A_FIX)
    assert run_eval.would_run_unasked(CAT, silent, "high")
    assert not run_eval.would_run_unasked(CAT, silent, "medium")
    assert not run_eval.would_run_unasked(CAT, asking, "high")
    assert not run_eval.would_run_unasked(CAT, "noop.no_issue_found", "high")
