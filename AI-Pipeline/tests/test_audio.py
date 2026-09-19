"""Synthetic signals test software only, never screening performance."""
import numpy as np
import pytest
import soundfile as sf
from auriscore.io import load_audio
from auriscore.preprocessing import preprocess, to_mono
from auriscore.segmentation import segment
from auriscore.features import extract_features, extract_logmel_tensor
from auriscore.validation import inspect_audio


def test_audio_loading_and_mono(tmp_path):
    path = tmp_path / "stereo.wav"
    sf.write(path, np.column_stack([np.full(100, .2), np.full(100, .4)]), 4000, subtype="FLOAT")
    audio, sr = load_audio(path)
    assert sr == 4000 and audio.shape == (100, 2)
    np.testing.assert_allclose(to_mono(audio), .3, atol=1e-7)
    assert inspect_audio(path)["channels"] == 2


@pytest.mark.parametrize("sr", [4000, 8000, 44100])
def test_resampling(sr, config):
    x = preprocess(.2 + np.sin(2 * np.pi * 200 * np.arange(sr) / sr), sr, config)
    assert x.shape == (8000,) and abs(x.mean()) < 1e-5
    assert np.max(np.abs(x)) <= 1.00001
    assert abs(np.argmax(np.abs(np.fft.rfft(x))) - 200) <= 1


def test_segmentation():
    windows = list(segment(np.arange(80000), 8000))
    assert [s for s, _, _ in windows] == [0, 20000, 40000]
    assert all(len(w) == 40000 and valid == 40000 for _, w, valid in windows)
    short = list(segment(np.ones(1000), 8000))
    assert short[0][2] == 1000 and np.count_nonzero(short[0][1]) == 1000
    assert len(list(segment(np.ones(41000), 8000))) == 1
    with pytest.raises(ValueError):
        list(segment(np.array([]), 8000))


def test_feature_shape(config):
    x = np.sin(2 * np.pi * 80 * np.arange(40000) / 8000).astype(np.float32)
    features = extract_features(x, config)
    assert len(features) == (13 + 13 + 40 + 3) * 5 + 4
    assert np.isfinite(list(features.values())).all()
    assert features == extract_features(x, config)
    tensor = extract_logmel_tensor(x, config)
    assert tensor.shape[0] == config["n_mels"] and tensor.ndim == 2
    assert np.isfinite(tensor).all() and tensor.min() >= 0 and tensor.max() <= 1


def test_corrupt_empty_nonfinite_audio(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not audio")
    assert not inspect_audio(broken)["valid"]
    assert not inspect_audio(tmp_path / "missing.wav")["valid"]
    empty = tmp_path / "empty.wav"
    sf.write(empty, np.array([]), 8000)
    assert inspect_audio(empty)["empty"]
    with pytest.raises(ValueError, match="Empty"):
        load_audio(empty)
    nonfinite = tmp_path / "nan.wav"
    sf.write(nonfinite, np.array([np.nan, np.inf]), 8000, subtype="FLOAT")
    assert not inspect_audio(nonfinite)["valid"]
    with pytest.raises(ValueError, match="NaN/Inf"):
        load_audio(nonfinite)


def test_silence_and_clipping(tmp_path, config):
    path = tmp_path / "clipped.wav"
    sf.write(path, np.ones(8000), 8000)
    assert inspect_audio(path)["clipping_ratio"] == 1
    with pytest.raises(ValueError, match="Silent"):
        preprocess(np.ones(8000), 8000, config)


def test_filter_option(config):
    config["filter_enabled"] = True
    x = np.sin(2 * np.pi * 100 * np.arange(8000) / 8000)
    assert np.isfinite(preprocess(x, 8000, config)).all()
