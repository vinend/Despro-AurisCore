"""Prepare real hardware heart and ambient audio as Hard Negative training segments."""
from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import butter, sosfiltfilt
import soundfile as sf
import librosa

LOG = logging.getLogger(__name__)


def prepare_hard_negatives(
    source_dir: Path = Path("D:/Despro/Prapemrosesan_Tubuh"),
    output_audio_dir: Path = Path("AI-Pipeline/data/processed/hard_negatives"),
    existing_segments_path: Path = Path("AI-Pipeline/data/processed/segments.csv"),
    output_segments_path: Path = Path("AI-Pipeline/data/processed/segments_train_hn.csv"),
    target_sr: int = 8000,
    window_sec: float = 5.0,
    overlap: float = 0.50,
) -> pd.DataFrame:
    source_dir = source_dir.resolve()
    output_audio_dir = output_audio_dir.resolve()
    existing_segments_path = existing_segments_path.resolve()
    output_segments_path = output_segments_path.resolve()

    output_audio_dir.mkdir(parents=True, exist_ok=True)

    # 1. Bandpass filter 100-1000 Hz (same as Abdomen pipeline)
    sos = butter(4, [100.0, 1000.0], btype="bandpass", fs=target_sr, output="sos")

    wav_files = sorted(list(source_dir.glob("*_organ_dokter_HP20Hz_kausal.wav")))
    if not wav_files:
        raise FileNotFoundError(f"No *_organ_dokter_HP20Hz_kausal.wav files found in {source_dir}")

    print(f"Found {len(wav_files)} hardware audio files in {source_dir}.")
    hn_segments: list[dict[str, Any]] = []

    window_samples = int(window_sec * target_sr)  # 40,000
    hop_samples = int(window_samples * (1.0 - overlap))  # 20,000

    for idx, wav_path in enumerate(wav_files, 1):
        data, sr = sf.read(str(wav_path))
        if data.ndim > 1:
            data = data[:, 0]
        # Resample from 16 kHz to 8 kHz
        if sr != target_sr:
            data_8k = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        else:
            data_8k = data

        # Apply bandpass filter
        filtered = sosfiltfilt(sos, data_8k).astype(np.float32)

        # Save .npy file
        rec_id = wav_path.stem
        npy_filename = f"{rec_id}.npy"
        npy_full_path = output_audio_dir / npy_filename
        np.save(npy_full_path, filtered)
        rel_npy_path = f"data/processed/hard_negatives/{npy_filename}"

        total_samples = len(filtered)
        duration_sec = round(total_samples / target_sr, 3)

        # Sliding windows
        seg_idx = 0
        for start_idx in range(0, total_samples, hop_samples):
            valid_len = min(window_samples, total_samples - start_idx)
            if valid_len < (target_sr * 2.0):  # Skip tails < 2 seconds
                continue

            seg_id = f"{rec_id}_{seg_idx:04d}"
            hn_segments.append({
                "dataset_source": "Hardware Heart Mic (Negative)",
                "subject_id": f"hard_neg_{idx:02d}",
                "recording_id": rec_id,
                "file_path": f"data/processed/hard_negatives/{rec_id}.dummy",
                "label": "Absent",
                "murmur_label": "Absent",
                "outcome_label": "hard_negative_0",
                "auscultation_location": "Chest",
                "original_sampling_rate": sr,
                "duration_sec": duration_sec,
                "split": "train",  # STRICTLY TRAIN ONLY
                "license": "Internal AurisCore",
                "notes": "Hard negative sample (heart/ambient noise)",
                "additional_id": np.nan,
                "subject_group": f"hard_neg_{idx:02d}",
                "sha256": "internal_hn",
                "quality_flag": "ok",
                "segment_id": seg_id,
                "processed_path": rel_npy_path,
                "start_sample": start_idx,
                "valid_samples": valid_len,
                "window_samples": window_samples,
                "sample_rate": target_sr,
                "window_label": "Absent",
                "window_events": "NONE",
            })
            seg_idx += 1

    df_hn = pd.DataFrame(hn_segments)
    print(f"Generated {len(df_hn)} hard negative segments across {len(wav_files)} recordings.")

    # 2. Merge with existing segments
    df_existing = pd.read_csv(existing_segments_path)
    print(f"Loaded {len(df_existing)} existing segments (Train: {(df_existing.split=='train').sum()}, Val: {(df_existing.split=='validation').sum()}, Test: {(df_existing.split=='test').sum()}).")

    df_merged = pd.concat([df_existing, df_hn], ignore_index=True)
    df_merged.to_csv(output_segments_path, index=False)
    print(f"Saved merged dataset to {output_segments_path} (Total Train: {(df_merged.split=='train').sum()}).")

    return df_merged


if __name__ == "__main__":
    prepare_hard_negatives()
