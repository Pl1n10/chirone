import zipfile

from train.bundle import build


def test_bundle_is_reproducible_and_complete(tmp_path):
    data = tmp_path / "ds"
    data.mkdir()
    (data / "train.jsonl").write_text("{}\n")
    (data / "val.jsonl").write_text("{}\n")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("output_dir: out/x\n")
    p1, s1 = build(data, cfg, tmp_path / "a")
    p2, s2 = build(data, cfg, tmp_path / "b")
    assert s1 == s2  # same inputs, same hash
    with zipfile.ZipFile(p1) as z:
        assert sorted(z.namelist()) == ["data/dataset/train.jsonl", "data/dataset/val.jsonl",
                                        "train/c.yaml", "train/sft.py"]
