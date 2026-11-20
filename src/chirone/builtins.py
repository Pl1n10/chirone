"""Probes implemented in Python instead of an external command.

Only for read-only facts that no single standard command prints compactly
(no shell is ever used: catalog probes are argv lists or one of these).
Each builtin returns (rc, output) like a command would.
"""
from __future__ import annotations

import configparser
import os
import shlex
from pathlib import Path

from . import config


def _app_dirs() -> list[Path]:
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [data_home] + [Path(d) for d in data_dirs.split(":") if d]
    # Flatpak exports are on XDG_DATA_DIRS in a desktop session, not always in ours.
    dirs += [Path.home() / ".local/share/flatpak/exports/share", Path("/var/lib/flatpak/exports/share")]
    return [d / "applications" for d in dirs]


def _localized(entry: configparser.SectionProxy, key: str, lang: str) -> str:
    return entry.get(f"{key}[{lang}]") or entry.get(key) or ""


def desktop_apps(dirs: list[Path] | None = None, lang: str | None = None) -> dict[str, str]:
    """desktop id -> "Name (GenericName)" for every launchable application.

    The first directory wins on duplicate ids (XDG precedence: the user's own
    overrides come first). Hidden/NoDisplay entries and non-applications are
    skipped: they are not something a person asks to open.
    """
    lang = lang or config.LANG
    apps: dict[str, str] = {}
    hidden: set[str] = set()
    for d in dirs if dirs is not None else _app_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.desktop")):
            app_id = f.name.removesuffix(".desktop")
            if app_id in apps or app_id in hidden:
                continue
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if (e.get("Type") != "Application" or e.get("NoDisplay", "").lower() == "true"
                    or e.get("Hidden", "").lower() == "true" or not e.get("Exec")):
                hidden.add(app_id)
                continue
            name = _localized(e, "Name", lang)
            generic = _localized(e, "GenericName", lang)
            label = name if not generic or generic.lower() == name.lower() else f"{name} ({generic})"
            apps[app_id] = label
    return apps


def apps_installed() -> tuple[int, str]:
    apps = desktop_apps()
    if not apps:
        return 1, "no applications found"
    return 0, "\n".join(f"{k}: {v}" for k, v in sorted(apps.items(), key=lambda kv: kv[1].lower()))


# Programs whose process is not named after the Exec of their .desktop file.
PROCESS_ALIASES = {"libreoffice": {"soffice.bin", "oosplash"}, "gnome-calculator": {"gnome-calculator"}}


# The desktop itself, never "a program to close": panel, desktop, window
# manager, session, sound. Their settings entries (panel-preferences runs
# xfce4-panel) would otherwise look like open programs (2026-11-10, vm1).
SESSION_PROCESSES = {
    "xfce4-panel", "xfdesktop", "xfwm4", "xfce4-session", "xfsettingsd", "xfconfd", "xfce4-notifyd",
    "xfce4-power-manager", "thunar", "Thunar", "nemo-desktop", "cinnamon", "cinnamon-session", "muffin",
    "mate-panel", "mate-session", "marco", "caja", "gnome-shell", "gnome-session-binary", "nautilus",
    "lightdm", "Xorg", "Xwayland", "dbus-daemon", "pipewire", "pipewire-pulse", "wireplumber",
    "pulseaudio", "systemd", "llama-server", "chirone",
}


def desktop_execs(dirs: list[Path] | None = None) -> dict[str, set[str]]:
    """desktop id -> process names that mean "this program is open"."""
    out: dict[str, set[str]] = {}
    for d in dirs if dirs is not None else _app_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.desktop")):
            app_id = f.name.removesuffix(".desktop")
            if app_id in out:
                continue
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
                argv = shlex.split(cp["Desktop Entry"].get("Exec", ""))
            except (configparser.Error, KeyError, UnicodeDecodeError, ValueError):
                continue
            while argv and (argv[0] == "env" or "=" in argv[0]):
                argv = argv[1:]
            if not argv:
                continue
            name = Path(argv[0]).name
            names = {name, *PROCESS_ALIASES.get(name, set())} - SESSION_PROCESSES
            if names:
                out[app_id] = names
    return out


def _ancestors() -> set[int]:
    """This process and its parents: chirone must never close the window it runs in."""
    pids, pid = set(), os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            pid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


def user_processes(proc: Path = Path("/proc")) -> dict[int, set[str]]:
    """pid -> names (comm, argv0 basename) of this user's processes, minus our own ancestry."""
    uid, skip, out = os.getuid(), _ancestors(), {}
    for p in proc.iterdir():
        if not p.name.isdigit() or int(p.name) in skip:
            continue
        try:
            if p.stat().st_uid != uid:
                continue
            stat = (p / "stat").read_text() if (p / "stat").exists() else ""
            if stat and stat.rsplit(")", 1)[1].split()[0] == "Z":
                continue  # exited, only waiting to be reaped: not open
            comm = (p / "comm").read_text().strip()
            argv0 = (p / "cmdline").read_bytes().split(b"\0", 1)[0].decode(errors="replace")
        except OSError:
            continue
        out[int(p.name)] = {comm, Path(argv0).name} - {""}
    return out


def app_pids(app_id: str) -> list[int]:
    names = desktop_execs().get(app_id, set())
    return sorted(pid for pid, n in user_processes().items() if n & names)


def apps_running() -> tuple[int, str]:
    """Installed programs that are open right now, same format as apps_installed."""
    apps, execs, procs = desktop_apps(), desktop_execs(), user_processes()
    running = {n for names in procs.values() for n in names}
    lines = [f"{k}: {v}" for k, v in sorted(apps.items(), key=lambda kv: kv[1].lower())
             if execs.get(k, set()) & running]
    return 0, "\n".join(lines)


BUILTINS = {"apps_installed": apps_installed, "apps_running": apps_running}
