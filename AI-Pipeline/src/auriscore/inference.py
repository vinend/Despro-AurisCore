"""Offline single-recording research screening using the saved training pipeline."""
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
from .features import extract_features, extract_logmel_tensor
from .io import load_audio
from .preprocessing import preprocess
from .segmentation import segment
from .validation import inspect_audio


def screen(path: Path, model_path: Path) -> dict[str, Any]:
    """Return a screening margin, never a diagnosis or calibrated confidence."""
    quality = inspect_audio(path)
    if not quality["valid"] or "silent" in quality["quality_flag"]:
        return {"screening_result": "unable to screen", "quality": quality, "requires_clinician_review": True}
    if model_path.suffix == ".keras":
        metadata_path = model_path.with_suffix(".json")
        if not metadata_path.exists():
            raise ValueError(f"Missing CNN metadata: {metadata_path}")
        import json
        from .cnn import require_tensorflow
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        config = metadata["config"]
    else:
        # Load only trusted, locally generated joblib files (pickle is executable).
        bundle = joblib.load(model_path)
        config = bundle["config"]
    x, sr = load_audio(path)
    try:
        x = preprocess(x, sr, config)
    except ValueError as exc:
        return {"screening_result": "unable to screen", "reason": str(exc), "quality": quality,
                "requires_clinician_review": True}
    windows = [w for _, w, _ in segment(x, config["sample_rate"], config["window_seconds"], config["overlap"])]
    if model_path.suffix == ".keras":
        tf = require_tensorflow()
        model = tf.keras.models.load_model(model_path)
        tensors = np.stack([extract_logmel_tensor(window, config) for window in windows])[..., np.newaxis]
        score = float(model.predict(tensors, verbose=0).reshape(-1).mean())
        threshold = float(metadata["decision_threshold"])
        return {"screening_result": "murmur present screening" if score >= threshold else "murmur absent screening",
                "model_kind": "cnn_logmel", "score": score, "decision_threshold": threshold,
                "confidence": None,
                "confidence_note": "Sigmoid score is not calibrated as a clinical probability",
                "quality": quality, "segments": len(windows), "requires_clinician_review": True,
                "limitation": "Single-recording research output using participant-level training labels; not a diagnosis"}
    rows = [extract_features(window, config) for window in windows]
    vector = pd.DataFrame(rows)[bundle["feature_columns"]].mean().to_frame().T
    margin = float(bundle["pipeline"].decision_function(vector)[0])
    threshold = float(bundle.get("decision_threshold", 0.0))
    return {"screening_result": "murmur present screening" if margin >= threshold else "murmur absent screening",
            "decision_margin": margin, "confidence": None,
            "decision_threshold": threshold,
            "confidence_note": "Margin is uncalibrated; no probability is available",
            "model_kind": "svm", "quality": quality, "segments": len(rows), "requires_clinician_review": True,
            "limitation": "Single-recording research output using participant-level training labels; not a diagnosis"}
