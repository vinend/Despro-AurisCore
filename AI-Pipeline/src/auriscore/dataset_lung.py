"""HF Lung manifests and strict event parsing with date/session leakage controls."""
import json
import hashlib
from pathlib import Path
import re
import numpy as np
import pandas as pd
import soundfile as sf
from .acquisition_lung import digest

LABELS = {"inhalation": "inhalation", "exhalation": "exhalation", "wheeze": "wheeze",
          "rhonchi": "rhonchi", "rhonchus": "rhonchi", "stridor": "stridor",
          "crackle": "crackle", "crackles": "crackle", "cas": "cas", "das": "crackle"}
LABELS.update({"i": "inhalation", "e": "exhalation", "d": "crackle"})
CLASSES = ("inhalation", "exhalation", "wheeze", "rhonchi", "stridor", "crackle", "cas")


def recording_identity(name):
    """Date is a conservative group proxy, not a patient identifier."""
    match = re.fullmatch(r"(steth|trunc)_(\d{4})-?(\d{2})-?(\d{2})[_-](.+)", name)
    if not match:
        raise ValueError(f"Unrecognized HF recording identity: {name}")
    device, year, month, day, rest = match.groups()
    import datetime
    datetime.date(int(year), int(month), int(day))
    location = re.search(r"-(L[1-8])_\d+$", rest) if device == "trunc" else None
    return {"group": year + month + day, "device": device,
            "location": location.group(1) if location else ""}


def parse_labels(path, duration, *, mapping=None):
    """Parse released label/HH:MM:SS.sss boundaries or explicit seconds fixtures."""
    mapping = mapping or LABELS
    events = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split(maxsplit=2)
        if len(fields) != 3:
            raise ValueError(f"Malformed event at line {number}")
        if ":" in fields[1]:
            raw = fields[0]
            def seconds(value):
                parts = value.split(":")
                if len(parts) != 3 or not 0 <= float(parts[1]) < 60 or not 0 <= float(parts[2]) < 60:
                    raise ValueError("Invalid HH:MM:SS timestamp")
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            start, end = seconds(fields[1]), seconds(fields[2])
        else:
            start, end = float(fields[0]), float(fields[1])
            raw = fields[2].strip()
        label = mapping.get(raw.lower())
        if label not in CLASSES or not np.isfinite([start, end]).all() or not 0 <= start < end <= duration + 1e-4:
            raise ValueError(f"Unsupported label or invalid event at line {number}: {raw}")
        events.append({"start_s": start, "end_s": min(end, duration), "label": label, "original_label": raw})
    return events


def build_manifest(root, *, mapping=None):
    """Inventory both splits, quarantine unsafe records, leave test labels sealed."""
    root = Path(root).resolve()
    rows, events, problems = [], [], []
    for split in ("train", "test"):
        for path in sorted((root / split).rglob("*.wav")):
            try:
                identity = recording_identity(path.stem)
                info = sf.info(path)
                x, rate = sf.read(path, dtype="float32", always_2d=True)
                if not x.size or not np.isfinite(x).all() or rate < 4000:
                    raise ValueError("Invalid audio or unsupported source rate")
                label_path = path.with_name(path.stem + "_label.txt")
                if not label_path.exists():
                    raise ValueError("Missing annotation file")
                duration = len(x) / rate
                # Inspect padding independently of target annotations.
                active = np.flatnonzero(np.any(x != 0, axis=1))
                valid_end = (int(active[-1]) + 1) / rate if active.size else 0
                quality = "ok" if valid_end > 0 and np.mean(np.abs(x) >= .999) <= .01 else "invalid"
                mono = x.mean(axis=1).astype(np.float64)
                mono -= mono.mean()
                peak = np.max(np.abs(mono))
                normalized_hash = hashlib.sha256(np.round(mono / max(peak, 1e-12) * 4096).astype('<i2').tobytes()).hexdigest()
                row = {"recording_id": path.stem, "file_path": path.relative_to(root).as_posix(),
                       "label_path": label_path.relative_to(root).as_posix(), "original_split": split,
                       **identity, "sample_rate": rate, "channels": info.channels, "duration_s": duration,
                       "valid_end_s": valid_end, "sha256": digest(path), "label_sha256": digest(label_path),
                       "normalized_pcm_sha256": normalized_hash,
                       "quality": quality, "split": split, "license": "CC-BY-4.0"}
                if split == "train":
                    for event in parse_labels(label_path, duration, mapping=mapping):
                        events.append({"recording_id": path.stem, **event})
                rows.append(row)
            except (ValueError, RuntimeError, OSError) as exc:
                problems.append({"file": path.relative_to(root).as_posix(), "reason": str(exc)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("No usable HF recordings")
    if frame.recording_id.duplicated().any():
        raise ValueError("Duplicate recording IDs")
    test = frame[frame.original_split == "test"]
    test_groups, test_hashes = set(test.group), set(test.sha256)
    test_normalized = set(test.normalized_pcm_sha256)
    conflict = (frame.original_split == "train") & (frame.group.isin(test_groups) | frame.sha256.isin(test_hashes)
                                                  | frame.normalized_pcm_sha256.isin(test_normalized))
    frame.loc[conflict | (frame.quality != "ok"), "split"] = "quarantine"
    # Union exact duplicates in TRAIN by quarantining all but the first source group.
    for _, duplicate in frame[frame.original_split == "train"].groupby("normalized_pcm_sha256"):
        if duplicate.group.nunique() > 1:
            frame.loc[duplicate.index, "split"] = "quarantine"
    groups = sorted(frame.loc[frame.split == "train", "group"].unique())
    if len(groups) >= 3:
        rng = np.random.default_rng(42)
        rng.shuffle(groups)
        validation = set(groups[:max(1, round(len(groups) * .2))])
        frame.loc[(frame.split == "train") & frame.group.isin(validation), "split"] = "validation"
    audit = {"schema_version": "lung-data-audit-v1", "test_inventory_present": not test.empty,
             "patient_disjoint_verified": False, "grouping": "shifted_recording_date",
             "train_test_group_conflicts": int(conflict.sum()), "problems": problems,
             "split_counts": frame.split.value_counts().to_dict(), "training_groups": len(groups),
             "observed_train_labels": sorted({e["label"] for e in events}),
             "annotation_coverage_verified": bool(events) and not problems,
             "coverage_policy": "annotated_respiration_and_positive_events_only",
             "near_duplicate_review_complete": not test.empty and not problems,
             "duplicate_check": "exact_file_and_gain_dc_normalized_quantized_pcm",
             "duplicate_check_limitations": "Not an exhaustive acoustic or patient identity check."}
    return frame, pd.DataFrame(events, columns=["recording_id", "start_s", "end_s", "label", "original_label"]), audit


def assert_split_integrity(frame):
    for column in ("group", "sha256", "normalized_pcm_sha256"):
        active = frame[frame.split.isin(["train", "validation", "test"])]
        if (active.groupby(column).split.nunique() > 1).any():
            raise ValueError(f"Cross-split leakage: {column}")
    if not {"train", "validation"}.issubset(set(frame.split)):
        raise ValueError("At least two disjoint development partitions required")
