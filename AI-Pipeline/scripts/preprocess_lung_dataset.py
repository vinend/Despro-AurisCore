"""Build Lung feature caches; no weights fitted and test labels never read."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import soundfile as sf
import yaml
import _bootstrap  # noqa: F401
from auriscore.dataset_lung import assert_split_integrity
from auriscore.acquisition_lung import digest
from auriscore.lung_preprocessing import windows, config_digest

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("data/external/hf-lung-v1/extracted"))
    p.add_argument("--manifest", type=Path, default=Path("data/processed/lung"))
    p.add_argument("--config", type=Path, default=Path("configs/lung_cnn.yaml"))
    a = p.parse_args()
    config = yaml.safe_load(a.config.read_text())
    frame = pd.read_csv(a.manifest / "recordings.csv", dtype={"group": str})
    events = pd.read_csv(a.manifest / "events.csv")
    assert_split_integrity(frame)
    output = a.manifest / "cache" / config_digest(config)
    output.mkdir(parents=True, exist_ok=True)
    index = []
    for row in frame[frame.split.isin(["train", "validation"])].itertuples():
        if digest(a.root / row.file_path) != row.sha256 or digest(a.root / row.label_path) != row.label_sha256:
            raise ValueError("Dataset changed after manifest audit")
        audio, rate = sf.read(a.root / row.file_path)
        labels = events[events.recording_id == row.recording_id].to_dict("records")
        for block in windows(audio, rate, labels, config, valid_end_s=row.valid_end_s,
                             coverage=config.get("annotation_coverage_verified") is True):
            name = f"{row.recording_id}_{block['start_sample']}.npz"
            np.savez_compressed(output / name, **block)
            index.append({"file": name, "group": row.group, "recording_id": row.recording_id,
                          "split": row.split, "source_sha256": row.sha256})
    pd.DataFrame(index).to_csv(output / "index.csv", index=False)
    (output / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (output / "provenance.json").write_text(json.dumps({"audit_sha256": digest(a.manifest / "audit.json"),
        "recordings_sha256": digest(a.manifest / "recordings.csv"), "events_sha256": digest(a.manifest / "events.csv"),
        "config_sha256": digest(output / "config.json"), "index_sha256": digest(output / "index.csv")}, indent=2))
    print(f"Prepared {len(index)} windows; no training started.")
