"""Abdomen Bowel Sounds dataset parser, annotation extraction, and manifest builder."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .validation import MANIFEST_COLUMNS, inspect_audio, validate_manifest

LOG = logging.getLogger(__name__)

# Figshare event types:
# SB: Single Burst (Solitary clicks) -> Active
# MB: Multiple Burst (Repeated clicks) -> Active
# CRS: Continuous Random Sound (Crepitating sweeps) -> Active
# HS: Harmonic Sound (Whistling sweeps) -> Active
# NONE: Background sound / silence -> Inactive
ACTIVE_EVENTS = {"SB", "MB", "CRS", "HS"}


def parse_annotation_file(path: Path) -> list[dict[str, Any]]:
    """Parse a tab-separated event annotation file."""
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\s+", line)
        if len(parts) >= 3:
            try:
                start_sec = float(parts[0])
                end_sec = float(parts[1])
                label = parts[2].upper()
                events.append({
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "event_type": label,
                    "is_active": label in ACTIVE_EVENTS,
                })
            except ValueError:
                continue
    return events


def extract_subject_info(filename: str) -> tuple[str, str, str]:
    """Extract subject_id, session_id, recording_id from standardized names.

    e.g. record_300424001_1.wav -> subject_id: 300424001, session_id: 1, recording_id: record_300424001_1
    """
    stem = Path(filename).stem
    match = re.match(r"^record_(\d+)_(\d+)$", stem)
    if match:
        subject_id = match.group(1)
        session_id = match.group(2)
        return subject_id, session_id, stem
    # Fallback for alternative naming schemes
    clean_stem = re.sub(r"[^a-zA-Z0-9_]", "", stem)
    return clean_stem, "1", clean_stem


def build_abdomen_manifest(root: Path, dataset_dir: Path) -> pd.DataFrame:
    """Build a complete manifest for the Bowel Sounds dataset."""
    root = root.resolve()
    dataset_dir = dataset_dir.resolve()
    wav_files = sorted(dataset_dir.glob("*.wav"))

    if not wav_files:
        raise FileNotFoundError(
            f"No WAV recordings found under {dataset_dir}. "
            "Run python scripts/download_abdomen_dataset.py first."
        )

    rows: list[dict[str, Any]] = []
    for wav_path in wav_files:
        rel_path = wav_path.relative_to(root).as_posix()
        txt_path = wav_path.with_suffix(".txt")
        events = parse_annotation_file(txt_path)

        subject_id, session_id, recording_id = extract_subject_info(wav_path.name)
        audio_info = inspect_audio(wav_path)

        # Has active sounds if at least one active event exists
        active_count = sum(1 for e in events if e["is_active"])
        has_active = active_count > 0
        murmur_label = "Present" if has_active else "Absent"

        row = {
            "dataset_source": "Figshare Bowel Sounds 1.0",
            "subject_id": subject_id,
            "recording_id": recording_id,
            "file_path": rel_path,
            "label": murmur_label,
            "murmur_label": murmur_label,
            "outcome_label": f"active_events_{active_count}",
            "auscultation_location": "Abdomen",
            "original_sampling_rate": audio_info.get("sampling_rate", 8000),
            "duration_sec": audio_info.get("duration_sec", 0.0),
            "split": "unassigned",
            "license": "CC BY 4.0",
            "notes": f"events={len(events)};active={active_count};session={session_id}",
            "additional_id": "",
            "subject_group": subject_id,
            "sha256": audio_info.get("sha256", ""),
            "quality_flag": audio_info.get("quality_flag", "ok"),
        }
        rows.append(row)

    frame = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    validate_manifest(frame)
    return frame


def assign_abdomen_splits(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Assign deterministic subject-level train/validation/test splits."""
    result = frame.copy()
    unique_subjects = sorted(result["subject_group"].unique())
    n_subjects = len(unique_subjects)

    if n_subjects == 0:
        raise ValueError("Cannot assign splits: empty subject list")

    # Deterministic assignment using random state
    rng = np.random.default_rng(config.get("seed", 42))
    shuffled_subjects = list(unique_subjects)
    rng.shuffle(shuffled_subjects)

    if n_subjects >= 7:
        # If enough subjects, use standard fraction calculation
        train_count = max(1, int(round(n_subjects * config.get("train_fraction", 0.70))))
        val_count = max(1, int(round(n_subjects * config.get("validation_fraction", 0.15))))
        test_count = max(1, n_subjects - train_count - val_count)

        train_subs = set(shuffled_subjects[:train_count])
        val_subs = set(shuffled_subjects[train_count:train_count + val_count])
        test_subs = set(shuffled_subjects[train_count + val_count:])
    elif n_subjects >= 4:
        # 4-6 subjects: at least 2 train, 1 val, 1 test
        train_subs = set(shuffled_subjects[:-2])
        val_subs = {shuffled_subjects[-2]}
        test_subs = {shuffled_subjects[-1]}
    elif n_subjects == 3:
        train_subs = {shuffled_subjects[0]}
        val_subs = {shuffled_subjects[1]}
        test_subs = {shuffled_subjects[2]}
    else:
        # Fallback for synthetic/very small test fixtures (1-2 subjects)
        train_subs = set(shuffled_subjects)
        val_subs = set(shuffled_subjects)
        test_subs = set(shuffled_subjects)

    result["split"] = "excluded"
    result.loc[result["subject_group"].isin(train_subs), "split"] = "train"
    result.loc[result["subject_group"].isin(val_subs), "split"] = "validation"
    result.loc[result["subject_group"].isin(test_subs), "split"] = "test"

    LOG.info(
        "Assigned Abdomen splits: %d train, %d validation, %d test subjects",
        len(train_subs), len(val_subs), len(test_subs)
    )
    return result


def segment_abdomen_with_annotations(
    root: Path,
    config: dict[str, Any],
    manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Preprocess and segment abdomen recordings, tagging windows with event labels."""
    from .io import load_audio
    from .preprocessing import preprocess
    from .segmentation import segment

    folder = root / "data/processed/audio"
    folder.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    eligible = manifest[manifest.split.isin(["train", "validation", "test"])]

    for index, (_, row) in enumerate(eligible.iterrows()):
        try:
            source = root / row["file_path"]
            txt_path = source.with_suffix(".txt")
            events = parse_annotation_file(txt_path)

            audio, sr = load_audio(source)
            audio = preprocess(audio, sr, config)
            dest_path = folder / f"{row['recording_id']}.npy"
            np.save(dest_path, audio, allow_pickle=False)

            sample_rate = config["sample_rate"]
            window_sec = config["window_seconds"]
            overlap = config["overlap"]

            for seg_idx, (start, window, valid) in enumerate(segment(audio, sample_rate, window_sec, overlap)):
                win_start_sec = start / sample_rate
                win_end_sec = (start + valid) / sample_rate

                # Check if any active event falls in this window
                window_events = [
                    e for e in events
                    if e["end_sec"] > win_start_sec and e["start_sec"] < win_end_sec
                ]
                active_events_in_win = [e for e in window_events if e["is_active"]]

                # Binary label for window (Present = Active Bowel Burst, Absent = Quiescent / Background)
                win_label = "Present" if active_events_in_win else "Absent"
                event_summary = ";".join(e["event_type"] for e in window_events) or "NONE"

                row_dict = row.to_dict()
                row_dict["label"] = win_label
                row_dict["murmur_label"] = win_label

                rows.append({
                    **row_dict,
                    "segment_id": f"{row['recording_id']}_{seg_idx:04d}",
                    "processed_path": dest_path.relative_to(root).as_posix(),
                    "start_sample": start,
                    "valid_samples": valid,
                    "window_samples": len(window),
                    "sample_rate": sample_rate,
                    "window_label": win_label,
                    "window_events": event_summary,
                })
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Preprocessing skipped %s: %s", row["recording_id"], exc)
            errors.append({"recording_id": row["recording_id"], "error": str(exc)})

    columns = list(manifest.columns) + [
        "segment_id", "processed_path", "start_sample", "valid_samples",
        "window_samples", "sample_rate", "window_label", "window_events"
    ]
    result = pd.DataFrame(rows, columns=columns)
    result.to_csv(root / "data/processed/segments.csv", index=False)
    (root / "metadata").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(errors, columns=["recording_id", "error"]).to_csv(
        root / "metadata/preprocessing_errors.csv", index=False
    )
    LOG.info("Created %d abdomen windows (%d errors)", len(result), len(errors))
    return result
