"""Lifecycle checks use fictional data and inference stubs; never fit models."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
import soundfile as sf
import yaml
from auriscore.acquisition_lung import digest
from auriscore.lung_training import preflight, train_final
from auriscore.lung_holdout import evaluate


def development(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    config = yaml.safe_load((Path(__file__).parents[1] / "configs/lung_cnn.yaml").read_text())
    (cache / "config.json").write_text(json.dumps(config))
    (tmp_path / "recordings.csv").write_text("fictional manifest")
    (tmp_path / "events.csv").write_text("fictional events")
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"test_inventory_present": True, "near_duplicate_review_complete": True,
        "annotation_coverage_verified": True, "observed_train_labels": config["classes"]}))
    rows = []
    for i, split in enumerate(("train", "validation")):
        name = f"{split}.npz"
        np.savez(cache / name, features=np.zeros((309, 96)), targets=np.zeros((309, 6)), mask=np.ones((309, 6)))
        rows.append({"file": name, "split": split, "group": str(i), "source_sha256": str(i) * 64})
    pd.DataFrame(rows).to_csv(cache / "index.csv", index=False)
    provenance = {"audit_sha256": digest(audit), "config_sha256": digest(cache / "config.json"),
        "index_sha256": digest(cache / "index.csv"), "recordings_sha256": digest(tmp_path / "recordings.csv"),
        "events_sha256": digest(tmp_path / "events.csv")}
    (cache / "provenance.json").write_text(json.dumps(provenance))
    return cache, audit, config


def test_preflight_rejects_changed_sources_and_final_rejects_unbound_selection(tmp_path):
    cache, audit, config = development(tmp_path)
    assert len(preflight(cache, audit)[1]) == 2
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"role": "development_validation", "config": config,
        "index_sha256": "wrong", "epochs": 1, "thresholds": [.5] * 6,
        "postprocessing": {"minimum_s": 0, "merge_gap_s": 0}}))
    with pytest.raises(ValueError, match="frozen development selection"):
        train_final(cache, audit, selection, tmp_path / "never-created", authorized=True)
    assert not (tmp_path / "never-created").exists()
    (tmp_path / "events.csv").write_text("changed annotations")
    with pytest.raises(ValueError, match="Stale Lung cache"):
        preflight(cache, audit)


def test_fictional_holdout_is_one_shot_and_merges_windows_without_fitting(tmp_path, monkeypatch):
    config = yaml.safe_load((Path(__file__).parents[1] / "configs/lung_cnn.yaml").read_text())
    root, manifest, candidate = (tmp_path / name for name in ("audio", "manifest", "candidate"))
    for folder in (root, manifest, candidate):
        folder.mkdir()
    audio_path, label_path = root / "test.wav", root / "test_label.txt"
    sf.write(audio_path, np.sin(np.arange(4000 * 6) * .1) * .1, 4000)
    label_path.write_text("0.1 2 inhalation\n2.2 4 exhalation\n0.5 1 wheeze\n")
    rows = [{"split": split, "group": str(i), "sha256": str(i) * 64, "normalized_pcm_sha256": str(i) * 64}
            for i, split in enumerate(("train", "validation"))]
    rows.append({"split": "test", "group": "2", "sha256": digest(audio_path), "normalized_pcm_sha256": "2" * 64,
        "file_path": audio_path.name, "label_path": label_path.name, "label_sha256": digest(label_path),
        "quality": "ok", "duration_s": 6., "valid_end_s": 6., "recording_id": "fictional", "device": "stub"})
    pd.DataFrame(rows).to_csv(manifest / "recordings.csv", index=False)
    (manifest / "audit.json").write_text("{}")
    selection = {"config": config, "role": "train_only_oof", "thresholds": [.5] * 6,
        "postprocessing": {"minimum_s": 0, "merge_gap_s": 0}}
    (candidate / "selection.json").write_text(json.dumps(selection))
    (candidate / "config.json").write_text(json.dumps(config))
    (candidate / "status.json").write_text('{"status":"completed"}')
    (candidate / "model.keras").write_bytes(b"fictional stub")
    np.savez(candidate / "normalization.npz", mean=np.zeros(96), std=np.ones(96))
    (candidate / "source.json").write_text(json.dumps({"audit_sha256": digest(manifest / "audit.json"),
        "selection_sha256": digest(candidate / "selection.json"), "model_role": "final_deployment_candidate",
        "model_sha256": digest(candidate / "model.keras"), "config_sha256": digest(candidate / "config.json"),
        "normalization_sha256": digest(candidate / "normalization.npz")}))
    class Stub:
        def __call__(self, x, training=False):
            assert training is False
            return np.zeros((1, x.shape[1], 6)) + .1
    monkeypatch.setitem(sys.modules, "tensorflow", SimpleNamespace(keras=SimpleNamespace(models=SimpleNamespace(load_model=lambda *a, **k: Stub()))))
    result = evaluate(candidate, root, manifest, model_version="fictional", authorized=True)
    assert result["deployment_eligible"] is False and result["metrics"][0]["fn"] > 0
    assert sum(result["metrics"][0][k] for k in ("tn", "tp", "fp", "fn")) < 372
    assert (manifest / "official-test-opened.json").exists()
    with pytest.raises(ValueError, match="already exists"):
        evaluate(candidate, root, manifest, model_version="fictional", authorized=True)
