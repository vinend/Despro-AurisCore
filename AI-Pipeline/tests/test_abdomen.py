"""Unit tests for the Abdomen Bowel Sounds pipeline and configurations."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import soundfile as sf

from auriscore.config import load_config
from auriscore.dataset_abdomen import (
    assign_abdomen_splits,
    build_abdomen_manifest,
    extract_subject_info,
    parse_annotation_file,
    segment_abdomen_with_annotations,
)
from auriscore.experiment_queue import load_plan
from auriscore.splitting import assert_no_leakage


def test_abdomen_configs_valid() -> None:
    """Validate that abdomen configs pass all DSP and parameter assertions."""
    root = Path(__file__).resolve().parents[1]
    cnn_cfg = load_config(root / "configs/abdomen_cnn.yaml")
    assert cnn_cfg["model_type"] == "cnn"
    assert cnn_cfg["sample_rate"] == 8000
    assert cnn_cfg["signal_band_max_hz"] == 1000
    assert cnn_cfg["filter_enabled"] is True
    assert cnn_cfg["filter_low_hz"] == 100
    assert cnn_cfg["filter_high_hz"] == 1000

    base_cfg = load_config(root / "configs/abdomen_baseline.yaml")
    assert base_cfg["model_type"] == "svm"
    assert base_cfg["sample_rate"] == 8000

    plan = load_plan(root / "configs/abdomen_cnn_queue.json")
    assert plan["schema_version"] == 1
    assert len(plan["experiments"]) >= 4


def test_parse_annotation_file(tmp_path: Path) -> None:
    """Verify parsing of Figshare annotation file."""
    txt_file = tmp_path / "record_test.txt"
    txt_file.write_text(
        "0.000000\t1.399535\tMB\n"
        "1.562815\t2.075978\tCRS\n"
        "2.869048\t3.102304\tSB\n"
        "6.694444\t6.881049\tHS\n"
        "10.00000\t15.00000\tNONE\n",
        encoding="utf-8",
    )
    events = parse_annotation_file(txt_file)
    assert len(events) == 5
    assert events[0]["event_type"] == "MB"
    assert events[0]["is_active"] is True
    assert events[4]["event_type"] == "NONE"
    assert events[4]["is_active"] is False


def test_extract_subject_info() -> None:
    """Test standard subject/session ID extraction from recording names."""
    sub_id, sess_id, rec_id = extract_subject_info("record_300424001_1.wav")
    assert sub_id == "300424001"
    assert sess_id == "1"
    assert rec_id == "record_300424001_1"

    sub_id2, sess_id2, rec_id2 = extract_subject_info("record_080524002_2")
    assert sub_id2 == "080524002"
    assert sess_id2 == "2"
    assert rec_id2 == "record_080524002_2"


def test_build_abdomen_manifest_and_splits(tmp_path: Path) -> None:
    """Test building manifest and splitting across synthetic subjects."""
    root = tmp_path
    dataset_dir = root / "data/external/bowel-sounds"
    dataset_dir.mkdir(parents=True)

    # Create 5 synthetic recording pairs (WAV + TXT)
    subjects = ["300424001", "080524001", "080524002", "100524001", "150524003"]
    for i, sub in enumerate(subjects, start=1):
        wav_file = dataset_dir / f"record_{sub}_1.wav"
        txt_file = dataset_dir / f"record_{sub}_1.txt"

        # Generate 10 seconds of synthetic audio @ 8000 Hz
        t = np.linspace(0, 10, 80000, endpoint=False)
        audio = 0.1 * np.sin(2 * np.pi * 200 * t)
        sf.write(wav_file, audio, 8000)

        # Write annotation with an active sound
        txt_file.write_text("1.0\t2.5\tSB\n5.0\t6.0\tMB\n", encoding="utf-8")

    manifest = build_abdomen_manifest(root, dataset_dir)
    assert len(manifest) == 5
    assert set(manifest["label"]) == {"Present"}

    cfg = {"seed": 42, "train_fraction": 0.70, "validation_fraction": 0.15, "test_fraction": 0.15}
    split_manifest = assign_abdomen_splits(manifest, cfg)
    assert_no_leakage(split_manifest)

    splits = set(split_manifest["split"])
    assert "train" in splits
    assert "validation" in splits
    assert "test" in splits


def test_segment_abdomen_with_annotations(tmp_path: Path) -> None:
    """Verify that segmenting tags audio windows with active events."""
    root = tmp_path
    dataset_dir = root / "data/external/bowel-sounds"
    dataset_dir.mkdir(parents=True)

    wav_file = dataset_dir / "record_300424001_1.wav"
    txt_file = dataset_dir / "record_300424001_1.txt"

    # Generate 12 seconds of audio @ 8000 Hz
    audio = 0.1 * np.random.default_rng(42).standard_normal(96000)
    sf.write(wav_file, audio, 8000)

    # Active burst between 1.0s and 2.0s
    txt_file.write_text("1.0\t2.0\tSB\n", encoding="utf-8")

    manifest = build_abdomen_manifest(root, dataset_dir)
    manifest["split"] = "train"

    cfg = {
        "sample_rate": 8000,
        "signal_band_max_hz": 1000,
        "window_seconds": 5.0,
        "overlap": 0.5,
        "filter_enabled": True,
        "filter_low_hz": 100,
        "filter_high_hz": 1000,
        "filter_order": 4,
    }

    segments = segment_abdomen_with_annotations(root, cfg, manifest)
    assert len(segments) >= 3
    # The first 5-second window (0-5s) contains the 1.0-2.0s event -> Present
    assert segments.iloc[0]["window_label"] == "Present"
    assert "SB" in segments.iloc[0]["window_events"]
