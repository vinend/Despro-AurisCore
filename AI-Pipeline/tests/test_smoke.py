"""Synthetic end-to-end tests; generated metrics stay inside pytest temp roots."""
import json
import numpy as np
import pytest
import soundfile as sf
import joblib
from auriscore.pipeline import run, stamp
from auriscore.io import read_table
from auriscore.inference import screen
from auriscore.holdout import evaluate_cnn_holdout, evaluate_svm_holdout, lock_holdout


def test_end_to_end_synthetic(tmp_path, config):
    folder = tmp_path / config["dataset_dir"] / "training_data"
    folder.mkdir(parents=True)
    rng = np.random.default_rng(1729)
    for index in range(24):
        sid = str(1000 + index)
        label = "Present" if index % 2 else "Absent"
        name = f"{sid}_AV.wav"
        t = np.arange(22000) / 4000
        x = .3 * np.sin(2 * np.pi * (90 + index) * t) + rng.normal(0, .01, len(t))
        sf.write(folder / name, x, 4000)
        (folder / f"{sid}.txt").write_text(
            f"{sid} 1 4000\nAV {sid}_AV.hea {name} {sid}_AV.tsv\n"
            f"#Murmur: {label}\n#Outcome: Abnormal\n#Additional ID: nan\n", encoding="utf-8")
    result = run(tmp_path, config, synthetic=True)
    assert result["status"] == "synthetic_smoke_only"
    assert (tmp_path / "artifacts/figures/validation_confusion_matrix.png").exists()
    model_path = tmp_path / "artifacts/models/heart_svm.joblib"
    bundle = joblib.load(model_path)
    assert "decision_threshold" in bundle
    features = read_table(tmp_path / "data/processed/features.csv")
    train = features[features.split == "train"]
    assert bundle["pipeline"].named_steps["scaler"].n_samples_seen_ == train.recording_id.nunique()
    np.testing.assert_allclose(bundle["pipeline"].named_steps["scaler"].mean_, train[bundle["feature_columns"]].mean(), rtol=1e-6, atol=1e-8)
    output = screen(folder / "1000_AV.wav", model_path)
    assert output["confidence"] is None and output["requires_clinician_review"]
    metrics = json.loads((tmp_path / "artifacts/metrics/baseline_metrics.json").read_text())
    assert metrics["status"] == "synthetic_smoke_only"
    assert metrics["holdout"]["evaluated"] is False and "test" not in metrics
    assert not (tmp_path / "artifacts/metrics/test_predictions.csv").exists()
    locked_config = dict(config, holdout_status="locked_unseen")
    lock_holdout(read_table(tmp_path / "metadata/dataset_manifest.csv"), locked_config, tmp_path)
    final = evaluate_svm_holdout(features, locked_config, tmp_path, model_path)
    assert final["status"] == "final_locked_holdout_evaluation"
    with pytest.raises(ValueError, match="already evaluated"):
        evaluate_svm_holdout(features, locked_config, tmp_path, model_path)
    config["seed"] = 99
    with pytest.raises(ValueError, match="Stale"):
        stamp(tmp_path, config, "features", verify=True)


def test_missing_dataset_actionable(tmp_path, config):
    with pytest.raises(FileNotFoundError, match="download_dataset.py"):
        run(tmp_path, config)


def test_cnn_end_to_end_synthetic(tmp_path, cnn_config):
    pytest.importorskip("tensorflow")
    cnn_config.update(cnn_epochs=1, cnn_patience=1, cnn_batch_size=8, cnn_verbose=0)
    folder = tmp_path / cnn_config["dataset_dir"] / "training_data"
    folder.mkdir(parents=True)
    rng = np.random.default_rng(2026)
    for index in range(24):
        sid = str(2000 + index)
        label = "Present" if index % 2 else "Absent"
        name = f"{sid}_AV.wav"
        t = np.arange(20000) / 4000
        frequency = 90 if label == "Absent" else 180
        x = 0.3 * np.sin(2 * np.pi * frequency * t) + rng.normal(0, 0.01, len(t))
        sf.write(folder / name, x, 4000)
        (folder / f"{sid}.txt").write_text(
            f"{sid} 1 4000\nAV {sid}_AV.hea {name} {sid}_AV.tsv\n"
            f"#Murmur: {label}\n#Outcome: Abnormal\n#Additional ID: nan\n",
            encoding="utf-8",
        )
    result = run(tmp_path, cnn_config, synthetic=True)
    assert result["status"] == "synthetic_smoke_only"
    assert result["holdout"]["evaluated"] is False and "test" not in result
    model_path = tmp_path / "artifacts/models/heart_cnn.keras"
    assert model_path.exists() and model_path.with_suffix(".json").exists()
    output = screen(folder / "2000_AV.wav", model_path)
    assert output["model_kind"] == "cnn_logmel"
    assert output["confidence"] is None and output["requires_clinician_review"]
    locked_config = dict(cnn_config, holdout_status="locked_unseen")
    lock_holdout(read_table(tmp_path / "metadata/dataset_manifest.csv"), locked_config, tmp_path)
    final = evaluate_cnn_holdout(
        read_table(tmp_path / "data/processed/segments.csv"), locked_config, tmp_path, model_path
    )
    assert final["status"] == "final_locked_holdout_evaluation"
