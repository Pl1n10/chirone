"""Preconditions that stop a fix the model chose on a PC where the fault is not there.

Run 6 (2026-11-10, lab notes F-019) proposed dns.reset_to_auto and
apt.disable_source on healthy ubuntu24 machines. The probe outputs below are
the real ones from those test rows and from the injected faults.
"""
from chirone import executor
from chirone.catalog import Catalog
from chirone.probes import ProbeResult, compact, evaluate

CAT = Catalog()

# Raw getent lines as the two OSes print them; the probe keeps the address only.
DNS_RAW_UBUNTU = "2a04:4e42:63::644 debian.map.fastlydns.net deb.debian.org"
DNS_RAW_DEBIAN = "2a04:4e42:7d::644 debian.map.fastlydns.net"
_DNS = CAT.probes["dns_lookup"]
DNS_OK_UBUNTU = compact(DNS_RAW_UBUNTU, _DNS.keep, _DNS.max_lines, _DNS.tail, _DNS.fields)
DNS_OK_DEBIAN = compact(DNS_RAW_DEBIAN, _DNS.keep, _DNS.max_lines, _DNS.tail, _DNS.fields)
DNS_BROKEN = "timeout after 8s"

SOURCES_UBUNTU = (
    "/etc/apt/sources.list.d/mozilla.list:deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] "
    "https://packages.mozilla.org/apt mozilla main\n"
    "/etc/apt/sources.list.d/ubuntu.sources:URIs: http://archive.ubuntu.com/ubuntu"
)
APT_ERR = "Err:4 http://deb.example.invalid/debian bookworm InRelease\nE: Failed to fetch"


def _pre(
    fix_id: str, probe: str, output: str, params: dict[str, str], rc: int = 0, other: str | None = None
) -> bool:
    checks = [c for c in CAT.playbooks[fix_id].preconditions if c.probe == probe]
    assert checks, f"{fix_id} has no precondition on {probe}"
    return all(
        evaluate(c, ProbeResult(probe, rc, output), params,
                 ProbeResult(c.mentions.probe, 0, other) if c.mentions and other is not None else None)
        for c in checks
    )


def test_dns_reset_only_when_lookup_fails():
    p = {"connection": "Connessione via cavo 1"}
    assert not _pre("dns.reset_to_auto", "dns_lookup", DNS_OK_UBUNTU, p)
    assert not _pre("dns.reset_to_auto", "dns_lookup", DNS_OK_DEBIAN, p)
    assert _pre("dns.reset_to_auto", "dns_lookup", DNS_BROKEN, p, rc=124)
    assert _pre("dns.reset_to_auto", "dns_lookup", "", p, rc=2)


def test_disable_source_needs_an_existing_file():
    assert _pre("apt.disable_source", "apt_sources", SOURCES_UBUNTU, {"file": "mozilla.list"})
    # the names run 6 invented: not in apt_sources, never moved
    for bad in ["packages.mozilla.org.ascittal_bazar_mozilla.list", "zilla.list", "ubuntu.sources.list"]:
        assert not _pre("apt.disable_source", "apt_sources", SOURCES_UBUNTU, {"file": bad})


SOURCES_MIXED = SOURCES_UBUNTU + (
    "\n/etc/apt/sources.list.d/vecchio-programma.list:deb http://deb.chirone.invalid/debian stable main"
)
APT_ERR_MIXED = (
    "Err:5 http://deb.chirone.invalid/debian stable InRelease\n"
    "W: Failed to fetch http://deb.chirone.invalid/debian/dists/stable/InRelease\n"
    "W: Some index files failed to download. They have been ignored, or old ones used instead."
)


def test_disable_source_needs_apt_errors():
    p = {"file": "vecchio-programma.list"}
    assert not _pre("apt.disable_source", "apt_update", "", p, other=SOURCES_MIXED)
    assert _pre("apt.disable_source", "apt_update", APT_ERR_MIXED, p, other=SOURCES_MIXED)


def test_disable_source_only_the_failing_file():
    # F-020: run 8 chose the good mozilla.list next to the broken source
    p = {"file": "mozilla.list"}
    assert not _pre("apt.disable_source", "apt_update", APT_ERR_MIXED, p, other=SOURCES_MIXED)
    assert not _pre("apt.disable_source", "apt_update", "E: Failed", p, other=SOURCES_MIXED)
    # a broken mozilla source is still disabled
    err = "Err:3 https://packages.mozilla.org/apt mozilla InRelease\nE: Failed to fetch"
    assert _pre("apt.disable_source", "apt_update", err, p, other=SOURCES_MIXED)


def test_disable_source_deb822_file():
    p = {"file": "ubuntu.sources"}
    err = "Err:1 http://archive.ubuntu.com/ubuntu noble InRelease"
    assert _pre("apt.disable_source", "apt_update", err, p, other=SOURCES_MIXED)
    assert not _pre("apt.disable_source", "apt_update", APT_ERR_MIXED, p, other=SOURCES_MIXED)


def test_mentions_without_other_output_fails():
    p = {"file": "vecchio-programma.list"}
    assert not _pre("apt.disable_source", "apt_update", APT_ERR_MIXED, p)


def test_not_needed_message_on_failed_precondition(monkeypatch):
    pb = CAT.playbooks["dns.reset_to_auto"]
    monkeypatch.setattr(executor, "run_checks", lambda *a, **k: (False, ["FAIL dns_lookup"]))
    monkeypatch.setattr(executor, "_log", lambda o: o)
    out = executor.execute(CAT, pb, {"connection": "Connessione via cavo 1"}, confirm=lambda _: True, lang="it")
    assert out.status == "precondition_failed"
    assert "niente da cambiare" in out.message


def test_failure_message_when_no_not_needed(monkeypatch):
    pb = CAT.playbooks["app.close"]
    monkeypatch.setattr(executor, "run_checks", lambda *a, **k: (False, ["FAIL apps_running"]))
    monkeypatch.setattr(executor, "_log", lambda o: o)
    out = executor.execute(CAT, pb, {"app": "firefox"}, confirm=lambda _: True, lang="it")
    assert out.message == executor.message(pb, "failure", {"app": "firefox"}, "it")


def test_dns_lookup_output_is_the_same_on_both_oses():
    # F-019: the alias Ubuntu prints after the address was read as a DNS fault
    assert DNS_OK_UBUNTU == "2a04:4e42:63::644"
    assert DNS_OK_DEBIAN == "2a04:4e42:7d::644"


def test_build_dataset_recompacts_old_dns_samples():
    from datagen.build_dataset import recompact

    probes = [{"id": "dns_lookup", "rc": 0, "output": DNS_RAW_UBUNTU},
              {"id": "resolv_conf", "rc": 0, "output": "nameserver 1.1.1.1"}]
    recompact(CAT, probes)
    recompact(CAT, probes)  # idempotent
    assert probes[0]["output"] == DNS_OK_UBUNTU
    assert probes[1]["output"] == "nameserver 1.1.1.1"


# vm2 (ubuntu24) seen by a user outside the graphical session: no card, only
# PipeWire's null sink. Run 9 chose it, already the default (2026-11-12).
SINKS_NULL = "36 auto_null PipeWire float32le 2ch 48000Hz SUSPENDED"
SERVER_NULL = "Server Name: PulseAudio (on PipeWire 1.0.5)\nDefault Sink: auto_null"
SINKS_REAL = SINKS_NULL + "\n69 alsa_output.pci-0000_02_0c.0.analog-stereo PipeWire s16le 2ch 48000Hz SUSPENDED"
SERVER_HDMI = "Server Name: PulseAudio (on PipeWire 1.0.5)\nDefault Sink: alsa_output.pci-0000_01_00.1.hdmi-stereo"
ANALOG = "alsa_output.pci-0000_02_0c.0.analog-stereo"


def test_set_default_sink_not_the_current_default():
    p = {"sink": "auto_null"}
    assert _pre("audio.set_default_sink", "audio_sinks", SINKS_NULL, p)
    assert not _pre("audio.set_default_sink", "audio_server", SERVER_NULL, p)


def test_set_default_sink_needs_an_existing_sink():
    assert _pre("audio.set_default_sink", "audio_sinks", SINKS_REAL, {"sink": ANALOG})
    assert _pre("audio.set_default_sink", "audio_server", SERVER_HDMI, {"sink": ANALOG})
    for bad in ["alsa_output.pci-0000_02_0c.0.analog", "alsa_output.pci-0000_00_1b.0.analog-stereo"]:
        assert not _pre("audio.set_default_sink", "audio_sinks", SINKS_REAL, {"sink": bad})


def test_build_dataset_recompacts_old_long_probes():
    # run 10: tighter kernel_errors/top_procs/disk_usage, applied to old samples too
    from datagen.build_dataset import recompact

    kern = "\n".join(["... (+4 earlier lines)", *[f"err {i}" for i in range(10)]])
    procs = "\n".join(["PID USER COMMAND %CPU %MEM", *[f"{i} u p{i} 1.0 0.1" for i in range(7)],
                       "... (+120 lines)"])
    df = ("Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 19G 5.9G 13G 33% /\n"
          "/dev/sda16 881M 167M 653M 21% /boot\n/dev/sda15 105M 6.2M 99M 6% /boot/efi")
    probes = [{"id": "kernel_errors", "rc": 0, "output": kern},
              {"id": "top_procs", "rc": 0, "output": procs},
              {"id": "disk_usage", "rc": 0, "output": df}]
    recompact(CAT, probes)
    once = [p["output"] for p in probes]
    recompact(CAT, probes)  # idempotent
    assert [p["output"] for p in probes] == once
    assert once[0].splitlines() == ["... (+9 earlier lines)", "err 5", "err 6", "err 7", "err 8", "err 9"]
    assert once[1].splitlines()[-1] == "... (+123 lines)"
    assert len(once[1].splitlines()) == 6
    assert once[2] == "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 19G 5.9G 13G 33% /"
