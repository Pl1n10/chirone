"""Pack what a remote trainer needs (code, config, dataset) into one zip.

    python train/bundle.py --data data/dataset --config train/config-gpu.yaml \
        --out data/bundles/

Prints the zip's SHA-256: the trainer refuses any file but that one
(private remote-run script -Train -BundleUrl ... -BundleSha256 ...).
The zip has fixed timestamps, so the same inputs give the same hash.
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def build(data_dir: Path, config: Path, out_dir: Path) -> tuple[Path, str]:
    members = {
        "train/sft.py": ROOT / "train/sft.py",
        f"train/{config.name}": config,
        "data/dataset/train.jsonl": data_dir / "train.jsonl",
        "data/dataset/val.jsonl": data_dir / "val.jsonl",
    }
    for src in members.values():
        if not src.is_file():
            raise SystemExit(f"missing {src}")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "bundle.zip.tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in sorted(members.items()):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, src.read_bytes())
    sha = hashlib.sha256(tmp.read_bytes()).hexdigest()
    final = out_dir / f"bundle-{sha[:12]}.zip"
    tmp.replace(final)
    return final, sha


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/dataset")
    ap.add_argument("--config", default="train/config-gpu.yaml")
    ap.add_argument("--out", default="data/bundles")
    a = ap.parse_args()
    path, sha = build(Path(a.data), Path(a.config), Path(a.out))
    print(f"{path}\n{sha}\nconfig inside the zip: train/{Path(a.config).name}")


if __name__ == "__main__":
    main()
