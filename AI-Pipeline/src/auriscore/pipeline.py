"""Stage orchestration, provenance checks and command-line entry points."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from .acquisition import acquire
from .analysis import analyze_dataset
from .config import load_config
from .dataset import build_manifest
from .features import extract_features
from .io import load_audio, read_table
from .preprocessing import preprocess
from .segmentation import segment
from .splitting import assign_splits, assert_no_leakage
from .training import train_baseline
from .cnn import train_cnn
from .validation import sha256

LOG = logging.getLogger(__name__)


def fingerprint(root: Path, config: dict[str, Any]) -> str:
    """Bind derived stages to exact manifest, configuration and implementation."""
    data = (root / "metadata/dataset_manifest.csv").read_bytes() + json.dumps(config, sort_keys=True).encode()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        data += path.name.encode() + path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def stamp(root: Path, config: dict[str, Any], stage: str, verify: bool = False) -> None:
    """Fail if an upstream stage was created with different data or settings."""
    path = root / f"data/processed/{stage}_provenance.json"
    current = fingerprint(root, config)
    if verify:
        if not path.exists() or json.loads(path.read_text())["fingerprint"] != current:
            raise ValueError(f"Stale/missing {stage} artifacts; rerun preceding stages with the same configuration")
        provenance = json.loads(path.read_text())
        if sha256(root / f"data/processed/{stage}.csv") != provenance["table_sha256"]:
            raise ValueError(f"Changed {stage} table; rerun preceding stages")
    else:
        path.write_text(json.dumps({"fingerprint": current, "config": config,
                                   "table_sha256": sha256(root / f"data/processed/{stage}.csv")}, indent=2), encoding="utf-8")


def preprocess_dataset(root: Path, config: dict[str, Any], frame: pd.DataFrame) -> pd.DataFrame:
    """Save one processed array per recording and a metadata-rich window index."""
    assert_no_leakage(frame)
    folder = root / "data/processed/audio"
    folder.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    eligible = frame[frame.split.isin(["train", "validation", "test"])]
    for index, (_, row) in enumerate(eligible.iterrows()):
        try:
            source = root / row.file_path
            if sha256(source) != row.sha256:
                raise ValueError("Source hash changed since manifest creation; rebuild manifest")
            audio, sr = load_audio(source)
            audio = preprocess(audio, sr, config)
            destination = folder / f"{row.recording_id}.npy"
            np.save(destination, audio, allow_pickle=False)
            for number, (start, window, valid) in enumerate(segment(audio, config["sample_rate"], config["window_seconds"], config["overlap"])):
                rows.append({**row.to_dict(), "segment_id": f"{row.recording_id}_{number:04d}",
                             "processed_path": destination.relative_to(root).as_posix(),
                             "start_sample": start, "valid_samples": valid, "window_samples": len(window),
                             "sample_rate": config["sample_rate"]})
        except (OSError, ValueError, RuntimeError) as exc:
            LOG.warning("Preprocessing skipped %s: %s", row.recording_id, exc)
            errors.append({"recording_id": row.recording_id, "error": str(exc)})
        if (index + 1) % 250 == 0:
            LOG.info("Preprocessed %d/%d recordings", index + 1, len(eligible))
    columns = list(frame.columns) + ["segment_id", "processed_path", "start_sample", "valid_samples", "window_samples", "sample_rate"]
    result = pd.DataFrame(rows, columns=columns)
    result.to_csv(root / "data/processed/segments.csv", index=False)
    pd.DataFrame(errors, columns=["recording_id", "error"]).to_csv(root / "metadata/preprocessing_errors.csv", index=False)
    stamp(root, config, "segments")
    LOG.info("Created %d windows; %d recording errors", len(result), len(errors))
    return result


def feature_dataset(root: Path, config: dict[str, Any]) -> pd.DataFrame:
    """Extract window features; never ingest demographic or target metadata as features."""
    stamp(root, config, "segments", verify=True)
    segments = read_table(root / "data/processed/segments.csv")
    rows, errors = [], []
    for index, (_, group) in enumerate(segments.groupby("recording_id", sort=True)):
        try:
            audio = np.load(root / group.iloc[0].processed_path, allow_pickle=False)
            local_rows = []
            for row in group.to_dict("records"):
                start, valid, size = int(row["start_sample"]), int(row["valid_samples"]), int(row["window_samples"])
                window = np.pad(audio[start:start + valid], (0, size - valid))
                local_rows.append({**row, **extract_features(window, config)})
            rows.extend(local_rows)
        except (OSError, ValueError, RuntimeError) as exc:
            LOG.warning("Feature extraction skipped %s: %s", group.iloc[0].recording_id, exc)
            errors.append({"recording_id": group.iloc[0].recording_id, "error": str(exc)})
        if (index + 1) % 100 == 0:
            LOG.info("Extracted features from %d recordings (%d windows)", index + 1, len(rows))
    result = pd.DataFrame(rows)
    pd.DataFrame(errors, columns=["recording_id", "error"]).to_csv(root / "metadata/feature_errors.csv", index=False)
    if result.empty:
        raise ValueError("No features extracted; inspect metadata/feature_errors.csv and source audio")
    result.to_csv(root / "data/processed/features.csv", index=False)
    stamp(root, config, "features")
    return result


def run(root: Path, config: dict[str, Any], stage: str = "run_pipeline", download: bool = False,
        synthetic: bool = False) -> dict[str, Any]:
    """Run a stage or the complete local-data pipeline; acquisition is explicit."""
    root = root.resolve()
    source = root / config["dataset_dir"]
    if stage == "download_dataset" or download:
        acquisition = acquire(source)
        if stage == "download_dataset":
            return acquisition
    if not list(source.rglob("*.wav")):
        raise FileNotFoundError(f"No PCG recordings under {source}. Run python scripts/download_dataset.py or place the public CirCor release there. Evaluation was not run.")
    if (source / "SHA256SUMS.txt").exists():
        for line in (source / "SHA256SUMS.txt").read_text().splitlines():
            digest, name = line.split(maxsplit=1)
            original = source / name.lstrip("*").removeprefix("./")
            if not original.resolve().is_relative_to(source.resolve()):
                raise ValueError("Unsafe checksum path")
            if not original.exists() or sha256(original) != digest:
                raise ValueError(f"Incomplete or changed public release: {original}. Rerun download_dataset.py; originals are never overwritten.")
    if stage in ("run_pipeline", "build_manifest"):
        frame = build_manifest(root, source)
        # Keep a useful manifest and quality report even if splitting cannot proceed.
        analyze_dataset(root, frame)
        frame = assign_splits(frame, config)
        frame.to_csv(root / "metadata/dataset_manifest.csv", index=False)
    else:
        frame = read_table(root / "metadata/dataset_manifest.csv")
    if stage in ("run_pipeline", "build_manifest", "analyze_dataset"):
        analyze_dataset(root, frame)
    if stage in ("run_pipeline", "preprocess_dataset"):
        preprocess_dataset(root, config, frame)
    model_type = config.get("model_type", "svm")
    if stage == "extract_features" or (stage == "run_pipeline" and model_type == "svm"):
        feature_dataset(root, config)
    if stage == "train_baseline" or (stage == "run_pipeline" and model_type == "svm"):
        stamp(root, config, "features", verify=True)
        return train_baseline(read_table(root / "data/processed/features.csv"), config, root, synthetic=synthetic)
    if stage == "train_cnn" or (stage == "run_pipeline" and model_type == "cnn"):
        stamp(root, config, "segments", verify=True)
        return train_cnn(read_table(root / "data/processed/segments.csv"), config, root, synthetic=synthetic)
    return {"status": "completed", "stage": stage}


def main(stage: str = "run_pipeline", default_config: str = "configs/heart_baseline.yaml") -> int:
    """CLI with actionable expected-error messages and nonzero failure exit codes."""
    parser = argparse.ArgumentParser(description="AurisCore research heart-sound pipeline")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=Path, default=Path(default_config))
    parser.add_argument("--download", action="store_true", help="Acquire the complete public CirCor release first")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(args.root / args.config)
        result = run(args.root, config, stage, args.download)
        LOG.info("Completed %s: %s", stage, result.get("status", "OK"))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        LOG.error("%s", exc)
        return 2
