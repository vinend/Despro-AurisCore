"""Frozen Lung package tests with fictional evidence; no model fitting."""
import json
from pathlib import Path
import numpy as np
import pytest
import yaml
from auriscore.acquisition_lung import digest, git_blob_digest, verify_download
from auriscore.lung_inference import verify_package, prepare_package, LungInferenceBackend
from auriscore.lung_models import build_model
from auriscore.analysis_service import AnalysisService, BackendDefinition


def package(tmp_path, config, *, real_model=False):
    source = tmp_path / "source"
    source.mkdir()
    config = {**config, "annotation_coverage_verified": True}
    (source / "config.json").write_text(json.dumps(config))
    np.savez(source / "normalization.npz", mean=np.zeros(96), std=np.ones(96))
    if real_model:
        model = build_model((309, 96), config["classes"])
        before = [w.numpy().copy() for w in model.weights]
        model.save(source / "model.keras")
        assert all(np.array_equal(a, b.numpy()) for a, b in zip(before, model.weights))
    else:
        (source / "model.keras").write_bytes(b"fictional engineering stub; not trained")
    evidence = {"model_sha256": digest(source / "model.keras"), "config_sha256": digest(source / "config.json"),
        "normalization_sha256": digest(source / "normalization.npz"), "classes": config["classes"], "group_disjoint": True,
        "grouping": "shifted_recording_date", "patient_disjoint_verified": False, "threshold_selection_role": "train_only_oof",
        "evaluation_role": "locked_official_test", "split_sha256": "a" * 64, "model_version": "fictional-test-only",
        "thresholds": [.5] * len(config["classes"]), "postprocessing": {"minimum_s": 0, "merge_gap_s": 0},
        "metrics": [{"tn": 9, "fp": 1, "fn": 1, "tp": 9, "sensitivity": .9, "specificity": .9, "f1": .9} for _ in config["classes"]]}
    decision = {"status": "approved_for_engineering_inference", "model_role": "final_deployment_model",
        "model_sha256": evidence["model_sha256"], "model_version": evidence["model_version"], "decision_id": "fictional-fixture",
        "engineering_gate": {c: {"sensitivity": .8, "specificity": .8} for c in config["classes"]}}
    (source / "evaluation.json").write_text(json.dumps(evidence))
    (source / "decision.json").write_text(json.dumps(decision))
    destination = tmp_path / "package"
    prepare_package(source, destination, model_version="fictional-test-only")
    return destination


@pytest.fixture
def config():
    return yaml.safe_load((Path(__file__).parents[1] / "configs/lung_cnn.yaml").read_text())


def test_upstream_header_mismatch_requires_pinned_blob(tmp_path):
    path = tmp_path / "volume"
    path.write_bytes(b"source bytes")
    entry = {"name": "volume", "bytes": path.stat().st_size, "sha256": "0" * 64}
    with pytest.raises(ValueError):
        verify_download(path, entry)
    entry["blob_id"] = git_blob_digest(path)
    with pytest.warns(RuntimeWarning):
        verify_download(path, entry)
    assert entry["sha256"] == digest(path) and entry["api_sha256"] == "0" * 64


def test_package_integrity_and_partial_inference(tmp_path, config):
    folder = package(tmp_path, config)
    class Model:
        def __call__(self, x, training=False):
            return np.zeros((1, x.shape[1], 6), dtype=np.float32)
    backend = LungInferenceBackend(folder, loader=lambda _: Model())
    service = AnalysisService(backends=[BackendDefinition("lung", "fixture", lambda: backend,
        model_version="fictional-test-only", requires_model=True, deployment_eligible=True)])
    output = service.analyze_pcm(np.sin(np.arange(8000 * 8) * .1) * .1, 8000, "lung")
    assert output["status"] == "partial" and output["analysis"]["respiratory"]["respiratory_rate_per_minute"] is None
    assert output["analysis"]["sound_events"] == []
    (folder / "model.keras").write_bytes(b"tampered")
    with pytest.raises(ValueError):
        verify_package(folder)


def test_research_models_cannot_be_promoted(tmp_path, config):
    folder = package(tmp_path, config)
    decision = json.loads((folder / "decision.json").read_text())
    decision["model_role"] = "outer_fold_model"
    (folder / "decision.json").write_text(json.dumps(decision))
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["files"]["decision.json"] = {"bytes": (folder / "decision.json").stat().st_size, "sha256": digest(folder / "decision.json")}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_package(folder)


def test_real_saved_untrained_keras_model_runs_inference_without_fitting(tmp_path, config):
    folder = package(tmp_path, config, real_model=True)
    backend = LungInferenceBackend(folder)
    result = backend.analyze(np.sin(np.arange(8000 * 6) * .1) * .1, 8000)
    assert result.analysis["mode"] == "lung" and len(result.analysis["class_scores"]) == 6
