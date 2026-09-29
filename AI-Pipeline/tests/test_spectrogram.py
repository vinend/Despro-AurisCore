"""Spectrogram-CNN feature, augmentation, cache, and grouped-fold tests."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from auriscore.augmentation import augment_spectrogram, augment_waveform, cutmix, mixup
from auriscore.config import load_config
from auriscore.cross_validation import assign_grouped_folds
from auriscore.spectrogram import extract_spectrogram_tensor
from auriscore.spectrogram_cache import build_cache_manifest


def improved_config() -> dict:
    path = Path(__file__).resolve().parents[1] / "configs/heart_spectrogram_cnn.yaml"
    config = load_config(path)
    config["spectrogram_normalization"] = "minmax"
    return config


def test_logmel_is_float_image_with_expected_bounds():
    config = improved_config()
    samples = int(config["sample_rate"] * config["window_seconds"])
    time = np.arange(samples) / config["sample_rate"]
    audio = np.sin(2 * np.pi * 120 * time).astype(np.float32)
    tensor = extract_spectrogram_tensor(audio, config)
    assert tensor.shape[0] == config["n_mels"]
    assert tensor.ndim == 2 and tensor.dtype == np.float32
    assert np.isfinite(tensor).all()
    assert 0 <= tensor.min() <= tensor.max() <= 1


def test_logstft_respects_frequency_limits():
    config = improved_config()
    config.update(spectrogram_type="logstft", feature_fmin=100, feature_fmax=1000)
    audio = np.ones(int(config["sample_rate"] * config["window_seconds"]), dtype=np.float32)
    tensor = extract_spectrogram_tensor(audio, config)
    frequencies = np.fft.rfftfreq(config["n_fft"], 1 / config["sample_rate"])
    expected = int(((frequencies >= 100) & (frequencies <= 1000)).sum())
    assert tensor.shape[0] == expected


def test_per_frequency_normalization_requires_training_statistics():
    config = improved_config()
    config["spectrogram_normalization"] = "per_frequency"
    audio = np.ones(int(config["sample_rate"] * config["window_seconds"]), dtype=np.float32)
    with pytest.raises(ValueError, match="training-set mean/std"):
        extract_spectrogram_tensor(audio, config)


def test_training_augmentation_is_seed_reproducible():
    config = improved_config()
    audio = np.linspace(-0.5, 0.5, 4000, dtype=np.float32)
    first = augment_waveform(audio, config, np.random.default_rng(7))
    second = augment_waveform(audio, config, np.random.default_rng(7))
    np.testing.assert_allclose(first, second)
    image = np.ones((32, 64), dtype=np.float32)
    masked = augment_spectrogram(image, config, np.random.default_rng(7))
    assert np.count_nonzero(masked == 0) > 0
    assert np.count_nonzero(image == 0) == 0


def test_mixup_and_cutmix_mix_labels_and_preserve_shape():
    first = np.ones((20, 30, 1), dtype=np.float32)
    second = np.zeros_like(first)
    mixed, label, retained = mixup(first, 1.0, second, 0.0, 0.4, np.random.default_rng(2))
    assert mixed.shape == first.shape and 0 < label < 1 and 0 < retained < 1
    cut, cut_label, retained = cutmix(
        first, 1.0, second, 0.0, 1.0, np.random.default_rng(2)
    )
    assert cut.shape == first.shape and 0 < cut_label < 1 and 0 < retained < 1
    assert np.any(cut == 0) and np.any(cut == 1)


def test_cache_manifest_is_reusable(tmp_path):
    config = improved_config()
    config.update(sample_rate=2000, feature_fmax=1000, window_seconds=1.0, n_fft=128, hop_length=32)
    audio_path = tmp_path / "data/processed/audio/example.npy"
    audio_path.parent.mkdir(parents=True)
    np.save(audio_path, np.sin(np.linspace(0, 20, 2000)).astype(np.float32))
    segments = pd.DataFrame(
        [{
            "segment_id": "recording_0000",
            "subject_group": "subject",
            "recording_id": "recording",
            "split": "train",
            "sha256": "a" * 64,
            "processed_path": "data/processed/audio/example.npy",
            "start_sample": 0,
            "valid_samples": 2000,
            "window_samples": 2000,
        }]
    )
    first = build_cache_manifest(segments, tmp_path, config)
    second = build_cache_manifest(segments, tmp_path, config)
    assert not bool(first.iloc[0].reused)
    assert bool(second.iloc[0].reused)
    assert (tmp_path / first.iloc[0].cache_path).exists()


def test_grouped_folds_keep_participants_exclusive():
    rows = []
    for index in range(20):
        label = "Present" if index % 2 else "Absent"
        for window in range(2):
            rows.append(
                {
                    "subject_group": f"s{index}",
                    "label": label,
                    "split": "train" if index < 16 else "validation",
                    "recording_id": f"r{index}",
                    "window": window,
                }
            )
    assignments = assign_grouped_folds(pd.DataFrame(rows), folds=5, seed=42)
    assert assignments.subject_group.nunique() == 20
    assert assignments.groupby("subject_group").cv_fold.nunique().max() == 1
    assert set(assignments.cv_fold) == set(range(5))


def test_residual_cnn_shape():
    tf = pytest.importorskip("tensorflow")
    from auriscore.cnn import build_cnn_model

    config = improved_config()
    model = build_cnn_model((96, 128, 1), config)
    output = model(tf.zeros((2, 96, 128, 1)), training=False)
    assert tuple(output.shape) == (2, 1)
    assert "residual_se" in model.name

