"""ssh-qm lab backend: command building and output parsing, no real ssh."""
import json
import shlex
import subprocess

import pytest

from lab.pve import QmLab, make_lab, parse_guest_exec


class FakeRun:
    def __init__(self, stdout="", rc=0):
        self.calls = []
        self.stdout, self.rc = stdout, rc

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        return subprocess.CompletedProcess(argv, self.rc, self.stdout, "")


CFG = {"backend": "ssh-qm", "ssh_qm": {"host": "pve-agent"}, "lab_user": "nonna"}


def test_make_lab_picks_backend():
    assert isinstance(make_lab(CFG), QmLab)
    with pytest.raises(ValueError):
        make_lab({**CFG, "backend": "nope"})


def test_exec_quotes_script_for_the_remote_shell():
    fake = FakeRun(json.dumps({"exited": 1, "exitcode": 0, "out-data": "ok\n"}))
    lab = QmLab(CFG, runner=fake)
    script = "nmcli connection modify \"$CON\" ipv4.dns 192.0.2.53; echo 'done'"
    assert lab.exec(9101, script, timeout=60) == (0, "ok\n")
    argv = fake.calls[0]
    assert argv[:4] == ["ssh", "-o", "BatchMode=yes", "pve-agent"]
    # what the remote shell will split must be exactly qm's argv, script intact
    assert shlex.split(argv[4]) == ["sudo", "qm", "guest", "exec", "9101", "--timeout", "60", "--",
                                    "bash", "-lc", script]


def test_user_exec_runs_inside_the_session():
    fake = FakeRun(json.dumps({"exited": 1, "exitcode": 0, "out-data": "1001\n"}))
    lab = QmLab(CFG, runner=fake)
    lab.exec(9102, "pactl info", as_user=True)
    remote = shlex.split(fake.calls[-1][4])
    assert remote[8:12] == ["runuser", "-u", "nonna", "--"]
    assert "XDG_RUNTIME_DIR=/run/user/1001" in remote and remote[-1] == "pactl info"


def test_parse_guest_exec():
    out = json.dumps({"exited": 1, "exitcode": 3, "out-data": "a", "err-data": "b"})
    assert parse_guest_exec(out, 0) == (3, "ab")
    with pytest.raises(RuntimeError):
        parse_guest_exec("", 255, "QEMU guest agent is not running")
    with pytest.raises(TimeoutError):
        parse_guest_exec(json.dumps({"exited": 0, "pid": 7}), 0)
