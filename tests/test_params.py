import pytest

from chirone.catalog import Catalog
from chirone.executor import ActionError, resolve
from chirone.runner import render_argv


@pytest.fixture(scope="module")
def cat():
    return Catalog()


@pytest.mark.parametrize("bad", ["; rm -rf /", "--help", "a/../b", "x\ny", "$(id)", "`id`", ""])
def test_printer_param_rejects_injection(cat, bad):
    with pytest.raises(ActionError):
        resolve(cat, {"fix_id": "print.clear_queue", "params": {"printer": bad}})


def test_enum_rejects_unknown_service(cat):
    with pytest.raises(ActionError):
        resolve(cat, {"fix_id": "svc.restart", "params": {"service": "sshd"}})


def test_fix_not_allowed_in_category(cat):
    with pytest.raises(ActionError):
        resolve(cat, {"fix_id": "audio.unmute", "params": {}}, category="printing")


def test_int_bounds_and_default(cat):
    _, p = resolve(cat, {"fix_id": "audio.set_volume", "params": {}})
    assert p == {"percent": "60"}
    with pytest.raises(ActionError):
        resolve(cat, {"fix_id": "audio.set_volume", "params": {"percent": 500}})
    with pytest.raises(ActionError):
        resolve(cat, {"fix_id": "proc.terminate_user_process", "params": {"pid": 1}})


def test_render_never_expands_home_for_root():
    with pytest.raises(ValueError):
        render_argv(["rm", "~/x"], {}, allow_home=False)


def test_connection_names_with_spaces_are_fine(cat):
    _, p = resolve(cat, {"fix_id": "dns.reset_to_auto", "params": {"connection": "Connessione via cavo 1"}})
    assert p["connection"] == "Connessione via cavo 1"
