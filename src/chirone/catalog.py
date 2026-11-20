"""Catalog: probes, playbooks, categories and lab faults, loaded from YAML.

The catalog is the single source of truth shared by the agent on the user's
PC, the root helper, the lab collector and the dataset builder.
"""
from __future__ import annotations

import re
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParamError(ValueError):
    pass


class Param(Strict):
    type: Literal["enum", "pattern", "int"]
    values: list[str] | None = None
    pattern: str | None = None
    min: int | None = None
    max: int | None = None
    default: int | str | None = None
    hint: str = ""
    # enum only: what each value turns into in the command. The model picks a
    # word from a closed list ("inps", "photos"), the catalog owns the URL or
    # path. A value "xdg:PICTURES" is resolved on the PC with xdg-user-dir.
    map: dict[str, str] | None = None

    def coerce(self, value) -> str:
        """Validate a model-proposed value and return it as a string."""
        if self.type == "enum":
            if value not in (self.values or []):
                raise ParamError(f"{value!r} not in {self.values}")
            return str(value)
        if self.type == "int":
            try:
                iv = int(value)
            except (TypeError, ValueError):
                raise ParamError(f"{value!r} is not an integer") from None
            if isinstance(value, bool) or (self.min is not None and iv < self.min) or (
                self.max is not None and iv > self.max
            ):
                raise ParamError(f"{iv} outside [{self.min}, {self.max}]")
            return str(iv)
        sval = str(value)
        if not re.fullmatch(self.pattern or "", sval):
            raise ParamError(f"{sval!r} does not match {self.pattern!r}")
        if sval.startswith("-") or "\x00" in sval or "\n" in sval:
            raise ParamError(f"{sval!r} rejected (option or control characters)")
        return sval

    def json_schema(self) -> dict:
        if self.type == "enum":
            return {"enum": list(self.values or [])}
        if self.type == "int":
            s: dict = {"type": "integer"}
            if self.min is not None:
                s["minimum"] = self.min
            if self.max is not None:
                s["maximum"] = self.max
            return s
        return {"type": "string", "pattern": f"^{self.pattern}$"}


class Probe(Strict):
    id: str
    # exactly one of argv (a command, never a shell) or builtin (chirone.builtins)
    argv: list[str] = Field(default_factory=list)
    builtin: str | None = None
    root: bool = False
    timeout: int = 10
    max_lines: int = 15
    # Keep the last max_lines lines instead of the first: for logs, where the
    # newest lines are the ones about the problem the person has now (F-017).
    tail: bool = False
    keep: str | None = None
    # Keep only the first N whitespace-separated fields of each line. For output
    # whose tail varies by OS without meaning anything: getent hosts prints the
    # alias on Ubuntu and not on Debian, and run 6 read that as a DNS fault (F-019).
    fields: int | None = None
    params: list[str] = Field(default_factory=list)
    description: str = ""
    # Non-empty only for the rare probe that changes state. Declared, never
    # implicit: docs/catalog.md lists them and a test pins the set.
    side_effect: str = ""


class Mentions(Strict):
    """Values taken from another probe that must show up in the checked lines.

    `regex` (params allowed) is run on the other probe's output; its first
    group gives the values. The check passes only if a line of this probe
    that matches `match` contains one of them.
    """

    probe: str
    regex: str


class Check(Strict):
    """A probe-based assertion, used for preconditions and verification."""

    probe: str
    match: str | None = None
    not_match: str | None = None
    rc: int | None = None
    when: dict[str, str] | None = None  # only applies if params match
    mentions: Mentions | None = None


class Step(Strict):
    argv: list[str] | None = None
    wait: int | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout: int = 120
    # Starts a program that keeps running (an app the person asked for): do
    # not wait for it, do not capture its output. Only the launcher's exit
    # code counts.
    detach: bool = False


class LangMessages(Strict):
    plan: str
    success: str = ""
    failure: str = ""
    # Said when a precondition shows the fix is not needed (the model chose it
    # on a PC where the fault is not there). Falls back to `failure`.
    not_needed: str = ""


class Playbook(Strict):
    id: str
    title: str
    risk: Literal["low", "medium", "high"]
    root: bool = False
    confirm: bool = True
    # Steps-less hand-over to a person: the executor writes a summary
    # (complaint, decision, diagnostics) for whoever comes to help.
    handover: bool = False
    params: dict[str, Param] = Field(default_factory=dict)
    preconditions: list[Check] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    verify: list[Check] = Field(default_factory=list)
    messages: dict[str, LangMessages]

    def command_values(self, params: dict[str, str]) -> dict[str, str]:
        """Validated params as they go into argv: mapped enums replaced."""
        return {k: (self.params[k].map or {}).get(v, v) if k in self.params else v for k, v in params.items()}

    def coerce_params(self, raw: dict | None) -> dict[str, str]:
        raw = dict(raw or {})
        extra = set(raw) - set(self.params)
        if extra:
            raise ParamError(f"{self.id}: unexpected params {sorted(extra)}")
        out = {}
        for name, spec in self.params.items():
            if name not in raw:
                if spec.default is None:
                    raise ParamError(f"{self.id}: missing param {name!r}")
                raw[name] = spec.default
            out[name] = spec.coerce(raw[name])
        return out


class Category(Strict):
    id: str
    label: dict[str, str]
    probes: list[str]
    fixes: list[str]
    # Where step-2 labels come from. lab: a fault injected in the lab, the fix
    # is correct by construction. requests: the person's request itself
    # (which program, what to search), paired with healthy lab snapshots.
    source: Literal["lab", "requests"] = "lab"


class Capture(Strict):
    probe: str
    regex: str


class Expected(Strict):
    fix_id: str
    params: dict[str, Capture | int | str] = Field(default_factory=dict)


class Fault(Strict):
    id: str
    category: str
    run_as: Literal["root", "user"]
    fidelity: Literal["low", "medium", "high"]
    symptom_it: str
    inject: str
    check_broken: str
    expected: Expected


def _load_yaml(base: Path, name: str):
    return yaml.safe_load((base / name).read_text(encoding="utf-8"))


class Catalog:
    def __init__(self, base: Path | None = None):
        self.base = Path(base) if base else Path(str(resources.files("chirone") / "catalog"))
        probes = [Probe(**p) for p in _load_yaml(self.base, "probes.yaml")]
        playbooks = [Playbook(**p) for p in _load_yaml(self.base, "playbooks.yaml")]
        cats = _load_yaml(self.base, "categories.yaml")
        faults = [Fault(**f) for f in _load_yaml(self.base, "faults.yaml")]
        self.probes = {p.id: p for p in probes}
        self.playbooks = {p.id: p for p in playbooks}
        self.categories = {c["id"]: Category(**c) for c in cats["categories"]}
        self.global_fixes: list[str] = cats["global_fixes"]
        self.faults = {f.id: f for f in faults}
        for kind, items, d in (
            ("probe", probes, self.probes),
            ("playbook", playbooks, self.playbooks),
            ("fault", faults, self.faults),
        ):
            if len(items) != len(d):
                raise ValueError(f"duplicate {kind} ids")

    def fixes_for(self, category: str) -> list[str]:
        return self.categories[category].fixes + self.global_fixes

    @cached_property
    def fix_ids(self) -> list[str]:
        return list(self.playbooks)

    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Cross-reference checks. Returns a list of problems (empty = ok)."""
        errs: list[str] = []
        from .builtins import BUILTINS

        for p in self.probes.values():
            if bool(p.argv) == bool(p.builtin):
                errs.append(f"probe {p.id}: exactly one of argv/builtin")
            if p.builtin and p.builtin not in BUILTINS:
                errs.append(f"probe {p.id}: unknown builtin {p.builtin}")
            if p.builtin and (p.root or p.params):
                errs.append(f"probe {p.id}: builtins run as the user and take no params")
            used = {m for a in p.argv for m in PLACEHOLDER.findall(a)}
            if used != set(p.params):
                errs.append(f"probe {p.id}: placeholders {used} != params {set(p.params)}")
            if p.root and any(a.startswith("~") for a in p.argv):
                errs.append(f"probe {p.id}: root probes must not use ~")
            if p.keep:
                _try_regex(p.keep, f"probe {p.id}.keep", errs)
        for pb in self.playbooks.values():
            declared = set(pb.params)
            for i, s in enumerate(pb.steps):
                if (s.argv is None) == (s.wait is None):
                    errs.append(f"{pb.id} step {i}: exactly one of argv/wait")
                for a in s.argv or []:
                    for m in PLACEHOLDER.findall(a):
                        if m not in declared:
                            errs.append(f"{pb.id} step {i}: undeclared {{{m}}}")
                    if pb.root and a.startswith("~"):
                        errs.append(f"{pb.id}: root playbooks must not use ~")
                if s.detach and pb.root:
                    errs.append(f"{pb.id} step {i}: detach is for user programs, not root steps")
            for c in pb.preconditions + pb.verify:
                probe = self.probes.get(c.probe)
                if not probe:
                    errs.append(f"{pb.id}: unknown probe {c.probe}")
                    continue
                if not set(probe.params) <= declared:
                    errs.append(f"{pb.id}: probe {c.probe} needs params {probe.params}")
                for rx in (c.match, c.not_match):
                    if rx:
                        _try_regex(PLACEHOLDER.sub("x", rx), f"{pb.id} check", errs)
                if c.mentions:
                    if not c.match:
                        errs.append(f"{pb.id}: mentions needs match")
                    other = self.probes.get(c.mentions.probe)
                    if not other:
                        errs.append(f"{pb.id}: unknown probe {c.mentions.probe}")
                    elif not set(other.params) <= declared:
                        errs.append(f"{pb.id}: probe {c.mentions.probe} needs params {other.params}")
                    _try_regex(PLACEHOLDER.sub("x", c.mentions.regex), f"{pb.id} mentions", errs)
            for name, spec in pb.params.items():
                if spec.type == "pattern":
                    if not spec.pattern:
                        errs.append(f"{pb.id}.{name}: pattern missing")
                    else:
                        _try_regex(spec.pattern, f"{pb.id}.{name}", errs)
                if spec.type == "enum" and not spec.values:
                    errs.append(f"{pb.id}.{name}: enum without values")
                if spec.map is not None:
                    if spec.type != "enum" or set(spec.map) != set(spec.values or []):
                        errs.append(f"{pb.id}.{name}: map must cover exactly the enum values")
                    for v in spec.map.values():
                        if not (v.startswith("https://") or v.startswith("xdg:")):
                            errs.append(f"{pb.id}.{name}: map value {v!r} is neither https:// nor xdg:")
                        if v.startswith("xdg:") and pb.root:
                            errs.append(f"{pb.id}.{name}: xdg: paths are the user's, not for root playbooks")
            if set(pb.messages) != {"it", "en"}:
                errs.append(f"{pb.id}: messages must have it and en")
            if pb.handover:
                if pb.steps:
                    errs.append(f"{pb.id}: handover playbooks have no steps")
                for lang, m in pb.messages.items():
                    if "{summary_path}" not in m.success or not m.failure:
                        errs.append(f"{pb.id}.{lang}: handover needs success with {{summary_path}} and a failure")
        for c in self.categories.values():
            for pid in c.probes:
                if pid not in self.probes:
                    errs.append(f"category {c.id}: unknown probe {pid}")
                elif self.probes[pid].params:
                    errs.append(f"category {c.id}: probe {pid} needs params")
            for fid in c.fixes:
                if fid not in self.playbooks:
                    errs.append(f"category {c.id}: unknown fix {fid}")
        for g in self.global_fixes:
            if g not in self.playbooks:
                errs.append(f"global fix {g} unknown")
        reachable = {f for c in self.categories.values() for f in c.fixes} | set(self.global_fixes)
        for pid in set(self.playbooks) - reachable:
            errs.append(f"playbook {pid} unreachable from any category")
        for f in self.faults.values():
            if f.category not in self.categories:
                errs.append(f"fault {f.id}: unknown category {f.category}")
                continue
            if f.expected.fix_id not in self.fixes_for(f.category):
                errs.append(f"fault {f.id}: {f.expected.fix_id} not allowed in {f.category}")
                continue
            pb = self.playbooks[f.expected.fix_id]
            required = {n for n, s in pb.params.items() if s.default is None}
            if not (required <= set(f.expected.params) <= set(pb.params)):
                errs.append(f"fault {f.id}: params {set(f.expected.params)} vs {set(pb.params)}")
            for name, v in f.expected.params.items():
                if isinstance(v, Capture):
                    if v.probe not in self.categories[f.category].probes:
                        errs.append(f"fault {f.id}: capture probe {v.probe} not in category bundle")
                    _try_regex(v.regex, f"fault {f.id}.{name}", errs)
                elif name in pb.params:
                    try:
                        pb.params[name].coerce(v)
                    except ParamError as e:
                        errs.append(f"fault {f.id}: {e}")
        return errs


def _try_regex(rx: str, where: str, errs: list[str]) -> None:
    try:
        re.compile(rx)
    except re.error as e:
        errs.append(f"{where}: bad regex {rx!r}: {e}")
