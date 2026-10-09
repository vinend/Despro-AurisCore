"""CPU-only H021 provenance and Heart integration tests; no model inference."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import numpy as np
import pytest

from auriscore.heart_result import analyze_heart, murmur_branch
from auriscore.murmur_inference import (
    EXPERIMENT, H021MurmurAdapter, MurmurRecording, FreezeIntegrityError,
    audit_fold_artifacts, audit_fold_linear_parameters, audit_fold_preprocessing,
    load_h021_freeze,
)

FREEZE = Path(os.environ["AURISCORE_H021_FREEZE"]) if "AURISCORE_H021_FREEZE" in os.environ else (
    Path(__file__).resolve().parents[1] / "analysis" / "HEART-DEVELOPMENT-FREEZE-H021")


def valid_audio() -> np.ndarray:
    t = np.arange(4 * 8000) / 8000
    return .1 * np.sin(2 * np.pi * 65 * t)


def test_real_freeze_is_oof_only_and_manifest_has_five_evaluation_folds():
    manifest = load_h021_freeze(FREEZE)
    assert manifest["deployment"] == {
        "status": "unavailable", "final_model_exists": False,
        "predeclared_ensemble": False,
        "reason": "Only outer-fold evaluation pipelines were produced",
    }
    assert manifest["threshold"]["usable_for_deployment"] is False
    assert [fold["fold"] for fold in manifest["folds"]] == [1, 2, 3, 4, 5]
    assert all({"stage1_model", "normalization", "scaler_logistic"}
               <= set(fold["artifacts"]) for fold in manifest["folds"])
    assert json.loads((FREEZE / "metrics.json").read_text())["eligible_for_external_validation"] is False


def test_missing_or_tampered_freeze_fails_closed(tmp_path: Path):
    with pytest.raises(FreezeIntegrityError, match="Missing"):
        load_h021_freeze(tmp_path)
    for name in ("artifact_manifest.json", "artifact_manifest_sha256.txt",
                 "protocol.json", "config.json", "metrics.json"):
        shutil.copyfile(FREEZE / name, tmp_path / name)
    (tmp_path / "metrics.json").write_text("{}")
    with pytest.raises(FreezeIntegrityError, match="hash mismatch"):
        load_h021_freeze(tmp_path)


def test_fold_scaler_logistic_and_preprocessing_are_auditable(tmp_path: Path):
    model = tmp_path / "best_model.keras"
    model.write_bytes(b"evaluation-only placeholder")
    config = tmp_path / "normalization_config.json"
    config.write_text(json.dumps({"sample_rate": 8000, "window_seconds": 5,
        "overlap": .5, "n_mels": 40, "n_fft": 512, "hop_length": 128,
        "feature_fmax": 2000, "spectrogram_normalization": "per_frequency",
        "spectrogram_frequency_mean": [0.] * 40,
        "spectrogram_frequency_std": [1.] * 40}))
    archive = tmp_path / "scaler_logistic.npz"
    np.savez(archive, scaler_mean=np.zeros(64), scaler_scale=np.ones(64),
             scaler_var=np.ones(64), coef=np.zeros((1, 64)), intercept=np.zeros(1),
             classes=np.array([0, 1]), C=.1)
    assert audit_fold_preprocessing(config)["n_mels"] == 40
    assert audit_fold_linear_parameters(archive) == {"feature_dim": 64,
                                                       "classes": [0, 1], "C": .1}
    import hashlib
    record = lambda path: {"path": path.name,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"folds": [{"fold": 1, "selected_C": .1, "artifacts": {
        "stage1_model": record(model), "normalization": record(config),
        "scaler_logistic": record(archive)}}]}
    assert audit_fold_artifacts(manifest, tmp_path, 1)["linear"]["C"] == .1
    config.write_text("{}")
    with pytest.raises(FreezeIntegrityError, match="hash mismatch"):
        audit_fold_artifacts(manifest, tmp_path, 1)


def test_h021_adapter_never_uses_an_arbitrary_fold_or_oof_threshold():
    adapter = H021MurmurAdapter(FREEZE)
    assert adapter.experiment_id == EXPERIMENT
    for bag in ([MurmurRecording(valid_audio(), 8000)],
                [MurmurRecording(valid_audio(), 8000, "AV"),
                 MurmurRecording(valid_audio(), 8000, "MV")]):
        assert adapter.predict_participant(bag) == {"status": "unavailable"}
    with pytest.raises(ValueError, match="At least one"):
        adapter.predict_participant([])


def test_heart_dsp_survives_unavailable_or_failed_murmur_service():
    audio = valid_audio()
    result = analyze_heart(audio, 8000, murmur_service=H021MurmurAdapter(FREEZE))
    assert result["schema_version"] == "heart-analysis-v1"
    assert result["quality"]["valid"] is True
    assert result["rhythm"] is not None and result["cardiac_events"] is not None
    assert result["murmur"]["status"] == "unavailable"
    assert result["murmur"]["probability"] is None
    assert result["murmur"]["threshold"] is None

    class FailingService:
        def predict_participant(self, recordings):
            raise RuntimeError("model unavailable")

    assert analyze_heart(audio, 8000, murmur_service=FailingService())["murmur"]["status"] == "unavailable"

    class MalformedService:
        def predict_participant(self, recordings):
            return {"status": "available", "probability": float("nan")}

    assert analyze_heart(audio, 8000, murmur_service=MalformedService())["murmur"]["status"] == "unavailable"


def test_invalid_audio_skips_murmur_and_available_result_remains_generic():
    class SpyService:
        called = False

        def predict_participant(self, recordings):
            self.called = True
            return {"status": "available", "probability": .8,
                    "threshold": .3, "model_version": "future-model"}

    service = SpyService()
    invalid = analyze_heart(np.zeros(32000), 8000, murmur_service=service)
    assert service.called is False
    assert invalid["murmur"] is None and invalid["rhythm"] is None
    available = analyze_heart(valid_audio(), 8000, murmur_service=service)
    assert service.called is True
    assert available["murmur"]["label"] == "present"
    assert available["murmur"]["model_version"] == "future-model"
    assert murmur_branch(.1, .3, "another-model")["label"] == "absent"
    with pytest.raises(ValueError, match="either"):
        analyze_heart(valid_audio(), 8000, murmur={"status": "unavailable"},
                      murmur_service=service)
