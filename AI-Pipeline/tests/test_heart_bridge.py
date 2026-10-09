"""CPU-only subprocess checks for the byte-stream WAV bridge used by WebApp."""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf


SCRIPT = Path(os.environ.get("AURISCORE_HEART_SCRIPT", str(
    Path(__file__).resolve().parents[1] / "scripts" / "analyze_heart_wav.py")))


def wav_bytes(signal: np.ndarray, sample_rate: int = 8000) -> bytes:
    stream = BytesIO()
    sf.write(stream, signal, sample_rate, format="WAV")
    return stream.getvalue()


def call_bridge(data: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, str(SCRIPT), "--stdin"], input=data,
                          capture_output=True, check=False, timeout=30)


def test_stdin_bridge_outputs_versioned_valid_result_without_murmur():
    sample_rate = 8000
    t = np.arange(sample_rate * 8) / sample_rate
    signal = np.zeros_like(t)
    for s1 in np.arange(.4, 7.2, .8):
        for center, amplitude in ((s1, 1.0), (s1 + .3, .7)):
            signal += amplitude * np.sin(2 * np.pi * 65 * (t - center)) * np.exp(
                -.5 * ((t - center) / .016) ** 2)
    response = call_bridge(wav_bytes(signal))
    assert response.returncode == 0, response.stderr.decode(errors="replace")
    result = json.loads(response.stdout)
    assert result["schema_version"] == "heart-analysis-v1"
    assert result["quality"]["valid"] is True
    assert result["rhythm"]["heart_rate_bpm"] == 75
    assert result["murmur"]["status"] == "unavailable"


def test_stdin_bridge_preserves_invalid_audio_without_invented_output():
    response = call_bridge(wav_bytes(np.zeros(8000 * 4)))
    assert response.returncode == 0
    result = json.loads(response.stdout)
    assert result["quality"]["reason"] == "silent_signal"
    assert result["rhythm"] is None
    assert result["cardiac_events"] is None


def test_stdin_bridge_rejects_malformed_wav():
    assert call_bridge(b"not a WAV").returncode != 0


def test_stdin_bridge_rejects_stereo_as_invalid_quality():
    response = call_bridge(wav_bytes(np.zeros((8000 * 4, 2))))
    assert response.returncode == 0
    result = json.loads(response.stdout)
    assert result["quality"]["reason"] == "mono_waveform_required"
    assert result["rhythm"] is None


def test_existing_wav_path_mode_still_works(tmp_path: Path):
    wav_path = tmp_path / "synthetic_silent.wav"
    wav_path.write_bytes(wav_bytes(np.zeros(8000 * 4)))
    response = subprocess.run([sys.executable, str(SCRIPT), "--wav", str(wav_path)],
                              capture_output=True, check=False, timeout=30)
    assert response.returncode == 0
    assert json.loads(response.stdout)["quality"]["reason"] == "silent_signal"
