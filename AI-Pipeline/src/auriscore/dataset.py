"""CirCor text metadata parsing, repeat-participant linkage and manifest creation."""
import logging
from pathlib import Path
import pandas as pd
from .validation import MANIFEST_COLUMNS, inspect_audio, validate_manifest

LOG = logging.getLogger(__name__)


def link_subjects(frame: pd.DataFrame) -> pd.DataFrame:
    """Union original and Additional IDs, including transitive cross-campaign links."""
    parent: dict[str, str] = {}

    def find(key: str) -> str:
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]

    for row in frame.itertuples():
        if not row.subject_id:
            continue
        find(row.subject_id)
        if row.additional_id:
            a, b = find(row.subject_id), find(row.additional_id)
            parent[max(a, b)] = min(a, b)
    frame = frame.copy()
    frame["subject_group"] = [find(s) if s else "" for s in frame.subject_id]
    return frame


def build_manifest(root: Path, dataset_dir: Path) -> pd.DataFrame:
    """Parse source labels verbatim, scan every WAV, retain bad/missing records."""
    metadata: dict[str, dict[str, str]] = {}
    notes = []
    for path in sorted(dataset_dir.rglob("*.txt")):
        if not path.stem.isdigit():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            header = lines[0].split()
            sid, count = header[0], int(header[1])
            tags = dict(line[1:].split(":", 1) for line in lines if line.startswith("#") and ":" in line)
            tags = {k.strip(): v.strip() for k, v in tags.items()}
            for line in lines[1:1 + count]:
                fields = line.split()
                name = fields[2]
                additional = tags.get("Additional ID", "")
                if additional.lower() in ("nan", "none"):
                    additional = ""
                metadata[str((path.parent / name).resolve())] = {
                    "subject_id": sid, "additional_id": additional,
                    "auscultation_location": fields[0],
                    "murmur_label": tags.get("Murmur", ""), "outcome_label": tags.get("Outcome", ""),
                }
        except (OSError, ValueError, IndexError) as exc:
            notes.append({"file": str(path), "error": str(exc)})
            LOG.warning("Cannot parse %s: %s", path, exc)
    paths = set(metadata) | {str(p.resolve()) for p in dataset_dir.rglob("*.wav")}
    rows, checks = [], []
    for name in sorted(paths):
        path = Path(name)
        row = dict.fromkeys(MANIFEST_COLUMNS, "")
        row.update(metadata.get(name, {}))
        quality = inspect_audio(path)
        checks.append({"recording_id": path.stem, "file_path": str(path.relative_to(root)), **quality})
        row.update(dataset_source="CirCor DigiScope 1.0.3", recording_id=path.stem,
                   file_path=path.relative_to(root).as_posix(), label=row["murmur_label"],
                   original_sampling_rate=quality.get("sampling_rate", ""),
                   duration_sec=quality.get("duration_sec", ""), license="ODC-By-1.0",
                   sha256=quality.get("sha256", ""), quality_flag=quality["quality_flag"])
        warnings = []
        if not row["subject_id"]:
            warnings.append("Missing subject metadata; cannot guarantee subject-wise split")
            LOG.warning("Missing subject ID: %s", path)
        if quality["error"]:
            warnings.append(quality["error"])
            LOG.warning("Invalid audio %s: %s", path, quality["error"])
        if row["label"] == "Unknown":
            warnings.append("Unknown murmur label; excluded from binary baseline")
        row["notes"] = "; ".join(warnings)
        rows.append(row)
    frame = link_subjects(pd.DataFrame(rows, columns=MANIFEST_COLUMNS))
    validate_manifest(frame)
    (root / "metadata").mkdir(parents=True, exist_ok=True)
    frame.to_csv(root / "metadata/dataset_manifest.csv", index=False)
    pd.DataFrame(checks, columns=["recording_id", "file_path", "valid", "error", "quality_flag", "sha256",
                                "channels", "sampling_rate", "duration_sec", "empty", "nan_count", "inf_count",
                                "rms", "clipping_ratio"]).to_csv(root / "metadata/audio_validation.csv", index=False)
    pd.DataFrame(notes, columns=["file", "error"]).to_csv(root / "metadata/metadata_errors.csv", index=False)
    return frame
