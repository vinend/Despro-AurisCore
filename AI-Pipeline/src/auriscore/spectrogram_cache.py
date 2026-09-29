"""Content-addressed cache for deterministic, unaugmented spectrogram tensors."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .spectrogram import extract_spectrogram_tensor


FEATURE_FIELDS = (
    "sample_rate",
    "window_seconds",
    "n_fft",
    "hop_length",
    "n_mels",
    "feature_fmin",
    "feature_fmax",
    "cnn_top_db",
    "spectrogram_type",
    "spectrogram_center",
    "spectrogram_normalization",
    "spectrogram_frequency_mean",
    "spectrogram_frequency_std",
    "spectrogram_normalization_clip",
)


def spectrogram_config_digest(config: dict[str, Any]) -> str:
    """Fingerprint only settings that change the tensor values."""
    payload = {field: config.get(field) for field in FEATURE_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def cache_key(row: dict[str, Any], config: dict[str, Any]) -> str:
    payload = {
        "source_sha256": row.get("sha256"),
        "segment_id": row.get("segment_id"),
        "start_sample": int(row["start_sample"]),
        "valid_samples": int(row["valid_samples"]),
        "window_samples": int(row["window_samples"]),
        "feature_config": spectrogram_config_digest(config),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_or_create(
    row: dict[str, Any],
    root: Path,
    config: dict[str, Any],
    loader: Callable[[str], np.ndarray],
) -> tuple[np.ndarray, Path, bool]:
    """Read or atomically create one unaugmented tensor cache entry."""
    key = cache_key(row, config)
    folder = root / "data/processed/spectrogram_cache" / spectrogram_config_digest(config)[:16]
    destination = folder / f"{key}.npy"
    if destination.exists():
        tensor = np.load(destination, allow_pickle=False)
        if tensor.ndim != 2 or not np.isfinite(tensor).all():
            raise ValueError(f"Invalid cached spectrogram: {destination}")
        return np.asarray(tensor, dtype=np.float32), destination, True

    audio = loader(str(root / row["processed_path"]))
    start = int(row["start_sample"])
    valid = int(row["valid_samples"])
    size = int(row["window_samples"])
    signal = np.pad(audio[start:start + valid], (0, size - valid))
    tensor = extract_spectrogram_tensor(signal, config)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.npy")
    np.save(temporary, tensor, allow_pickle=False)
    temporary.replace(destination)
    return tensor, destination, False


def build_cache_manifest(
    segments: pd.DataFrame, root: Path, config: dict[str, Any]
) -> pd.DataFrame:
    """Precompute tensors and save auditable cache metadata."""
    loaded: dict[str, np.ndarray] = {}

    def loader(path: str) -> np.ndarray:
        if path not in loaded:
            loaded[path] = np.load(path, allow_pickle=False)
        return loaded[path]

    rows = []
    for row in segments.to_dict("records"):
        tensor, path, reused = load_or_create(row, root, config, loader)
        rows.append(
            {
                "segment_id": row.get("segment_id"),
                "subject_group": row.get("subject_group"),
                "recording_id": row.get("recording_id"),
                "split": row.get("split"),
                "source_sha256": row.get("sha256"),
                "cache_key": cache_key(row, config),
                "cache_path": path.relative_to(root).as_posix(),
                "frequency_bins": int(tensor.shape[0]),
                "time_frames": int(tensor.shape[1]),
                "reused": bool(reused),
            }
        )
    manifest = pd.DataFrame(rows)
    metadata = root / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(metadata / "spectrogram_cache_manifest.csv", index=False)
    (metadata / "spectrogram_cache.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "representation": "floating-point spectrogram tensor; PNG is not used for training",
                "config_sha256": spectrogram_config_digest(config),
                "entry_count": len(manifest),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def render_previews(manifest: pd.DataFrame, root: Path, count: int = 12) -> list[Path]:
    """Render a small, explicitly non-training PNG set for human QC."""
    if count <= 0 or manifest.empty:
        return []
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    destination = root / "artifacts/figures/spectrogram_previews"
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    for row in manifest.head(count).to_dict("records"):
        tensor = np.load(root / row["cache_path"], allow_pickle=False)
        fig, ax = plt.subplots(figsize=(9, 3))
        image = ax.imshow(tensor, origin="lower", aspect="auto", cmap="magma")
        ax.set(title=str(row["segment_id"]), xlabel="Time frame", ylabel="Frequency bin")
        fig.colorbar(image, ax=ax, label="Normalized value")
        fig.tight_layout()
        path = destination / f"{row['segment_id']}.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths.append(path)
    return paths
