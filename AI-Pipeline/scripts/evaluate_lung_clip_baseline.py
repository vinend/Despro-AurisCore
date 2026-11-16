"""Pool a verified saved Lung development checkpoint for a clip baseline."""

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd

from auriscore.acquisition_lung import digest
from auriscore.lung_clip_evaluation import nominal_clip_frames, reduce_clip_predictions
from auriscore.lung_evaluation import frame_metrics


def evaluate(experiment: Path, cache: Path, audit: Path, localization: Path) -> dict:
    """Reuse completed localization evidence that validated cache labels and order."""
    source_path = experiment / "source.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    verification = json.loads(localization.read_text(encoding="utf-8"))
    status = json.loads((experiment / "status.json").read_text(encoding="utf-8"))
    fold = experiment / "fold-0"
    evaluation = json.loads((fold / "evaluation.json").read_text(encoding="utf-8"))
    prediction_path = fold / "development_predictions.npz"
    index_path = cache / "index.csv"
    recordings_path = audit.parent / "recordings.csv"
    provenance = json.loads((cache / "provenance.json").read_text(encoding="utf-8"))
    order_path = experiment / "prediction_index.json"
    order = pd.DataFrame(json.loads(order_path.read_text(encoding="utf-8")))
    with np.load(prediction_path, allow_pickle=False) as data:
        truth, scores, supervision = (data[key] for key in ("truth", "scores", "mask"))
    if (
        status["status"] != "completed" or source["evaluation_role"] != "development_only"
        or verification["schema_version"] != "lung-localization-evaluation-v1"
        or verification["role"] != "development_only" or verification["fold"] != 0
        or verification["official_test_labels_opened"] is not False
        or verification["prediction_sha256"] != digest(prediction_path)
        or verification["source_sha256"] != digest(source_path)
        or verification["index_sha256"] != source["index_sha256"]
        or source["index_sha256"] != digest(index_path)
        or source["audit_sha256"] != provenance["audit_sha256"]
        or source["audit_sha256"] != digest(audit)
        or provenance["recordings_sha256"] != digest(recordings_path)
        or evaluation["classes"] != verification["classes"]
        or evaluation["classes"] != source["model_classes"]
        or evaluation["thresholds"] != verification["thresholds"]
        or not order.fold.eq(0).all() or not order.file.is_unique or order.empty
    ):
        raise ValueError("Completed and verified development inputs required")

    index = pd.read_csv(index_path, dtype={"group": str})
    selected = index[index.split.eq("validation")].set_index("file")
    if not selected.index.is_unique or selected.index.tolist() != order.file.tolist():
        raise ValueError("Prediction index must match the native validation window order")
    rows = selected.reset_index()
    if rows.group.tolist() != order.group.astype(str).tolist():
        raise ValueError("Prediction groups disagree with the cache index")
    recordings = pd.read_csv(recordings_path, dtype={"group": str})
    recordings = recordings[recordings.split.eq("validation")].set_index("recording_id")
    recordings = recordings.loc[rows.recording_id]
    if recordings.group.tolist() != rows.group.tolist():
        raise ValueError("Recording groups disagree with the cache index")

    config = source["config"]
    rate, hop, fft = (config[key] for key in ("sample_rate", "hop_length", "n_fft"))
    frames = 1 + (round(rate * config["window_seconds"]) - fft) // hop
    classes = evaluation["classes"]
    shape = (len(order), frames, len(classes))
    truth, scores, supervision = (tensor.reshape(shape) for tensor in (truth, scores, supervision))
    starts = rows.file.str.extract(r"_(\d+)\.npz$")[0].astype(int).to_numpy()
    ends = np.rint(recordings.valid_end_s.to_numpy() * rate).astype(int)
    valid = starts[:, None] + np.arange(frames)[None, :] * hop + fft <= ends[:, None]
    clip_frames = nominal_clip_frames(rate, hop)
    y, p, m = reduce_clip_predictions(truth, scores, supervision, valid, clip_frames=clip_frames)
    thresholds = evaluation["thresholds"]
    all_metrics = frame_metrics(y, p, m, thresholds)
    complete = valid[:, : frames // clip_frames * clip_frames].reshape(len(order), -1, clip_frames).all(axis=2)
    for i, metric in enumerate(all_metrics):
        tp, tn, fp, fn = (metric[key] for key in ("tp", "tn", "fp", "fn"))
        eligible = tp + tn + fp + fn
        sensitivity, specificity = metric["sensitivity"], metric["specificity"]
        metric.update(
            threshold=thresholds[i], positive=tp + fn, negative=tn + fp,
            unknown=int(complete.sum()) - eligible,
            accuracy=(tp + tn) / eligible if eligible else None,
            balanced_accuracy=(sensitivity + specificity) / 2
            if sensitivity is not None and specificity is not None else None,
        )
    return {
        "schema_version": "lung-clip-baseline-v1",
        "experiment": experiment.name,
        "role": "descriptive_development_only",
        "official_test_labels_opened": False,
        "threshold_source": "original saved frame thresholds applied to pooled scores",
        "clip_frames": clip_frames,
        "clip_hop_seconds": clip_frames * hop / rate,
        "input_windows": len(order),
        "complete_clips": int(complete.sum()),
        "incomplete_clips": int((~complete).sum()),
        "recordings": int(rows.recording_id.nunique()),
        "groups": int(rows.group.nunique()),
        "metrics": dict(zip(classes, all_metrics)),
        "hashes": {
            "source": digest(source_path), "prediction_index": digest(order_path),
            "predictions": verification["prediction_sha256"], "cache_index": source["index_sha256"],
            "audit": source["audit_sha256"], "previous_localization": digest(localization),
        },
        "limitations": [
            "Native windows overlap, so derived clips can also overlap.",
            "Unknown clips are excluded separately for each class.",
            "Original frame thresholds were selected on this population for frame metrics.",
            "Shifted acquisition-date groups do not establish patient independence.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "cache", "audit", "localization", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.experiment.resolve() in args.output.resolve().parents:
        parser.error("Use a fresh output path outside the completed experiment directory")
    result = evaluate(args.experiment, args.cache, args.audit, args.localization)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, allow_nan=False)
    print(f"Saved diagnostic Lung clip baseline to {args.output}")
