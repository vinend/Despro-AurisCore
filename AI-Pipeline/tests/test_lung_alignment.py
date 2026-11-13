"""Fictional source/cache agreement and holdout protections; no fitting."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import soundfile as sf
import yaml
from auriscore import lung_alignment
from auriscore.acquisition_lung import digest
from auriscore.lung_preprocessing import windows


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    root, cache = tmp_path / "source", tmp_path / "cache"
    root.mkdir(); cache.mkdir()
    config = yaml.safe_load((Path(__file__).parents[1] / "configs/lung_cnn.yaml").read_text())
    audio = .1 * np.sin(2 * np.pi * 200 * np.arange(16000) / 4000)
    sf.write(root / "sample.wav", audio, 4000)
    (root / "label.txt").write_text("0.5 1.5 I\n2.0 3.0 E\n")
    audit = tmp_path / "audit.json"
    audit.write_text("{}")
    labels = [{"start_s": .5, "end_s": 1.5, "label": "inhalation", "original_label": "I"},
              {"start_s": 2., "end_s": 3., "label": "exhalation", "original_label": "E"}]
    records = pd.DataFrame([{"recording_id": "sample", "file_path": "sample.wav", "label_path": "label.txt",
        "original_split": "train", "split": "train", "device": "steth", "group": "1", "valid_end_s": 4.,
        "sha256": digest(root / "sample.wav"), "label_sha256": digest(root / "label.txt"), "license": "CC-BY-4.0"}])
    records.to_csv(tmp_path / "recordings.csv", index=False)
    pd.DataFrame([{**e, "recording_id": "sample"} for e in labels]).to_csv(tmp_path / "events.csv", index=False)
    saved_audio, rate = sf.read(root / "sample.wav")
    index = []
    for block in windows(saved_audio, rate, labels, config, valid_end_s=4., coverage=True):
        name = f"sample_{block['start_sample']}.npz"
        np.savez(cache / name, **block)
        index.append({"file": name, "recording_id": "sample", "split": "train", "group": "1",
                      "source_sha256": records.iloc[0].sha256})
    rows = pd.DataFrame(index)
    rows.to_csv(cache / "index.csv", index=False)
    monkeypatch.setattr(lung_alignment, "preflight", lambda *args: (config, rows))
    return cache, audit, root, tmp_path / "review"


def test_source_cache_review_is_not_acoustic_verification(evidence):
    report = lung_alignment.review_alignment(*evidence)
    assert report["source_cache_agreement"] is True
    assert report["acoustic_alignment_verified"] is False
    assert report["official_test_labels_opened"] is False
    assert '<audio controls' in (evidence[-1] / "review.html").read_text()
    assert digest(evidence[-1] / "recording-0.wav") == digest(evidence[2] / "sample.wav")
    with pytest.raises(ValueError, match="overwrite"):
        lung_alignment.review_alignment(*evidence)


def test_target_shift_is_detected(evidence):
    cache = evidence[0]
    path = next(cache.glob("*.npz"))
    with np.load(path) as saved:
        block = {key: saved[key] for key in saved.files}
    block["targets"] = np.roll(block["targets"], 10, axis=0)
    np.savez(path, **block)
    report = lung_alignment.review_alignment(*evidence)
    assert report["source_cache_agreement"] is False
    assert report["recordings"][0]["mismatches"][0]["field"] == "targets"


def test_non_development_and_changed_source_rejected(evidence):
    with pytest.raises(ValueError, match="development"):
        lung_alignment.review_alignment(*evidence, recording_ids=["official-test"])
    (evidence[2] / "label.txt").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        lung_alignment.review_alignment(*evidence)
