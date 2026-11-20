"""Thin Proxmox wrapper: snapshot rollback and command execution through the
QEMU guest agent. The guest agent keeps working when a fault kills the VM's
network, which is why the lab does not use SSH *into the VM*.

Two backends, same interface (reset / exec / uid):

* ``api`` (default): Proxmox REST API with a token restricted to the lab VMs.
* ``ssh-qm``: ``ssh <node> sudo qm ...`` with an identity that already has
  ``qm`` rights on the node. No API token to mint or store; the guest is
  still driven through the guest agent, so network faults are fine.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time


def make_lab(cfg: dict):
    backend = cfg.get("backend", "api")
    if backend == "api":
        return Lab(cfg)
    if backend == "ssh-qm":
        return QmLab(cfg)
    raise ValueError(f"unknown lab backend {backend!r}")


def _user_cmd(user: str, uid: int, script: str) -> list[str]:
    """Run a script inside the desktop user's session (PipeWire, systemd --user)."""
    return [
        "runuser", "-u", user, "--", "env",
        f"XDG_RUNTIME_DIR=/run/user/{uid}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
        "bash", "-lc", script,
    ]


class Lab:
    def __init__(self, cfg: dict):
        from proxmoxer import ProxmoxAPI  # only the api backend needs it

        p = cfg["proxmox"]
        self.node = p["node"]
        self.px = ProxmoxAPI(
            p["host"],
            user=p["user"],
            token_name=p["token_name"],
            token_value=os.environ[p["token_value_env"]],
            verify_ssl=p.get("verify_ssl", True),
        )
        self.user = cfg["lab_user"]
        self._uids: dict[int, int] = {}

    def vm(self, vmid: int):
        return self.px.nodes(self.node).qemu(vmid)

    def _wait_task(self, upid: str, timeout: int = 300) -> None:
        end = time.time() + timeout
        while time.time() < end:
            st = self.px.nodes(self.node).tasks(upid).status.get()
            if st["status"] == "stopped":
                if st.get("exitstatus") != "OK":
                    raise RuntimeError(f"task {upid}: {st.get('exitstatus')}")
                return
            time.sleep(2)
        raise TimeoutError(upid)

    def reset(self, vmid: int, snapshot: str) -> None:
        """Rollback to a disk-only snapshot and boot to a settled state."""
        if self.vm(vmid).status.current.get()["status"] == "running":
            self._wait_task(self.vm(vmid).status.stop.post())
        self._wait_task(self.vm(vmid).snapshot(snapshot).rollback.post())
        self._wait_task(self.vm(vmid).status.start.post())
        self._wait_agent(vmid)
        self.exec(vmid, "systemctl is-system-running --wait >/dev/null; sleep 5", timeout=240)
        self._uids.pop(vmid, None)

    # 240 s was not enough with four VMs booting at once on one disk (2026-11-08)
    def _wait_agent(self, vmid: int, timeout: int = 480) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                self.vm(vmid).agent.ping.post()
                return
            except Exception:
                time.sleep(3)
        raise TimeoutError(f"guest agent on {vmid}")

    def uid(self, vmid: int) -> int:
        if vmid not in self._uids:
            rc, out = self.exec(vmid, f"id -u {shlex.quote(self.user)}")
            self._uids[vmid] = int(out.strip())
        return self._uids[vmid]

    def exec(self, vmid: int, script: str, as_user: bool = False, timeout: int = 300) -> tuple[int, str]:
        if as_user:
            cmd = _user_cmd(self.user, self.uid(vmid), script)
        else:
            cmd = ["bash", "-lc", script]
        # PVE >= 7 takes `command` as an array; proxmoxer sends lists as repeated fields.
        pid = self.vm(vmid).agent.exec.post(command=cmd)["pid"]
        end = time.time() + timeout
        while time.time() < end:
            st = self.vm(vmid).agent("exec-status").get(pid=pid)
            if st.get("exited"):
                out = (st.get("out-data") or "") + (st.get("err-data") or "")
                return int(st.get("exitcode", 1)), out
            time.sleep(1)
        raise TimeoutError(f"exec on {vmid}: {script[:60]}")


class QmLab:
    """Same interface as Lab, through ``ssh <host> sudo qm`` on the PVE node."""

    def __init__(self, cfg: dict, runner=subprocess.run):
        self.host = cfg["ssh_qm"]["host"]  # an ssh alias, e.g. pve-agent
        self.user = cfg["lab_user"]
        self._run = runner
        self._uids: dict[int, int] = {}

    def _qm(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        remote = " ".join(shlex.quote(a) for a in ("sudo", "qm", *args))
        return self._run(
            ["ssh", "-o", "BatchMode=yes", self.host, remote],
            capture_output=True, text=True, timeout=timeout + 30, check=False,
        )

    def _ok(self, *args: str, timeout: int = 300) -> str:
        r = self._qm(*args, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"qm {' '.join(args)}: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout

    def reset(self, vmid: int, snapshot: str) -> None:
        """Rollback to a disk-only snapshot and boot to a settled state."""
        if "status: running" in self._ok("status", str(vmid)):
            self._ok("stop", str(vmid))
        self._ok("rollback", str(vmid), snapshot)
        self._ok("start", str(vmid))
        self._wait_agent(vmid)
        self.exec(vmid, "systemctl is-system-running --wait >/dev/null; sleep 5", timeout=240)
        self._uids.pop(vmid, None)

    # 240 s was not enough with four VMs booting at once on one disk (2026-11-08)
    def _wait_agent(self, vmid: int, timeout: int = 480) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if self._qm("guest", "cmd", str(vmid), "ping", timeout=20).returncode == 0:
                return
            time.sleep(3)
        raise TimeoutError(f"guest agent on {vmid}")

    def uid(self, vmid: int) -> int:
        if vmid not in self._uids:
            rc, out = self.exec(vmid, f"id -u {shlex.quote(self.user)}")
            self._uids[vmid] = int(out.strip())
        return self._uids[vmid]

    def exec(self, vmid: int, script: str, as_user: bool = False, timeout: int = 300) -> tuple[int, str]:
        cmd = _user_cmd(self.user, self.uid(vmid), script) if as_user else ["bash", "-lc", script]
        r = self._qm("guest", "exec", str(vmid), "--timeout", str(timeout), "--", *cmd, timeout=timeout)
        return parse_guest_exec(r.stdout, r.returncode, r.stderr)


def parse_guest_exec(stdout: str, rc: int, stderr: str = "") -> tuple[int, str]:
    """`qm guest exec` prints the guest-exec-status JSON (exitcode, out-data,
    err-data); a non-zero exit with no JSON means the agent itself failed."""
    try:
        st = json.loads(stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"qm guest exec failed (rc={rc}): {(stderr or stdout).strip()[-300:]}") from None
    if not st.get("exited"):
        raise TimeoutError("guest exec did not finish in time")
    return int(st.get("exitcode", 1)), fix_mojibake((st.get("out-data") or "") + (st.get("err-data") or ""))


def fix_mojibake(s: str) -> str:
    """qm hands the guest's UTF-8 back as if it were Latin-1 ("più" -> "piÃ¹").
    Undo it when the round trip is exact; leave genuine Latin-1 text alone."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
