"""Audio and table IO without modifying original recordings."""
from pathlib import Path
import numpy as np
import pandas as pd
import soundfile as sf


def load_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Load float64 samples preserving channels; reject empty/nonfinite audio."""
    audio, sr = sf.read(path, dtype="float64", always_2d=True)
    if audio.size == 0:
        raise ValueError("Empty audio")
    if sr <= 0 or not np.isfinite(audio).all():
        raise ValueError("Invalid sample rate or NaN/Inf audio")
    return audio, sr


def read_table(path: Path) -> pd.DataFrame:
    """Preserve numeric-looking IDs as strings and missing values as blanks."""
    return pd.read_csv(path, keep_default_na=False, dtype={
        "subject_id": str, "recording_id": str, "subject_group": str,
        "additional_id": str,
    })
