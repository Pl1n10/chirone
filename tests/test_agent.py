"""Agent loop with a fake model and fake probes: wiring, not intelligence."""
from chirone import agent, executor, probes
from chirone.catalog import Catalog
from chirone.llm import Completion
from chirone.probes import ProbeResult


class FakeLLM:
    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def complete_json(self, messages, schema, max_tokens=64):
        self.prompts.append(messages)
        return Completion(self.answers.pop(0), "", 0.01)


def test_noop_flow(monkeypatch):
    cat = Catalog()
    monkeypatch.setattr(agent, "collect", lambda c, cat_id: [ProbeResult("os_release", 0, "ID=debian")])
    monkeypatch.setattr(executor, "_log", lambda o: o)
    llm = FakeLLM([{"category": "other"}, {"fix_id": "noop.no_issue_found", "params": {}, "confidence": "low"}])
    d, outcome, err = agent.handle(cat, llm, "come ingrandisco le scritte?", confirm=lambda p: True)
    assert not err and d.category == "other"
    assert outcome.status == "info"
    assert "[os_release rc=0]" in llm.prompts[1][1]["content"]


def test_rejects_fix_outside_category(monkeypatch):
    cat = Catalog()
    monkeypatch.setattr(agent, "collect", lambda c, cat_id: [])
    llm = FakeLLM([{"category": "printing"}, {"fix_id": "audio.unmute", "params": {}, "confidence": "high"}])
    d, outcome, err = agent.handle(cat, llm, "non stampa", confirm=lambda p: True)
    assert outcome is None and "not allowed" in err


def test_declined_runs_nothing(monkeypatch):
    cat = Catalog()
    ran = []
    monkeypatch.setattr(agent, "collect", lambda c, cat_id: [])
    monkeypatch.setattr(executor, "run_checks", lambda *a, **k: (True, []))
    monkeypatch.setattr(executor, "run_step", lambda *a: ran.append(a) or (0, ""))
    monkeypatch.setattr(executor, "_log", lambda o: o)
    llm = FakeLLM([{"category": "storage"}, {"fix_id": "disk.empty_trash", "params": {}, "confidence": "high"}])
    _, outcome, _ = agent.handle(cat, llm, "disco pieno", confirm=lambda p: False)
    assert outcome.status == "declined" and ran == []


def test_compact_filters_dedupes_and_caps():
    out = probes.compact("a\nkeep 1\nkeep 1\nkeep 2\nkeep 3\nb", keep="^keep", max_lines=2)
    assert out == "keep 1\nkeep 2\n... (+1 lines)"


def test_compact_tail_keeps_newest_lines():
    out = probes.compact("boot 1\nboot 2\nboot 3\nfault", keep=None, max_lines=2, tail=True)
    assert out == "... (+2 earlier lines)\nboot 3\nfault"


def test_kernel_errors_keeps_newest_lines():
    # F-017: the fault's lines come after the boot noise, never cut them
    assert Catalog().probes["kernel_errors"].tail


def test_bare_replies_never_reach_the_model():
    from chirone.agent import is_bare_reply

    assert all(is_bare_reply(t) for t in ["s", "Sì!", "ok", "no.", "?", "  ", "grazie"])
    assert not is_bare_reply("non sento niente")


def test_web_search_only_with_the_persons_words():
    from chirone.agent import query_from_person

    act = {"fix_id": "web.search", "params": {"query": "speci di questo computer"}}
    assert not query_from_person(act, "mi elenchi le specs di questo computer?")
    act["params"]["query"] = "specs di questo computer"
    assert query_from_person(act, "mi elenchi le specs di questo computer?")
    assert query_from_person({"fix_id": "app.open", "params": {"app": "x"}}, "ciao")
