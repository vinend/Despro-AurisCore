"""Unit tests for Abdomen TFLite model artifacts and export pipeline."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import numpy as np

from auriscore.cnn import require_tensorflow
from auriscore.crnn_sed import build_crnn_sed_model

EXP_DIR = Path(__file__).resolve().parent.parent / "results" / "EXP-A105-abdomen-crnn-specaugment-noise"


def test_unrolled_crnn_model_build():
    """Verify build_crnn_sed_model supports static unrolling for TFLite."""
    tf = require_tensorflow()
    config = {
        "crnn_architecture": "residual_se",
        "cnn_se_ratio": 8,
        "crnn_gru_units": 64,
        "cnn_dropout": 0.25,
    }
    model = build_crnn_sed_model((40, 126, 1), config, batch_size=1, unroll=True)
    assert model is not None
    assert model.input_shape == (1, 40, 126, 1)
    assert model.output_shape == (1, 126, 1)


@pytest.mark.skipif(not (EXP_DIR / "model.tflite").exists(), reason="EXP-A105 model.tflite not yet exported")
def test_tflite_models_load_and_run():
    """Verify exported TFLite models load with pure standard runtime and run inference."""
    tf = require_tensorflow()

    f32_path = EXP_DIR / "model.tflite"
    fp16_path = EXP_DIR / "model_fp16.tflite"

    assert f32_path.exists(), f"Missing {f32_path}"
    assert fp16_path.exists(), f"Missing {fp16_path}"

    dummy_input = np.zeros((1, 40, 126, 1), dtype=np.float32)

    # Test Float32 model
    interp_f32 = tf.lite.Interpreter(model_path=str(f32_path))
    interp_f32.allocate_tensors()
    in_det_f32 = interp_f32.get_input_details()[0]
    out_det_f32 = interp_f32.get_output_details()[0]

    assert list(in_det_f32["shape"]) == [1, 40, 126, 1]
    assert list(out_det_f32["shape"]) == [1, 126, 1]

    interp_f32.set_tensor(in_det_f32["index"], dummy_input)
    interp_f32.invoke()
    out_f32 = interp_f32.get_tensor(out_det_f32["index"])

    assert out_f32.shape == (1, 126, 1)
    assert np.all(np.isfinite(out_f32))
    assert np.all(out_f32 >= 0.0) and np.all(out_f32 <= 1.0)

    # Test Float16 model
    interp_fp16 = tf.lite.Interpreter(model_path=str(fp16_path))
    interp_fp16.allocate_tensors()
    in_det_fp16 = interp_fp16.get_input_details()[0]
    out_det_fp16 = interp_fp16.get_output_details()[0]

    interp_fp16.set_tensor(in_det_fp16["index"], dummy_input)
    interp_fp16.invoke()
    out_fp16 = interp_fp16.get_tensor(out_det_fp16["index"])

    assert out_fp16.shape == (1, 126, 1)
    assert np.all(np.isfinite(out_fp16))
    assert np.all(out_fp16 >= 0.0) and np.all(out_fp16 <= 1.0)

    # Parity between Float32 and Float16
    max_diff = float(np.max(np.abs(out_f32 - out_fp16)))
    assert max_diff < 0.01, f"Float32 vs Float16 difference too large: {max_diff}"


@pytest.mark.skipif(not (EXP_DIR / "tflite_metadata.json").exists(), reason="EXP-A105 tflite_metadata.json not found")
def test_tflite_metadata_complete():
    """Verify tflite_metadata.json contains complete mobile integration specs."""
    meta_path = EXP_DIR / "tflite_metadata.json"
    assert meta_path.exists()

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["format"] == "TensorFlow Lite"
    assert meta["tflite_builtins_only"] is True
    assert meta["flex_delegate_required"] is False

    # Check preprocessing spec
    audio_pre = meta["audio_preprocessing"]
    assert audio_pre["target_sample_rate"] == 8000
    assert audio_pre["window_duration_seconds"] == 2.0
    assert audio_pre["window_samples"] == 16000

    norm = audio_pre["normalization"]
    assert norm["type"] == "per_frequency"
    assert len(norm["mean_freq"]) == 40
    assert len(norm["std_freq"]) == 40
    assert all(np.isfinite(norm["mean_freq"]))
    assert all(s > 0 for s in norm["std_freq"])

    # Check postprocessing
    post = meta["event_detection_postprocessing"]
    assert post["method"] == "hysteresis_thresholding"
    assert "balanced" in post["operating_profiles"]
    assert post["operating_profiles"]["balanced"]["onset"] == 0.45
    assert post["operating_profiles"]["balanced"]["offset"] == 0.36

    # Check clinical analytics schema
    clinical = meta["clinical_analytics"]
    assert clinical["schema_version"] == "abdomen-analysis-v1"
    assert "motility_patterns" in clinical
    assert "hypoactive" in clinical["motility_patterns"]
    assert "normoactive" in clinical["motility_patterns"]
    assert "hyperactive" in clinical["motility_patterns"]
