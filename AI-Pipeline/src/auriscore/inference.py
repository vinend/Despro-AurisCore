"""Offline single-recording research screening using the saved training pipeline."""
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
from .features import extract_features
from .io import load_audio
from .preprocessing import preprocess
from .segmentation import segment
from .validation import inspect_audio


def screen(path: Path, model_path: Path) -> dict[str, Any]:
    """Return a screening margin, never a diagnosis or calibrated confidence."""
    quality = inspect_audio(path)
    if not quality["valid"] or "silent" in quality["quality_flag"]:
        return {"screening_result": "unable to screen", "quality": quality, "requires_clinician_review": True}
    # Load only trusted, locally generated joblib files (pickle is executable).
    bundle = joblib.load(model_path)
    config = bundle["config"]
    x, sr = load_audio(path)
    try:
        x = preprocess(x, sr, config)
    except ValueError as exc:
        return {"screening_result": "unable to screen", "reason": str(exc), "quality": quality,
                "requires_clinician_review": True}
    rows = [extract_features(w, config) for _, w, _ in segment(x, config["sample_rate"], config["window_seconds"], config["overlap"])]
    vector = pd.DataFrame(rows)[bundle["feature_columns"]].mean().to_frame().T
    margin = float(bundle["pipeline"].decision_function(vector)[0])
    return {"screening_result": "murmur present screening" if margin >= 0 else "murmur absent screening",
            "decision_margin": margin, "confidence": None,
            "confidence_note": "Margin is uncalibrated; no probability is available",
            "quality": quality, "segments": len(rows), "requires_clinician_review": True,
            "limitation": "Single-recording research output using participant-level training labels; not a diagnosis"}
