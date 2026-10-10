"""Temporal localization engineering tests with fictional events and frozen stubs."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import soundfile as sf
import yaml

from auriscore.acquisition_lung import digest
from auriscore.lung_localization import localize_frames, localize_wav, evaluate_development_localization, predict_frames


def test_adjacent_frames_merge_without_float_fragmentation_and_classes_overlap():
    times = .032 + np.arange(100) * .016
    scores = np.ones((100, 2)) * .8
    events = localize_frames(times, scores, ["inhalation", "wheeze"], [.5, .5], hop_s=.016, duration_s=2)
    assert len(events) == 2
    assert events[0]["start_s"] == pytest.approx(.024)
    assert events[0]["end_s"] == pytest.approx(1.624)
    assert events[0]["positive_frame_count"] == 100
    assert events[0]["mean_positive_frame_score"] == pytest.approx(.8)
    assert events[0]["duration_s"] == pytest.approx(1.6)


def test_gap_minimum_duration_missing_frames_and_threshold_equality():
    times = np.arange(6) * .1 + .05
    scores = np.array([[.5], [.5], [.1], [.5], [.1], [.5]])
    first = localize_frames(times, scores, ["crackle"], [.5], hop_s=.1, duration_s=.6, minimum_s=.15)
    assert len(first) == 1 and first[0]["end_s"] == pytest.approx(.2)
    merged = localize_frames(times, scores, ["crackle"], [.5], hop_s=.1, duration_s=.6, merge_gap_s=.1)
    assert len(merged) == 1 and merged[0]["end_s"] == .6
    assert merged[0]["positive_frame_count"] == 4
    missing = localize_frames(np.array([.05, .25]), np.ones((2, 1)), ["crackle"], [.5],
                              hop_s=.1, duration_s=.3, merge_gap_s=1)
    assert len(missing) == 2  # No extrapolation across a hole in the frame timeline.


@pytest.mark.parametrize("times,scores", [([.2, .1], [[.5], [.5]]), ([.1], [[np.nan]]), ([.1], [[1.1]]), ([-.1], [[.5]])])
def test_invalid_frames_rejected(times, scores):
    with pytest.raises(ValueError):
        localize_frames(np.array(times), np.array(scores), ["wheeze"], [.5], hop_s=.1, duration_s=1)


@pytest.fixture
def config():
    return yaml.safe_load((Path(__file__).parents[1] / "configs/lung_cnn.yaml").read_text())


class FrozenModel:
    def __call__(self, x, training=False):
        assert training is False
        scores = np.zeros((1, x.shape[1], 6), dtype=np.float32)
        scores[:, 20:30, 2] = .8
        return scores


def completed(tmp_path, config):
    experiment = tmp_path / "experiment"
    folder = experiment / "fold-0"
    folder.mkdir(parents=True)
    (experiment / "source.json").write_text(json.dumps({"evaluation_role": "development_only", "config": config}))
    (experiment / "status.json").write_text(json.dumps({"status": "completed"}))
    (folder / "evaluation.json").write_text(json.dumps({"role": "development_only", "classes": config["classes"],
                                                       "thresholds": [.5] * 6, "groups": ["g1"]}))
    (folder / "model.keras").write_bytes(b"fictional frozen stub")
    np.savez(folder / "normalization.npz", mean=np.zeros(96), std=np.ones(96))
    return experiment, folder


def test_wav_to_onset_offset_and_frames_with_research_provenance(tmp_path, config):
    experiment, _ = completed(tmp_path, config)
    wav = tmp_path / "lung.wav"
    sf.write(wav, np.sin(np.arange(8000 * 5) * .1) * .1, 8000)
    report = localize_wav(experiment, wav, loader=lambda _: FrozenModel())
    assert report["deployment_eligible"] is report["training_started"] is False
    assert report["official_test_labels_opened"] is False
    assert len(report["sound_events"]) == 1
    assert report["sound_events"][0]["label"] == "wheeze"
    assert report["sound_events"][0]["start_s"] == pytest.approx(.344)
    assert report["sound_events"][0]["end_s"] == pytest.approx(.504)
    assert len(report["frames"]["times_s"]) == 309
    assert report["respiratory"]["respiratory_rate_per_minute"] is None
    json.dumps(report, allow_nan=False)


def test_quality_and_unfinished_experiment_rejected_before_model_loading(tmp_path, config):
    experiment, _ = completed(tmp_path, config)
    wav = tmp_path / "silence.wav"
    sf.write(wav, np.zeros(8000 * 5), 8000)
    def denied(_):
        pytest.fail("Must not load a model for rejected input")
    with pytest.raises(ValueError, match="silent_signal"):
        localize_wav(experiment, wav, loader=denied)
    (experiment / "status.json").write_text(json.dumps({"status": "running"}))
    with pytest.raises(ValueError, match="Completed development"):
        localize_wav(experiment, wav, loader=denied)


def test_window_overlap_is_averaged_tail_dropped_and_non_temporal_model_rejected(config):
    audio = np.sin(np.arange(8000 * 8) * .1) * .1
    times, scores = predict_frames(audio, 8000, config, np.zeros(96), np.ones(96), FrozenModel())
    assert len(np.unique(times)) == len(times)
    assert np.diff(times).min() == pytest.approx(.016)
    assert times[-1] + .032 <= 8
    assert scores.shape == (len(times), 6)
    with pytest.raises(ValueError, match="Invalid temporal"):
        predict_frames(audio, 8000, config, np.zeros(96), np.ones(96), lambda *a, **kw: np.zeros((1, 6)))


def test_saved_prediction_evaluation_merges_recording_and_rejects_misalignment(tmp_path, config, monkeypatch):
    experiment, folder = completed(tmp_path, config)
    cache = tmp_path / "cache"
    cache.mkdir()
    config = {**config}
    audit = tmp_path / "audit.json"
    audit.write_text("{}")
    rows = []
    blocks, prediction_order = [], []
    # Two overlapping cached windows for one fictional held-out recording.
    for i, start in enumerate((0, 128)):
        name = f"block-{i}.npz"
        truth = np.zeros((4, 6))
        mask = np.ones_like(truth)
        scores = np.zeros_like(truth)
        scores[:, 2] = .8
        np.savez(cache / name, targets=truth, mask=mask, start_sample=start)
        blocks.append((truth, scores, mask))
        rows.append({"file": name, "group": "g1", "recording_id": "fictional", "split": "validation"})
        prediction_order.append({"file": name, "group": "g1", "fold": 0})
    pd.DataFrame(rows).to_csv(cache / "index.csv", index=False)
    pd.DataFrame([{"recording_id": "fictional", "group": "g1", "split": "validation", "valid_end_s": 5,
                   "device": "fictional"}]).to_csv(tmp_path / "recordings.csv", index=False)
    pd.DataFrame([{"recording_id": "fictional", "label": "wheeze", "start_s": .024, "end_s": .104}]).to_csv(tmp_path / "events.csv", index=False)
    (experiment / "source.json").write_text(json.dumps({"evaluation_role": "development_only", "config": config,
                                                        "index_sha256": digest(cache / "index.csv"), "audit_sha256": digest(audit)}))
    (experiment / "prediction_index.json").write_text(json.dumps(prediction_order))
    saved = {key: np.concatenate([block[i] for block in blocks]) for i, key in enumerate(("truth", "scores", "mask"))}
    np.savez(folder / "development_predictions.npz", **saved)
    monkeypatch.setattr("auriscore.lung_localization.preflight", lambda *_: (config, pd.DataFrame(rows)))
    result = evaluate_development_localization(cache, audit, experiment)
    assert result["event_metrics"]["wheeze"]["tp"] == 1
    assert result["event_metrics"]["wheeze"]["fp"] == 0
    assert result["event_metrics"]["wheeze"]["onset_mae_s"] == pytest.approx(0)
    assert result["event_metrics"]["wheeze"]["offset_mae_s"] == pytest.approx(0)
    assert result["event_metrics"]["inhalation"]["onset_mae_s"] is None
    assert len(result["recordings"][0]["sound_events"]) == 1
    assert result["recordings"][0]["sound_events"][0]["positive_frame_count"] == 5
    saved["truth"][0, 0] = 1
    np.savez(folder / "development_predictions.npz", **saved)
    with pytest.raises(ValueError, match="misaligned"):
        evaluate_development_localization(cache, audit, experiment)
    (experiment / "prediction_index.json").write_text(json.dumps(prediction_order[:1]))
    with pytest.raises(ValueError, match="every held-out"):
        evaluate_development_localization(cache, audit, experiment)


def test_boundary_errors_are_reported_only_for_one_to_one_matches():
    from auriscore.lung_evaluation import event_metrics
    reference = [{"label": "wheeze", "start_s": 1., "end_s": 2.}]
    predicted = [{"label": "wheeze", "start_s": 1.05, "end_s": 1.96}]
    result = event_metrics(reference, predicted)
    assert result["onset_mae_s"] == pytest.approx(.05)
    assert result["offset_mae_s"] == pytest.approx(.04)
    assert result["duration_mae_s"] == pytest.approx(.09)
    assert event_metrics(reference, [])["onset_mae_s"] is None
