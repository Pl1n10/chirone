"""Firefox 147+ puts new profiles under ~/.config/mozilla (XDG); older
installs keep ~/.mozilla. Probe, playbook and lab fault must cover both."""
import re

from chirone.catalog import Catalog
from chirone.probes import compact

LEGACY = "/home/nonna/.mozilla/firefox/a1b2c3.default-esr/lock"
XDG = "/home/nonna/.config/mozilla/firefox/d85indrp.default-lab/lock"


def test_probe_searches_both_homes():
    argv = Catalog().probes["firefox_locks"].argv
    assert "~/.mozilla/firefox" in argv and "~/.config/mozilla/firefox" in argv


def test_probe_keep_drops_missing_dir_noise():
    p = Catalog().probes["firefox_locks"]
    out = f"find: '/home/nonna/.mozilla/firefox': No such file or directory\n{XDG}\n"
    assert compact(out, p.keep, p.max_lines) == XDG


def test_capture_regex_matches_both_homes():
    rx = Catalog().faults["firefox_stale_lock"].expected.params["profile"].regex
    assert re.search(rx, LEGACY).group(1) == "a1b2c3.default-esr"
    assert re.search(rx, XDG).group(1) == "d85indrp.default-lab"


def test_fix_removes_lock_in_both_homes():
    argv = Catalog().playbooks["app.firefox_clear_stale_lock"].steps[0].argv
    assert "~/.mozilla/firefox/{profile}/lock" in argv
    assert "~/.config/mozilla/firefox/{profile}/lock" in argv


def test_firefox_running_does_not_match_chirone_itself():
    import subprocess

    argv = Catalog().probes["firefox_running"].argv
    assert "-f" not in argv and "-x" in argv
    # a process whose command line mentions firefox, but is not Firefox
    p = subprocess.Popen(["sleep", "30", "app.firefox_clear_stale_lock"])
    try:
        assert subprocess.run(argv, capture_output=True).returncode == 1
    finally:
        p.kill()
