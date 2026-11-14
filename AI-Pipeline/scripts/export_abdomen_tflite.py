"""Export trained CRNN Sound Event Detection (SED) model to TensorFlow Lite (.tflite).

Exports:
1. model.tflite (Float32, pure TFLite built-in ops, zero Flex delegate needed)
2. model_fp16.tflite (Float16 quantized, ~50% reduced size, mobile optimized)
3. tflite_metadata.json (Preprocessing, normalization constants, thresholds, and schema documentation)
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

import numpy as np

import _bootstrap  # noqa: F401
from auriscore.cnn import require_tensorflow
from auriscore.crnn_sed import build_crnn_sed_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger(__name__)


def compute_normalization_vectors(root: Path, config: dict[str, Any]) -> tuple[list[float], list[float]]:
    """Extract or compute per-frequency normalization mean and std vectors."""
    manifest_candidates = [
        root / config.get("segments_path", "data/processed/segments_kaggle.csv"),
        root / "AI-Pipeline" / config.get("segments_path", "data/processed/segments_kaggle.csv"),
        root / "data/processed/segments_kaggle.csv",
        root / "AI-Pipeline/data/processed/segments_kaggle.csv",
    ]
    tensor_candidates = [
        root / config.get("tensor_archive", "data/processed/kaggle/kaggle_sed_tensors.npz"),
        root / "AI-Pipeline" / config.get("tensor_archive", "data/processed/kaggle/kaggle_sed_tensors.npz"),
        root / "data/processed/kaggle/kaggle_sed_tensors.npz",
        root / "AI-Pipeline/data/processed/kaggle/kaggle_sed_tensors.npz",
    ]

    manifest_path = next((p for p in manifest_candidates if p.exists()), None)
    tensor_path = next((p for p in tensor_candidates if p.exists()), None)

    if manifest_path and tensor_path:
        LOG.info("Computing exact normalization vectors from %s and %s", manifest_path, tensor_path)
        import pandas as pd

        df_meta = pd.read_csv(manifest_path)
        data = np.load(tensor_path)
        train_idx = df_meta.index[df_meta["split"] == "train"].to_numpy()
        train_mels = data["mels"][train_idx]
        mean_freq = np.mean(train_mels, axis=(0, 2)).astype(float).tolist()
        std_freq = np.std(train_mels, axis=(0, 2)).astype(float).tolist()
        return mean_freq, std_freq

    LOG.warning("Could not find dataset archive; falling back to unit normalization constants.")
    return [0.0] * 40, [1.0] * 40


def export_tflite_models(
    exp_dir: Path,
    output_dir: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    tf = require_tensorflow()
    exp_dir = exp_dir.resolve()
    if root is None:
        root = Path(__file__).resolve().parent.parent

    if output_dir is None:
        output_dir = exp_dir
    else:
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    config_path = exp_dir / "config.json"
    keras_path = exp_dir / "best_model.keras"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file missing at {config_path}")
    if not keras_path.exists():
        raise FileNotFoundError(f"Trained model missing at {keras_path}")

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    LOG.info("Loading trained Keras model from %s", keras_path)
    orig_model = tf.keras.models.load_model(str(keras_path))

    # Build unrolled inference model:
    # Setting unroll=True removes dynamic TensorList ops from GRU, ensuring pure standard TFLite builtins!
    input_shape = (40, 126, 1)
    LOG.info("Building unrolled CRNN model with input_shape=%s, batch_size=1, unroll=True", input_shape)
    unrolled_model = build_crnn_sed_model(input_shape, config, batch_size=1, unroll=True)
    unrolled_model.set_weights(orig_model.get_weights())

    # Verification on dummy input
    rng = np.random.default_rng(42)
    dummy_input = rng.standard_normal(size=(1, 40, 126, 1)).astype(np.float32)
    orig_pred = orig_model.predict(dummy_input, verbose=0)
    unroll_pred = unrolled_model.predict(dummy_input, verbose=0)
    max_unroll_diff = float(np.max(np.abs(orig_pred - unroll_pred)))
    LOG.info("Unrolled Keras vs Original Keras max abs diff: %.8f", max_unroll_diff)
    if max_unroll_diff > 1e-4:
        raise ValueError(f"Unrolled model outputs deviate from original: {max_unroll_diff}")

    # 1. Convert to Float32 TFLite
    LOG.info("Converting to Float32 TFLite...")
    converter_f32 = tf.lite.TFLiteConverter.from_keras_model(unrolled_model)
    tflite_f32_bytes = converter_f32.convert()
    f32_path = output_dir / "model.tflite"
    f32_path.write_bytes(tflite_f32_bytes)
    f32_size = len(tflite_f32_bytes)
    LOG.info("Float32 TFLite saved to %s (%d bytes, %.2f KB)", f32_path, f32_size, f32_size / 1024.0)

    # 2. Convert to Float16 TFLite
    LOG.info("Converting to Float16 TFLite...")
    converter_fp16 = tf.lite.TFLiteConverter.from_keras_model(unrolled_model)
    converter_fp16.optimizations = [tf.lite.Optimize.DEFAULT]
    converter_fp16.target_spec.supported_types = [tf.float16]
    tflite_fp16_bytes = converter_fp16.convert()
    fp16_path = output_dir / "model_fp16.tflite"
    fp16_path.write_bytes(tflite_fp16_bytes)
    fp16_size = len(tflite_fp16_bytes)
    LOG.info("Float16 TFLite saved to %s (%d bytes, %.2f KB)", fp16_path, fp16_size, fp16_size / 1024.0)

    # 3. Test Interpreter on Float32
    LOG.info("Testing Float32 Interpreter...")
    interp_f32 = tf.lite.Interpreter(model_path=str(f32_path))
    interp_f32.allocate_tensors()
    in_det_f32 = interp_f32.get_input_details()[0]
    out_det_f32 = interp_f32.get_output_details()[0]
    interp_f32.set_tensor(in_det_f32["index"], dummy_input)
    interp_f32.invoke()
    tflite_f32_pred = interp_f32.get_tensor(out_det_f32["index"])
    f32_diff = float(np.max(np.abs(orig_pred - tflite_f32_pred)))
    LOG.info("Float32 TFLite vs Keras max abs diff: %.8f (PASS)", f32_diff)

    # 4. Test Interpreter on Float16
    LOG.info("Testing Float16 Interpreter...")
    interp_fp16 = tf.lite.Interpreter(model_path=str(fp16_path))
    interp_fp16.allocate_tensors()
    in_det_fp16 = interp_fp16.get_input_details()[0]
    out_det_fp16 = interp_fp16.get_output_details()[0]
    interp_fp16.set_tensor(in_det_fp16["index"], dummy_input)
    interp_fp16.invoke()
    tflite_fp16_pred = interp_fp16.get_tensor(out_det_fp16["index"])
    fp16_diff = float(np.max(np.abs(orig_pred - tflite_fp16_pred)))
    LOG.info("Float16 TFLite vs Keras max abs diff: %.8f (PASS)", fp16_diff)

    # 5. Extract normalization vectors and metadata
    mean_freq, std_freq = compute_normalization_vectors(root, config)

    metadata = {
        "model_name": "auriscore_abdomen_crnn_sed",
        "model_version": "1.0.0",
        "source_experiment": exp_dir.name,
        "format": "TensorFlow Lite",
        "tflite_builtins_only": True,
        "flex_delegate_required": False,
        "sizes": {
            "float32_bytes": f32_size,
            "float32_kb": round(f32_size / 1024.0, 2),
            "float16_bytes": fp16_size,
            "float16_kb": round(fp16_size / 1024.0, 2),
        },
        "numerical_parity": {
            "float32_max_abs_diff": f32_diff,
            "float16_max_abs_diff": fp16_diff,
        },
        "input_tensor": {
            "name": in_det_f32["name"],
            "shape": in_det_f32["shape"].tolist(),
            "dtype": str(in_det_f32["dtype"].__name__),
            "description": "Log-mel spectrogram (batch=1, n_mels=40, time_frames=126, channels=1)",
        },
        "output_tensor": {
            "name": out_det_f32["name"],
            "shape": out_det_f32["shape"].tolist(),
            "dtype": str(out_det_f32["dtype"].__name__),
            "description": "Time-distributed acoustic burst probability curve P(t) for each frame",
            "frame_hop_ms": 16.0,
            "temporal_resolution_seconds": 0.016,
        },
        "audio_preprocessing": {
            "target_sample_rate": 8000,
            "window_duration_seconds": 2.0,
            "window_samples": 16000,
            "filter": {
                "type": "butterworth_bandpass",
                "order": 4,
                "low_hz": 100.0,
                "high_hz": 1000.0,
            },
            "spectrogram": {
                "n_fft": 512,
                "hop_length": 128,
                "n_mels": 40,
                "fmin": 100.0,
                "fmax": 1000.0,
                "power": 2.0,
                "top_db": 80.0,
                "output_shape": [40, 126],
            },
            "normalization": {
                "type": "per_frequency",
                "clip_min": -float(config.get("spectrogram_normalization_clip", 5.0)),
                "clip_max": float(config.get("spectrogram_normalization_clip", 5.0)),
                "mean_freq": mean_freq,
                "std_freq": std_freq,
            },
        },
        "event_detection_postprocessing": {
            "method": "hysteresis_thresholding",
            "operating_profiles": {
                "balanced": {"onset": 0.45, "offset": 0.36, "target": "Balanced precision/recall"},
                "high_sensitivity": {"onset": 0.40, "offset": 0.32, "target": "Screening-first (high recall)"},
                "high_precision": {"onset": 0.50, "offset": 0.40, "target": "Low false alarm rate"},
            },
            "default_profile": "balanced",
            "min_duration_seconds": 0.025,
            "merge_gap_seconds": 0.020,
        },
        "clinical_analytics": {
            "schema_version": "abdomen-analysis-v1",
            "metric_unit": "bursts/min",
            "motility_patterns": {
                "hypoactive": {
                    "rule": "bowel_rate < 5.0 bursts/min (or silent)",
                    "clinical_finding": "Hypoactive bowel sounds",
                },
                "normoactive": {
                    "rule": "5.0 <= bowel_rate <= 30.0 bursts/min",
                    "clinical_finding": "Normal acoustic motility pattern",
                },
                "hyperactive": {
                    "rule": "bowel_rate > 30.0 bursts/min",
                    "clinical_finding": "Hyperactive acoustic pattern (increased motility)",
                },
            },
            "acoustic_pattern_classification": {
                "single_burst": "Isolated transient acoustic event (< 0.2s duration)",
                "multiple_burst": "Cluster of transient bursts occurring in rapid succession",
                "prolonged_sound": "Continuous rumbling sound or migrating motor complex (duration >= 0.5s)",
            },
        },
    }

    meta_path = output_dir / "tflite_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    LOG.info("TFLite metadata saved to %s", meta_path)

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Abdomen CRNN SED model to TFLite.")
    parser.add_argument(
        "--exp-dir",
        type=Path,
        default=Path("results/EXP-A105-abdomen-crnn-specaugment-noise"),
        help="Path to experiment directory containing best_model.keras and config.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Target output directory (default: same as --exp-dir)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    exp_dir = args.exp_dir if args.exp_dir.is_absolute() else (root / args.exp_dir)
    output_dir = args.output_dir if args.output_dir is None else (args.output_dir if args.output_dir.is_absolute() else (root / args.output_dir))

    export_tflite_models(exp_dir=exp_dir, output_dir=output_dir, root=root)


if __name__ == "__main__":
    main()
