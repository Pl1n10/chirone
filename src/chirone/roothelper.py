"""Privileged helper, invoked as: sudo -n chirone-root-helper probe|step ...

Sudoers whitelists only this program. It trusts nothing from the caller:
the catalog is loaded from the root-owned install, the probe/playbook must
be marked root, and params are validated again before rendering argv.

    probe <probe_id> <params_json>
    step  <fix_id> <step_index> <params_json>
"""
from __future__ import annotations

import json
import os
import sys

from .catalog import Catalog, ParamError
from .probes import execute_probe
from .runner import render_argv, run


def _die(msg: str, code: int = 2) -> None:
    print(f"chirone-root-helper: {msg}", file=sys.stderr)
    sys.exit(code)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if os.geteuid() != 0:
        _die("must run as root")
    cat = Catalog()  # package data, root-owned install
    try:
        if len(args) == 3 and args[0] == "probe":
            probe = cat.probes.get(args[1]) or _die("unknown probe")
            if not probe.root:
                _die("probe does not need root")
            raw = json.loads(args[2])
            # probe params are validated by any playbook that declares them
            params = {}
            for name in probe.params:
                spec = next((pb.params[name] for pb in cat.playbooks.values() if name in pb.params), None)
                if spec is None or name not in raw:
                    _die(f"param {name} missing or undeclared")
                params[name] = spec.coerce(raw[name])
            res = execute_probe(probe, params)
        elif len(args) == 4 and args[0] == "step":
            pb = cat.playbooks.get(args[1]) or _die("unknown playbook")
            if not pb.root:
                _die("playbook does not need root")
            idx = int(args[2])
            if not 0 <= idx < len(pb.steps) or pb.steps[idx].argv is None:
                _die("bad step index")
            params = pb.coerce_params(json.loads(args[3]))
            step = pb.steps[idx]
            res = run(render_argv(step.argv, pb.command_values(params), allow_home=False),
                      timeout=step.timeout, env=step.env)
        else:
            _die("usage: probe <id> <json> | step <fix_id> <n> <json>")
    except (ParamError, ValueError, json.JSONDecodeError) as e:
        _die(str(e))
    sys.stdout.write(res.output)
    sys.exit(res.rc)


if __name__ == "__main__":
    main()
