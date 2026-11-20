from types import SimpleNamespace

from chirone import cli


def test_chat_record_keeps_what_the_tester_review_needs():
    d = SimpleNamespace(category="audio", action={"fix_id": "audio.unmute"}, seconds=12.345)
    o = SimpleNamespace(status="done")
    r = cli.chat_record("non sento niente", d, o, "")
    assert r["complaint"] == "non sento niente" and r["category"] == "audio"
    assert r["action"] == {"fix_id": "audio.unmute"} and r["seconds"] == 12.3
    assert r["status"] == "done" and r["error"] is None


def test_chat_record_on_model_error():
    r = cli.chat_record("boh", None, None, "model error: timeout")
    assert r["category"] is None and r["error"] == "model error: timeout"


def test_chat_quits_on_eof(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(EOFError))
    assert cli.main(["chat"]) == 0
    assert "chirone" in capsys.readouterr().out
