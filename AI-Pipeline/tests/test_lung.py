"""Lung engineering checks; no training, dataset holdout or model fitting."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import soundfile as sf
import yaml
from auriscore.acquisition_lung import safe_member
from auriscore.dataset_lung import parse_labels, recording_identity, build_manifest, assert_split_integrity
from auriscore.lung_preprocessing import windows, fit_normalization
from auriscore.lung_evaluation import frame_metrics, select_thresholds, event_metrics, merge_predictions
from auriscore.lung_dsp import respiratory_measurements
from auriscore.lung_training import train, preflight
from auriscore.analysis_service import AnalysisService


@pytest.fixture
def config():
    return yaml.safe_load((Path(__file__).parents[1] / "configs/lung_cnn.yaml").read_text())


@pytest.mark.parametrize("name", ["../outside", "C:/outside", "/outside", "folder\\..\\outside"])
def test_archive_paths(name):
    with pytest.raises(ValueError):
        safe_member(name)


def test_labels_are_strict_and_overlaps_preserved(tmp_path):
    label = tmp_path / "label.txt"
    label.write_text("0.1\t1.0\tinhalation\n0.2\t0.3\twheeze\n")
    events = parse_labels(label, 2)
    assert len(events) == 2 and events[1]["label"] == "wheeze"
    label.write_text("I 00:00:01.500 00:00:02.457\nD 00:00:01.500 00:00:02.457\nRhonchi 00:00:03.000 00:00:04.000")
    released = parse_labels(label, 5)
    assert [e["label"] for e in released] == ["inhalation", "crackle", "rhonchi"]
    for line in ["0 1 pneumonia", "0 300 wheeze", "nan 1 crackle", "1 0 rhonchi"]:
        label.write_text(line)
        with pytest.raises(ValueError):
            parse_labels(label, 2)


def test_identity_does_not_invent_littmann_site():
    assert recording_identity("steth_20200101_12_00_00")["location"] == ""
    assert recording_identity("trunc_2020-01-01-12-00-00-L2_3")["location"] == "L2"
    with pytest.raises(ValueError):
        recording_identity("anonymous")


def test_manifest_quarantines_cross_split_dates_and_does_not_parse_test(tmp_path):
    for split, date in [("train", "20200101"), ("test", "20200101"), ("train", "20200102"), ("train", "20200103"), ("train", "20200104")]:
        path = tmp_path / split / f"steth_{date}_12_00_{'01' if split == 'test' else '00'}.wav"
        path.parent.mkdir(exist_ok=True)
        rng = np.random.default_rng(int(date) + 100 * (split == "test"))
        sf.write(path, rng.normal(0, .05, 4000 * 6), 4000)
        path.with_name(path.stem + "_label.txt").write_text("sealed test text" if split == "test" else "0.1 1 inhalation")
    frame, events, audit = build_manifest(tmp_path)
    assert audit["train_test_group_conflicts"] == 1
    assert audit["test_inventory_present"]
    assert len(events) == 4  # Provenance retains quarantined TRAIN labels, never used in a cache.
    assert_split_integrity(frame)


def test_aligned_multi_label_targets_mask_tail_and_unknown_negatives(config):
    audio = np.sin(np.arange(4000 * 6) * .1) * .1
    labels = [{"start_s": .1, "end_s": .2, "label": "wheeze"}, {"start_s": .15, "end_s": .25, "label": "crackle"}]
    blocks = list(windows(audio, 4000, labels, config, valid_end_s=5.8, coverage=True))
    assert len(blocks) == 2
    assert blocks[1]["start_sample"] % config["hop_length"] == 0
    assert np.any((blocks[0]["targets"][:, 2] > 0) & (blocks[0]["targets"][:, 5] > 0))
    assert np.any(blocks[-1]["mask"] == 0)
    unknown = list(windows(audio, 4000, [], config, coverage=False))
    assert all(not np.any(b["mask"]) for b in unknown)
    mean, std = fit_normalization([blocks[0]["features"]], [blocks[0]["mask"]])
    assert mean.shape == std.shape == (96,) and np.all(std > 0)


def test_overlap_merge_and_event_matching_are_one_to_one():
    times, scores = merge_predictions([(0, np.ones((3, 1)), 768), (128, np.zeros((3, 1)), 768)], sample_rate=8000, hop_length=128, n_fft=512)
    assert len(times) == 4 and scores[1, 0] == .5
    event = {"label": "wheeze", "start_s": 1., "end_s": 2.}
    result = event_metrics([event], [event, event])
    assert result["tp"] == 1 and result["fp"] == 1


def test_thresholds_require_support_and_confusion_counts():
    truth = np.array([[0], [0], [1], [1]], np.float32)
    scores = np.array([[.1], [.2], [.8], [.9]])
    mask = np.ones_like(truth)
    threshold = select_thresholds(truth, scores, mask)
    assert frame_metrics(truth, scores, mask, threshold)[0]["f1"] == 1
    with pytest.raises(ValueError):
        select_thresholds(np.zeros_like(truth), scores, mask)


def test_respiration_requires_complete_unambiguous_cycles():
    events = []
    for start in (.5, 3.5, 6.5, 9.5, 12.5):
        events.extend([{"label": "inhalation", "start_s": start, "end_s": start + 1},
                       {"label": "exhalation", "start_s": start + 1.2, "end_s": start + 2.7}])
    result = respiratory_measurements(events, 16)
    assert result["respiratory_rate_per_minute"] == 20 and result["ie_ratio"] == pytest.approx(2 / 3)
    assert respiratory_measurements(events[:2], 15)["respiratory_rate_per_minute"] is None
    events[1]["start_s"] = .6
    assert respiratory_measurements(events, 16)["reason"] == "ambiguous_overlapping_phases"


def test_training_is_denied_before_even_reading_paths():
    with pytest.raises(PermissionError):
        train("missing", "missing", "missing")
    from auriscore.lung_training import train_final
    from auriscore.lung_holdout import evaluate
    with pytest.raises(PermissionError):
        train_final("missing", "missing", "missing", "missing")
    with pytest.raises(PermissionError):
        evaluate("missing", "missing", "missing", model_version="test")


def test_lung_without_model_and_silence_fail_safely():
    service = AnalysisService()
    valid = service.analyze_pcm(np.sin(np.arange(8000 * 6) * .1) * .1, 8000, "lung")
    assert valid["status"] == "unavailable" and valid["analysis"] is None
    silence = service.analyze_pcm(np.zeros(8000 * 6), 8000, "lung")
    assert silence["quality"]["reason"] == "silent_signal"
