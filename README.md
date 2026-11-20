# chirone

**A tiny, offline troubleshooting model that keeps old PCs alive on Linux.**

Windows 10 extended support ended on 13 October 2026. Hundreds of millions of
working PCs cannot run Windows 11. Linux runs fine on them, and communities
like End of 10 help people install it. What nobody solves is *the day after*:
the printer stops, the sound disappears, an update breaks, and the person has
no one to call.

chirone is the help that stays on the machine. A sub-1B model runs locally on
the same old hardware it repairs (target floor: a 2008 Core 2 Quad without
AVX and 4 GB of RAM), reads what the person writes in plain Italian, runs
read-only diagnostics, and proposes one fix from a closed, audited catalog.
The person approves; chirone applies and verifies. Nothing leaves the PC.

> Chiron taught Asclepius the art of healing. Here a large open model teaches
> a very small one, once, at build time.

## How it works

```
complaint ──► [model] category ──► probe bundle (code) ──► [model] {fix_id, params}
                                                                   │
            person approves ◄── plain-language plan (template) ◄───┘
                   │
                   └──► fixed steps from the catalog ──► verify ──► local log
```

* The model **never writes commands**. It outputs ~20 tokens of JSON,
  constrained by a grammar compiled from the catalog. Params are re-validated
  in Python and again by the root helper.
* Words shown to the person come from templates, not from the model.
* Training labels come from a **fault-injection lab** (Proxmox VMs where each
  fault is broken on purpose, so the correct fix is known by construction).
  A large open-weights teacher only writes the *complaints*, in the voice of
  real users. Every fix is executed in the lab and kept only if it verifies.

See [docs/architecture.md](docs/architecture.md), [docs/safety.md](docs/safety.md),
[docs/catalog.md](docs/catalog.md).

## Layout

```
src/chirone/          agent, probes, executor, root helper, schemas, prompts
src/chirone/catalog/  probes.yaml  playbooks.yaml  categories.yaml  faults.yaml
lab/                  Proxmox fault-injection lab (guest agent, not SSH)
datagen/              teacher complaints + dataset builder
train/                SFT + GGUF export
eval/                 accuracy/latency eval, llama.cpp benchmark
deploy/               pilot-machine installer, llama-server user service
```

## Quickstart (development)

```bash
pip install -e '.[dev]'
chirone validate                 # catalog cross-checks
pytest -q
chirone probe --category network # runs real read-only probes on this machine
chirone schema --step 2 --category audio
```

Day zero on the target machine:

```bash
eval/bench.sh Qwen3.5-0.8B-Q8_0.gguf Qwen3.5-0.8B-Q4_K_M.gguf
```

## Status

Pre-alpha, working end to end. Catalog: 43 probes, 33 playbooks, 9 categories,
27 lab faults, Debian family (Debian, Ubuntu, Linux Mint). Results, all on an
OS held out of training, are in [eval/results/](eval/results/): start from
`2026-11-12-zeroshot-vs-run9.md`, `2026-11-15-run10-vs-run9.md` and
`2026-11-19-cpu-latency.md`. Model weights are not in this repository yet.
See [docs/roadmap.md](docs/roadmap.md).

License: Apache-2.0, see [LICENSE](LICENSE).
