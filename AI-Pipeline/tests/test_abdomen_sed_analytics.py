"""Unit tests for Abdomen SED Analytics and Inference Integration (PRD Section 8)."""
from __future__ import annotations

import numpy as np
import pytest

from auriscore.abdomen_sed_analytics import (
    build_unified_abdomen_analysis,
    categorize_bowel_patterns,
    categorize_event_pattern,
    compute_bowel_rate,
    compute_bowel_rate_variability,
)
from auriscore.abdomen_sed_inference import (
    AbdomenSEDBackend,
    BowelEventScorer,
    abdomen_sed_backend_definition,
)
from auriscore.analysis_service import AnalysisService, BackendDefinition


class MockCRNNModel:
    """Mock CRNN SED model outputting deterministic frame probabilities for tests."""

    def predict(self, x: np.ndarray, batch_size: int = 32, verbose: int = 0) -> np.ndarray:
        # x is (N_windows, 40, 126, 1) -> return (N_windows, 126, 1)
        n_windows = x.shape[0]
        preds = np.zeros((n_windows, 126, 1), dtype=np.float32)
        # Create a burst in the middle of each window (frames 40 to 60)
        preds[:, 40:60, 0] = 0.85
        return preds


def test_compute_bowel_rate_clinical_categories() -> None:
    # 1. Normoactive: 15 events in 60 seconds = 15.0 events/min
    events_normo = [{"start_s": i * 4.0, "end_s": i * 4.0 + 0.2} for i in range(15)]
    res_normo = compute_bowel_rate(events_normo, analyzed_duration_s=60.0)
    assert res_normo["valid"] is True
    assert res_normo["events_per_minute"] == 15.0
    assert res_normo["motility_category"] == "normoactive"
    assert "Normoactive" in res_normo["interpretation"]

    # 2. Hypoactive: 2 events in 60 seconds = 2.0 events/min (< 4.0)
    events_hypo = [{"start_s": 10.0, "end_s": 10.2}, {"start_s": 40.0, "end_s": 40.2}]
    res_hypo = compute_bowel_rate(events_hypo, analyzed_duration_s=60.0)
    assert res_hypo["events_per_minute"] == 2.0
    assert res_hypo["motility_category"] == "hypoactive"
    assert "Hypoactive" in res_hypo["interpretation"]

    # 3. Hyperactive: 40 events in 60 seconds = 40.0 events/min (> 32.0)
    events_hyper = [{"start_s": i * 1.5, "end_s": i * 1.5 + 0.1} for i in range(40)]
    res_hyper = compute_bowel_rate(events_hyper, analyzed_duration_s=60.0)
    assert res_hyper["events_per_minute"] == 40.0
    assert res_hyper["motility_category"] == "hyperactive"
    assert "Hyperactive" in res_hyper["interpretation"]

    # 4. Zero duration safeguard
    res_zero = compute_bowel_rate(events_normo, analyzed_duration_s=0.0)
    assert res_zero["valid"] is False


def test_compute_bowel_rate_variability() -> None:
    # 1. Insufficient events (< 2)
    assert compute_bowel_rate_variability([])["available"] is False
    assert compute_bowel_rate_variability([{"start_s": 1.0, "end_s": 1.2}])["available"] is False

    # 2. Regular intervals: onsets at 2.0s, 4.0s, 6.0s (intervals: 2.0s, 2.0s)
    events = [
        {"start_s": 2.0, "end_s": 2.1},
        {"start_s": 4.0, "end_s": 4.15},
        {"start_s": 6.0, "end_s": 6.1},
    ]
    var_res = compute_bowel_rate_variability(events)
    assert var_res["available"] is True
    assert var_res["interval_count"] == 2
    assert var_res["mean_interval_s"] == 2.0
    assert var_res["std_interval_s"] == 0.0
    assert var_res["cv_interval"] == 0.0
    assert var_res["rhythm_regularity"] == "semi_regular"


def test_categorize_bowel_patterns() -> None:
    assert categorize_event_pattern(150.0) == "single_burst"
    assert categorize_event_pattern(450.0) == "multiple_burst"
    assert categorize_event_pattern(1200.0) == "prolonged_sound"

    events = [
        {"start_s": 1.0, "end_s": 1.1, "duration_ms": 100.0, "confidence": 0.90},
        {"start_s": 3.0, "end_s": 3.4, "duration_ms": 400.0, "confidence": 0.88},
        {"start_s": 5.0, "end_s": 6.2, "duration_ms": 1200.0, "confidence": 0.92},
    ]

    p_res = categorize_bowel_patterns(events)
    assert p_res["total_events"] == 3
    assert p_res["single_burst_count"] == 1
    assert p_res["multiple_burst_count"] == 1
    assert p_res["prolonged_sound_count"] == 1
    assert len(p_res["annotated_events"]) == 3
    assert p_res["annotated_events"][0]["pattern"] == "single_burst"
    assert p_res["annotated_events"][1]["pattern"] == "multiple_burst"
    assert p_res["annotated_events"][2]["pattern"] == "prolonged_sound"


def test_build_unified_abdomen_analysis_schema() -> None:
    events = [
        {"start_s": 1.0, "end_s": 1.1, "duration_ms": 100.0, "confidence": 0.90},
        {"start_s": 4.0, "end_s": 4.5, "duration_ms": 500.0, "confidence": 0.85},
    ]
    res = build_unified_abdomen_analysis(events, analyzed_duration_s=10.0)

    # Check top-level contract
    assert res["schema_version"] == "abdomen-analysis-v1"
    assert res["mode"] == "abdomen"
    assert res["quality"]["valid"] is True

    # Crucial: verify that the previously null fields are now completely populated!
    assert res["bowel_events"] is not None
    assert len(res["bowel_events"]) == 2
    assert res["bowel_rate_per_minute"] is not None
    assert res["bowel_rate_per_minute"]["events_per_minute"] == 12.0
    assert res["bowel_rate_variability"] is not None
    assert res["bowel_rate_variability"]["available"] is True
    assert res["pattern_categories"] is not None
    assert res["pattern_categories"]["total_events"] == 2
    assert len(res["limitations"]) > 0


def test_end_to_end_sed_backend(tmp_path) -> None:
    # Setup dummy model path for loader
    dummy_model_path = tmp_path / "mock_sed.keras"
    dummy_model_path.write_bytes(b"mock")

    backend = AbdomenSEDBackend(
        model_path=dummy_model_path,
        loader=lambda _: MockCRNNModel(),
    )

    # Synthetic 6-second audio (3 complete 2.0s windows)
    sr = 8000
    t = np.arange(6 * sr) / float(sr)
    audio = (0.2 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)

    output = backend.analyze(audio, sr)
    assert output.status == "completed"
    assert output.errors == []

    analysis = output.analysis
    assert analysis["schema_version"] == "abdomen-analysis-v1"
    assert analysis["mode"] == "abdomen"
    assert analysis["quality"]["valid"] is True

    # Each window should have detected 1 event -> total 3 events
    events = analysis["bowel_events"]
    assert len(events) == 3
    # Check rate: 3 events in 6 seconds = 30 events/minute
    rate = analysis["bowel_rate_per_minute"]
    assert rate["events_per_minute"] == 30.0
    assert rate["motility_category"] == "normoactive"

    # Variability: 2 intervals between 3 events
    var = analysis["bowel_rate_variability"]
    assert var["available"] is True
    assert var["interval_count"] == 2


def test_short_audio_rejection(tmp_path) -> None:
    dummy_model_path = tmp_path / "mock_sed.keras"
    dummy_model_path.write_bytes(b"mock")

    backend = AbdomenSEDBackend(
        model_path=dummy_model_path,
        loader=lambda _: MockCRNNModel(),
    )

    # Short audio (1.0 second < 2.0 second minimum)
    short_audio = np.zeros(8000, dtype=np.float32)
    output = backend.analyze(short_audio, 8000)
    assert output.status == "failed"
    assert output.analysis["quality"]["valid"] is False
    assert len(output.errors) == 1
    assert output.errors[0].code == "ABDOMEN_AUDIO_INVALID"
