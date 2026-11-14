"""Preprocessing and frame-mask generation for Kaggle Bowel Sounds Dataset (Nowak et al.).

Converts 1,606 2.0-second auscultation recordings to AurisCore standard:
- Resampled to 8,000 Hz mono
- Bandpass filtered 100 - 1,000 Hz
- Log-Mel spectrograms: (40, 126) at 16.0 ms frame hop
- Frame ground-truth mask: (126,) binary labels [0, 1] per frame
- Strict patient-level train/val/test split (427 unique patients, 0% leakage)
- Optional injection of hardware stethoscope hard-negatives into training set
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd
from scipy.signal import butter, sosfilt
import soundfile as sf
import librosa
from sklearn.model_selection import GroupShuffleSplit

LOG = logging.getLogger(__name__)


def prepare_kaggle_sed_dataset(
    source_dir: Path = Path("AI-Pipeline/data/external/kaggle-bowel-sounds"),
    output_dir: Path = Path("AI-Pipeline/data/processed/kaggle"),
    hardware_dir: Path | None = Path("D:/Despro/Prapemrosesan_Tubuh"),
    manifest_path: Path = Path("AI-Pipeline/data/processed/segments_kaggle.csv"),
    target_sr: int = 8000,
    n_mels: int = 40,
    n_fft: int = 512,
    hop_length: int = 128,
    fmin: float = 100.0,
    fmax: float = 1000.0,
    seed: int = 42,
) -> pd.DataFrame:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    manifest_path = manifest_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    files_csv = source_dir / "files.csv"
    if not files_csv.exists():
        raise FileNotFoundError(f"files.csv not found in {source_dir}")

    df_files = pd.read_csv(files_csv)
    print(f"Loaded files.csv: {len(df_files)} total files.")

    # Bandpass filter 100 - 1000 Hz
    sos = butter(4, [fmin, fmax], btype="bandpass", fs=target_sr, output="sos")
    frame_dur_s = hop_length / float(target_sr)  # 0.016s

    tensors_mel: list[np.ndarray] = []
    tensors_mask: list[np.ndarray] = []
    metadata_rows: list[dict[str, Any]] = []

    print("Processing Kaggle bowel sound clips (resampling to 8 kHz, bandpass, log-mel)...")
    for idx, row in df_files.iterrows():
        fn = str(row["filename"])
        wav_path = source_dir / fn
        base_name = fn.replace(".wav", "")
        csv_path = source_dir / f"{base_name}.csv"

        if not wav_path.exists():
            continue

        patient_id = fn.split("_")[0]
        chunk_id = fn.split("_")[1].replace(".wav", "")

        # 1. Read audio & resample
        y, orig_sr = sf.read(str(wav_path))
        if y.ndim > 1:
            y = y[:, 0]
        if orig_sr != target_sr:
            y = librosa.resample(y, orig_sr=orig_sr, target_sr=target_sr)

        # Ensure exact 2.0 seconds (16,000 samples)
        expected_len = target_sr * 2
        if len(y) < expected_len:
            y = np.pad(y, (0, expected_len - len(y)))
        elif len(y) > expected_len:
            y = y[:expected_len]

        # 2. Bandpass filter
        y_filt = sosfilt(sos, y)

        # 3. Log-Mel spectrogram (40, 126)
        mel = librosa.feature.melspectrogram(
            y=y_filt,
            sr=target_sr,
            n_fft=n_fft,
            hop_length=hop_length,
            n_mels=n_mels,
            fmin=fmin,
            fmax=fmax,
            power=2.0,
        )
        logmel = librosa.power_to_db(mel, ref=np.max, top_db=80.0).astype(np.float32)

        # 4. Frame mask (126,)
        n_frames = logmel.shape[1]
        mask = np.zeros(n_frames, dtype=np.float32)
        event_count = 0

        if csv_path.exists():
            try:
                df_ann = pd.read_csv(csv_path)
                if not df_ann.empty and "start" in df_ann.columns and "end" in df_ann.columns:
                    for _, ann in df_ann.iterrows():
                        s = float(ann["start"])
                        e = float(ann["end"])
                        s_idx = max(0, int(np.floor(s / frame_dur_s)))
                        e_idx = min(n_frames, int(np.ceil(e / frame_dur_s)))
                        if e_idx > s_idx:
                            mask[s_idx:e_idx] = 1.0
                            event_count += 1
            except Exception as ex:
                LOG.warning("Failed to parse %s: %s", csv_path.name, ex)

        tensors_mel.append(logmel)
        tensors_mask.append(mask)

        metadata_rows.append({
            "segment_id": f"kaggle_{base_name}",
            "filename": fn,
            "patient_id": f"patient_{patient_id}",
            "chunk_id": chunk_id,
            "duration_s": 2.0,
            "n_frames": n_frames,
            "active_frames": int(mask.sum()),
            "burst_coverage": float(mask.sum() / n_frames),
            "event_count": event_count,
            "source": "kaggle_nowak",
        })

        if (idx + 1) % 400 == 0 or (idx + 1) == len(df_files):
            print(f"  Processed {idx + 1}/{len(df_files)} files...")

    # 5. Optional Hardware Stethoscope Hard Negatives (Train-only)
    if hardware_dir and hardware_dir.exists():
        print(f"Mining hardware hard-negatives from {hardware_dir}...")
        hw_files = sorted(list(hardware_dir.glob("*_organ_dokter_HP20Hz_kausal.wav")))
        hw_count = 0
        for hw_idx, hw_path in enumerate(hw_files):
            y_hw, sr_hw = sf.read(str(hw_path))
            if y_hw.ndim > 1:
                y_hw = y_hw[:, 0]
            if sr_hw != target_sr:
                y_hw = librosa.resample(y_hw, orig_sr=sr_hw, target_sr=target_sr)

            # Slice into 2.0-second non-overlapping windows
            step = target_sr * 2
            for start_sample in range(0, len(y_hw) - step + 1, step):
                chunk = y_hw[start_sample : start_sample + step]
                chunk_filt = sosfilt(sos, chunk)
                mel_hw = librosa.feature.melspectrogram(
                    y=chunk_filt,
                    sr=target_sr,
                    n_fft=n_fft,
                    hop_length=hop_length,
                    n_mels=n_mels,
                    fmin=fmin,
                    fmax=fmax,
                    power=2.0,
                )
                logmel_hw = librosa.power_to_db(mel_hw, ref=np.max, top_db=80.0).astype(np.float32)
                mask_hw = np.zeros(logmel_hw.shape[1], dtype=np.float32)

                tensors_mel.append(logmel_hw)
                tensors_mask.append(mask_hw)

                metadata_rows.append({
                    "segment_id": f"hw_neg_{hw_idx}_{hw_count}",
                    "filename": hw_path.name,
                    "patient_id": f"hw_subject_{hw_idx}",
                    "chunk_id": str(hw_count),
                    "duration_s": 2.0,
                    "n_frames": logmel_hw.shape[1],
                    "active_frames": 0,
                    "burst_coverage": 0.0,
                    "event_count": 0,
                    "source": "hardware_stethoscope",
                    "split": "train",
                })
                hw_count += 1

        print(f"  Added {hw_count} hardware hard-negative windows into training split.")

    df_meta = pd.DataFrame(metadata_rows)

    # 6. Strict patient-level split for Kaggle patients (70% train, 15% val, 15% test)
    print("Performing patient-level leak-free split for Kaggle patients...")
    kaggle_mask = df_meta["source"] == "kaggle_nowak"
    kaggle_patients = np.array(sorted(df_meta[kaggle_mask]["patient_id"].unique()))
    rng = np.random.default_rng(seed)
    rng.shuffle(kaggle_patients)

    n_p = len(kaggle_patients)
    n_train = int(0.70 * n_p)
    n_val = int(0.15 * n_p)

    train_pts = set(kaggle_patients[:n_train])
    val_pts = set(kaggle_patients[n_train : n_train + n_val])
    test_pts = set(kaggle_patients[n_train + n_val :])

    def assign_split(row: pd.Series) -> str:
        if row.get("source") == "hardware_stethoscope":
            return "train"
        pid = row["patient_id"]
        if pid in train_pts:
            return "train"
        if pid in val_pts:
            return "val"
        return "test"

    df_meta["split"] = df_meta.apply(assign_split, axis=1)

    # 7. Save tensors and manifest
    mels_arr = np.array(tensors_mel, dtype=np.float32)  # (N, 40, 126)
    masks_arr = np.array(tensors_mask, dtype=np.float32)  # (N, 126)

    tensor_archive = output_dir / "kaggle_sed_tensors.npz"
    print(f"Saving tensors archive: {mels_arr.shape} mels and {masks_arr.shape} masks...")
    np.savez_compressed(tensor_archive, mels=mels_arr, masks=masks_arr)

    df_meta.to_csv(manifest_path, index=False)
    print(f"Saved manifest to {manifest_path}")

    # Summary
    print("\nDataset Preparation Summary:")
    print(f"  Total Segments: {len(df_meta)}")
    print(f"  Train: {(df_meta['split'] == 'train').sum()} segments")
    print(f"  Val  : {(df_meta['split'] == 'val').sum()} segments")
    print(f"  Test : {(df_meta['split'] == 'test').sum()} segments")
    print(f"  Total Annotated Events: {df_meta['event_count'].sum()}")
    print(f"  Tensor archive: {tensor_archive} ({tensor_archive.stat().st_size / (1024*1024):.2f} MB)")

    return df_meta


if __name__ == "__main__":
    prepare_kaggle_sed_dataset()
