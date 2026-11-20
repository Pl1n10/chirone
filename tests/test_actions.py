"""Everyday actions: open a program, search the web."""
import subprocess
import sys
import time

import pytest

from chirone.builtins import desktop_apps
from chirone.catalog import Catalog, ParamError
from chirone.runner import run


def _desktop(d, name, body):
    (d / f"{name}.desktop").write_text("[Desktop Entry]\n" + body, encoding="utf-8")


def test_desktop_apps_localized_and_filtered(tmp_path):
    user, system = tmp_path / "user", tmp_path / "sys"
    user.mkdir()
    system.mkdir()
    _desktop(system, "galculator", "Type=Application\nExec=galculator\nName=Galculator\n"
                                   "GenericName=Scientific Calculator\nGenericName[it]=Calcolatrice scientifica\n")
    _desktop(system, "mousepad", "Type=Application\nExec=mousepad\nName=Mousepad\nName[it]=Mousepad\n")
    _desktop(system, "hidden", "Type=Application\nExec=x\nName=Hidden\nNoDisplay=true\n")
    _desktop(system, "link", "Type=Link\nURL=https://example.org\nName=Link\n")
    _desktop(system, "broken", "not an ini file at all")
    # the user's own override hides the system entry with the same id
    _desktop(user, "firefox-esr", "Type=Application\nExec=firefox-esr\nName=Firefox\nNoDisplay=true\n")
    _desktop(system, "firefox-esr", "Type=Application\nExec=firefox-esr\nName=Firefox ESR\n")
    apps = desktop_apps([user, system], lang="it")
    assert apps == {"galculator": "Galculator (Calcolatrice scientifica)", "mousepad": "Mousepad"}
    assert desktop_apps([user, system], lang="en")["galculator"] == "Galculator (Scientific Calculator)"


def test_app_param_is_never_a_path_or_option():
    p = Catalog().playbooks["app.open"].params["app"]
    assert p.coerce("org.gnome.Calculator") == "org.gnome.Calculator"
    for bad in ["../../bin/sh", "/usr/bin/xterm", "-e", "a b", "x;rm", ""]:
        with pytest.raises(ParamError):
            p.coerce(bad)


def test_search_query_is_plain_text():
    p = Catalog().playbooks["web.search"].params["query"]
    assert p.coerce("orari farmacia di turno San Giorgio a Cremano") == "orari farmacia di turno San Giorgio a Cremano"
    assert p.coerce("ricetta pastiera napoletana è facile?") == "ricetta pastiera napoletana è facile?"
    for bad in ['-profile /tmp/x', '"; rm -rf ~', "a\\b", "riga\nnuova", " spazio iniziale", "x" * 121]:
        with pytest.raises(ParamError):
            p.coerce(bad)


def test_app_open_requires_an_installed_app():
    pb = Catalog().playbooks["app.open"]
    assert [c.probe for c in pb.preconditions] == ["apps_installed"]
    assert all(s.detach for s in pb.steps if s.argv)


def test_detach_does_not_wait_for_the_launched_program(tmp_path):
    # a "launcher" that starts a long-lived child holding stdout, then exits
    launcher = tmp_path / "launcher.py"
    launcher.write_text("import subprocess, sys\n"
                        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n")
    t0 = time.monotonic()
    res = run([sys.executable, str(launcher)], timeout=10, detach=True)
    assert res.rc == 0 and time.monotonic() - t0 < 5
    # without detach the same launcher would block on the inherited stdout
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([sys.executable, str(launcher)], stdout=subprocess.PIPE, timeout=3)


def test_maps_turn_names_into_vetted_values():
    cat = Catalog()
    site = cat.playbooks["web.open_site"]
    assert site.command_values({"site": "inps", "browser": "firefox"}) == {
        "site": "https://www.inps.it", "browser": "firefox"}
    with pytest.raises(ParamError):
        site.coerce_params({"site": "https://evil.example", "browser": "firefox"})
    folder = cat.playbooks["files.open_folder"]
    assert folder.command_values({"folder": "photos"}) == {"folder": "xdg:PICTURES"}
    with pytest.raises(ParamError):  # the model can't hand us an xdg: or a path itself
        folder.coerce_params({"folder": "xdg:PICTURES"})


def test_every_site_is_https():
    for url in Catalog().playbooks["web.open_site"].params["site"].map.values():
        assert url.startswith("https://")


def _fake_xdg(tmp_path, monkeypatch, answer):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "xdg-user-dir").write_text(f"#!/bin/sh\necho '{answer}'\n")
    (bin_ / "xdg-user-dir").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:/usr/bin:/bin")
    monkeypatch.setenv("HOME", str(tmp_path))


def test_xdg_folder_resolved_inside_home(tmp_path, monkeypatch):
    from chirone.runner import render_argv

    (tmp_path / "Immagini").mkdir()
    _fake_xdg(tmp_path, monkeypatch, tmp_path / "Immagini")
    assert render_argv(["xdg-open", "{folder}"], {"folder": "xdg:PICTURES"}, allow_home=True) == [
        "xdg-open", str(tmp_path / "Immagini")]


def test_xdg_folder_outside_home_refused(tmp_path, monkeypatch):
    from chirone.runner import render_argv

    _fake_xdg(tmp_path, monkeypatch, "/etc")
    with pytest.raises(ValueError):
        render_argv(["xdg-open", "{folder}"], {"folder": "xdg:PICTURES"}, allow_home=True)
    with pytest.raises(ValueError):
        render_argv(["xdg-open", "{folder}"], {"folder": "xdg:PICTURES"}, allow_home=False)


def test_detach_program_that_keeps_running_counts_as_started():
    t0 = time.monotonic()
    res = run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1, detach=True)
    assert res.rc == 0 and time.monotonic() - t0 < 5


def test_detach_program_is_reaped_when_it_exits(monkeypatch):
    import subprocess
    started = []
    real = subprocess.Popen

    def spy(*a, **k):
        started.append(real(*a, **k))
        return started[-1]

    monkeypatch.setattr(subprocess, "Popen", spy)
    res = run([sys.executable, "-c", "import time; time.sleep(1.5)"], timeout=0.5, detach=True)
    assert res.rc == 0
    time.sleep(2.5)
    # reaped by chirone: no zombie left behind that would still look open
    assert started[0].returncode == 0


def test_detach_launcher_failure_is_reported():
    assert run([sys.executable, "-c", "raise SystemExit(3)"], timeout=5, detach=True).rc == 3
    assert run(["/nonexistent/launcher"], timeout=5, detach=True).rc == 127


def test_qm_mojibake_undone():
    from lab.pve import fix_mojibake

    assert fix_mojibake("piÃ¹ lento") == "più lento"
    assert fix_mojibake("già corretto: più") == "già corretto: più"
