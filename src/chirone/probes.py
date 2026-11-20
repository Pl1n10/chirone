"""Run read-only probes and turn their output into a compact block for the model.

Compaction matters more than anything else for speed on old CPUs: prefill
(reading the prompt) is the expensive part, so every probe is filtered,
deduplicated and capped before it reaches the model.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from . import config
from .catalog import Catalog, Check, Probe
from .runner import RunResult, is_root, render_argv, run, run_via_helper


@dataclass
class ProbeResult:
    id: str
    rc: int
    output: str  # already compacted

    def block(self) -> str:
        body = self.output if self.output else "(empty)"
        return f"[{self.id} rc={self.rc}]\n{body}"


def compact(
    text: str, keep: str | None, max_lines: int, tail: bool = False, fields: int | None = None
) -> str:
    # collapse column padding: df/ps pad with spaces, and every space is prompt tokens
    lines = [" ".join(ln.split()) for ln in text.splitlines() if ln.strip()]
    if fields:
        lines = [" ".join(ln.split()[:fields]) for ln in lines]
    if keep:
        rx = re.compile(keep)
        lines = [ln for ln in lines if rx.search(ln)]
    deduped: list[str] = []
    for ln in lines:
        if not deduped or deduped[-1] != ln:
            deduped.append(ln)
    extra = len(deduped) - max_lines
    if extra > 0 and tail:
        deduped = [f"... (+{extra} earlier lines)", *deduped[-max_lines:]]
    elif extra > 0:
        deduped = [*deduped[:max_lines], f"... (+{extra} lines)"]
    return "\n".join(ln[:200] for ln in deduped)


def execute_probe(probe: Probe, params: dict[str, str]) -> RunResult:
    """Run the probe in this process (used directly, or inside the root helper)."""
    if probe.builtin:
        from .builtins import BUILTINS

        rc, out = BUILTINS[probe.builtin]()
        return RunResult(rc, out)
    argv = render_argv(probe.argv, params, allow_home=not probe.root)
    return run(argv, timeout=probe.timeout)


def run_probe(cat: Catalog, probe_id: str, params: dict[str, str] | None = None) -> ProbeResult:
    probe = cat.probes[probe_id]
    params = {k: v for k, v in (params or {}).items() if k in probe.params}
    if probe.root and not is_root():
        res = run_via_helper(["probe", probe_id, json.dumps(params)], probe.timeout)
    else:
        res = execute_probe(probe, params)
    return ProbeResult(probe_id, res.rc, compact(res.output, probe.keep, probe.max_lines, probe.tail, probe.fields))


def collect(cat: Catalog, category: str) -> list[ProbeResult]:
    return [run_probe(cat, pid) for pid in cat.categories[category].probes]


def diagnostics_block(results: list[ProbeResult], budget: int = config.DIAG_BUDGET) -> str:
    """Join probe blocks, trimming from the end if over budget."""
    out, used = [], 0
    for r in results:
        b = r.block()
        if used + len(b) > budget:
            b = b[: max(0, budget - used - 20)] + "\n... (truncated)"
            out.append(b)
            break
        out.append(b)
        used += len(b) + 1
    return "\n".join(out)


def to_json(results: list[ProbeResult]) -> str:
    return json.dumps([asdict(r) for r in results], ensure_ascii=False)


def from_json(data: str | list) -> list[ProbeResult]:
    items = json.loads(data) if isinstance(data, str) else data
    return [ProbeResult(**i) for i in items]


# ---------------------------------------------------------------------------
def check_applies(check: Check, params: dict[str, str]) -> bool:
    return not check.when or all(params.get(k) == v for k, v in check.when.items())


def _fill(rx: str, params: dict[str, str]) -> str:
    return re.sub(r"\{([a-z_]+)\}", lambda m: re.escape(params[m.group(1)]), rx)


def evaluate(
    check: Check, result: ProbeResult, params: dict[str, str], other: ProbeResult | None = None
) -> bool:
    """Params inside check regexes are inserted escaped.

    `other` is the output of `check.mentions.probe`, needed when the check has
    `mentions`: without it such a check fails.
    """
    if check.rc is not None and result.rc != check.rc:
        return False
    if check.match and not re.search(_fill(check.match, params), result.output, re.M):
        return False
    if check.not_match and re.search(_fill(check.not_match, params), result.output, re.M):
        return False
    if check.mentions:
        if other is None or not check.match:
            return False
        values = [v for v in re.findall(_fill(check.mentions.regex, params), other.output, re.M) if v]
        lines = [ln for ln in result.output.splitlines() if re.search(_fill(check.match, params), ln)]
        if not any(v in ln for v in values for ln in lines):
            return False
    return True


def run_checks(cat: Catalog, checks: list[Check], params: dict[str, str]) -> tuple[bool, list[str]]:
    notes = []
    for c in checks:
        if not check_applies(c, params):
            continue
        r = run_probe(cat, c.probe, params)
        other = run_probe(cat, c.mentions.probe, params) if c.mentions else None
        ok = evaluate(c, r, params, other)
        notes.append(f"{'ok' if ok else 'FAIL'} {c.probe}")
        if not ok:
            return False, notes
    return True, notes
