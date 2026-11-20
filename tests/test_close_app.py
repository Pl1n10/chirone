import os
from pathlib import Path

from chirone import builtins
from chirone.catalog import Catalog


def _desktop(d: Path, name: str, exec_: str) -> None:
    (d / f"{name}.desktop").write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec={exec_}\n")


def test_desktop_execs_reads_the_program_behind_each_id(tmp_path):
    _desktop(tmp_path, "firefox-esr", "/usr/lib/firefox-esr/firefox-esr %u")
    _desktop(tmp_path, "libreoffice-writer", "libreoffice --writer %U")
    _desktop(tmp_path, "odd", "env GTK_THEME=x mousepad %F")
    ex = builtins.desktop_execs([tmp_path])
    assert ex["firefox-esr"] == {"firefox-esr"}
    assert "soffice.bin" in ex["libreoffice-writer"]  # LibreOffice runs as soffice.bin
    assert ex["odd"] == {"mousepad"}


def test_user_processes_never_include_chirone_itself(tmp_path):
    me = tmp_path / str(os.getpid())
    me.mkdir()
    (me / "comm").write_text("python3\n")
    (me / "cmdline").write_bytes(b"/usr/bin/python3\0-m\0chirone\0")
    other = tmp_path / "99999"
    other.mkdir()
    (other / "comm").write_text("firefox-esr\n")
    (other / "cmdline").write_bytes(b"/usr/lib/firefox-esr/firefox-esr\0")
    procs = builtins.user_processes(tmp_path)
    assert os.getpid() not in procs and procs[99999] == {"firefox-esr"}


def test_user_processes_skip_zombies(tmp_path):
    z = tmp_path / "99998"
    z.mkdir()
    (z / "comm").write_text("firefox-esr\n")
    (z / "cmdline").write_bytes(b"")
    (z / "stat").write_text("99998 (firefox-esr) Z 1012 1499 1499 0 -1\n")
    assert 99998 not in builtins.user_processes(tmp_path)


def test_close_and_restart_are_actions_that_always_ask():
    cat = Catalog()
    assert {"app.close", "system.restart"} <= set(cat.fixes_for("actions"))
    for fid in ("app.close", "system.restart"):
        pb = cat.playbooks[fid]
        assert pb.confirm and not pb.root
    # never a repair the model can pick on its own for a fault
    assert all("system.restart" not in cat.fixes_for(c) for c in cat.categories if c != "actions")


def test_the_desktop_itself_is_never_a_program_to_close(tmp_path):
    _desktop(tmp_path, "panel-preferences", "xfce4-panel --preferences")
    _desktop(tmp_path, "thunar", "thunar %F")
    _desktop(tmp_path, "galculator", "galculator")
    assert set(builtins.desktop_execs([tmp_path])) == {"galculator"}
