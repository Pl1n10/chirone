"""Command execution shared by probes, playbook steps and the root helper."""
from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass

from . import config
from .catalog import PLACEHOLDER


@dataclass
class RunResult:
    rc: int
    output: str


def xdg_user_dir(name: str) -> str:
    """The person's own folder (Immagini, Documenti...) inside their home, or an error."""
    res = run(["xdg-user-dir", name], timeout=5)
    path = os.path.realpath(res.output.strip()) if res.rc == 0 else ""
    home = os.path.realpath(os.path.expanduser("~"))
    if not path or not (path == home or path.startswith(home + os.sep)) or not os.path.isdir(path):
        raise ValueError(f"no usable folder for {name}")
    return path


def render_argv(argv: list[str], params: dict[str, str], allow_home: bool) -> list[str]:
    """Fill {placeholders} with already-validated params; expand a leading ~;
    resolve xdg:NAME (only ever produced by a catalog map) to the user's folder."""
    out = []
    for a in argv:
        a = PLACEHOLDER.sub(lambda m: params[m.group(1)], a)
        if a.startswith("xdg:"):
            if not allow_home:
                raise ValueError("xdg: not allowed here")
            a = xdg_user_dir(a.removeprefix("xdg:"))
        if a.startswith("~"):
            if not allow_home:
                raise ValueError("~ not allowed here")
            a = os.path.expanduser(a)
        out.append(a)
    return out


def run(argv: list[str], timeout: int, env: dict[str, str] | None = None, detach: bool = False) -> RunResult:
    full_env = {**os.environ, **config.PROBE_ENV, **(env or {})}
    if detach:
        # Starts a program the person keeps using. Two shapes: a launcher that
        # hands off and exits (gtk-launch, xdg-open, or Firefox passing the URL
        # to a running Firefox), or the program itself (Firefox when it was
        # closed), which never exits while in use. So: never capture output (the
        # program inherits it and would hold us), own session (it outlives
        # chirone), the user's locale; wait `timeout` seconds at most: exited ->
        # its exit code, still running -> it started.
        try:
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True,
                                 env={**os.environ, **(env or {})})
        except FileNotFoundError:
            return RunResult(127, f"{argv[0]}: command not found")
        try:
            return RunResult(p.wait(timeout=timeout), "")
        except subprocess.TimeoutExpired:
            # chirone chat lives on: reap the program when the person closes it,
            # or it stays a zombie child of ours and still looks open (app.close)
            threading.Thread(target=p.wait, daemon=True).start()
            return RunResult(0, f"running after {timeout}s")
    try:
        p = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=full_env,
            text=True,
            errors="replace",
        )
        return RunResult(p.returncode, p.stdout)
    except FileNotFoundError:
        return RunResult(127, f"{argv[0]}: command not found")
    except subprocess.TimeoutExpired:
        return RunResult(124, f"timeout after {timeout}s")


def is_root() -> bool:
    return os.geteuid() == 0


def run_via_helper(args: list[str], timeout: int) -> RunResult:
    """Run a root-only probe/step through the sudo-whitelisted helper."""
    if not os.path.exists(config.HELPER):
        return RunResult(126, "root helper not installed")
    return run(["sudo", "-n", config.HELPER, *args], timeout=timeout + 5)
