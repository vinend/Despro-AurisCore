"""One-shot official test evaluation of frozen Lung candidates; never fits weights."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import soundfile as sf
from .acquisition_lung import digest
from .dataset_lung import assert_split_integrity, parse_labels
from .lung_preprocessing import windows, validate_config
from .lung_evaluation import frame_metrics, merge_predictions, extract_events, event_metrics
from .lung_dsp import respiratory_measurements
from .lung_temporal import LOCALIZATION_VERSION, localize_frames


def evaluate(candidate, root, manifest, *, model_version, authorized=False):
    if authorized is not True:
        raise PermissionError("Opening official test labels requires explicit authorization")
    candidate, root, manifest = Path(candidate), Path(root).resolve(), Path(manifest)
    config = json.loads((candidate / "config.json").read_text())
    validate_config(config)
    selection = json.loads((candidate / "selection.json").read_text())
    source = json.loads((candidate / "source.json").read_text())
    status = json.loads((candidate / "status.json").read_text())
    if (selection.get("config") != config or selection.get("role") not in {"development_validation", "train_only_oof"}
            or status.get("status") != "completed" or source.get("audit_sha256") != digest(manifest / "audit.json")
            or source.get("model_role") != "final_deployment_candidate"
            or source.get("model_sha256") != digest(candidate / "model.keras")
            or source.get("config_sha256") != digest(candidate / "config.json")
            or source.get("normalization_sha256") != digest(candidate / "normalization.npz")
            or source.get("selection_sha256") != digest(candidate / "selection.json")):
        raise ValueError("Completed final candidate and frozen selection provenance required")
    frame = pd.read_csv(manifest / "recordings.csv", dtype={"group": str})
    assert_split_integrity(frame)
    thresholds = selection["thresholds"]
    if len(thresholds) != len(config["classes"]) or not np.isfinite(thresholds).all() or np.any((np.asarray(thresholds) < 0) | (np.asarray(thresholds) > 1)):
        raise ValueError("Invalid frozen thresholds")
    post = selection["postprocessing"]
    localization_version = selection.get("localization_version", "lung-frame-events-v1")
    if localization_version not in {"lung-frame-events-v1", LOCALIZATION_VERSION}:
        raise ValueError("Unsupported frozen localization version")
    decoder = localize_frames if localization_version == LOCALIZATION_VERSION else extract_events
    if set(post) != {"minimum_s", "merge_gap_s"} or any(not isinstance(v, (int, float)) or not np.isfinite(v) or not 0 <= v <= 2 for v in post.values()):
        raise ValueError("Invalid frozen postprocessing")
    if not model_version.strip():
        raise ValueError("Model version required")
    # A dataset-level receipt prevents reuse of official test for iterative tuning.
    receipt = manifest / "official-test-opened.json"
    if (candidate / "evaluation.json").exists():
        raise ValueError("Evaluation already exists")
    import tensorflow as tf
    model = tf.keras.models.load_model(candidate / "model.keras", compile=False)
    with np.load(candidate / "normalization.npz", allow_pickle=False) as data:
        mean, std = data["mean"], data["std"]
    if mean.shape != (config["n_mels"],) or std.shape != mean.shape or not np.isfinite(mean).all() or not np.isfinite(std).all() or np.any(std <= 0):
        raise ValueError("Invalid final normalization")
    model_hash = digest(candidate / "model.keras")
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump({"model_sha256": model_hash, "model_version": model_version, "status": "opened_no_retry_or_tuning"}, stream)
    truths, scores, masks, recordings = [], [], [], []
    for row in frame[frame.split == "test"].itertuples():
        audio_path, label_path = (root / row.file_path).resolve(), (root / row.label_path).resolve()
        if root not in audio_path.parents or root not in label_path.parents:
            raise ValueError("Unsafe test path")
        if digest(audio_path) != row.sha256 or digest(label_path) != row.label_sha256:
            raise ValueError("Official test source changed")
        if row.quality != "ok":
            recordings.append({"recording_id": row.recording_id, "group": row.group, "status": "quality_excluded"})
            continue
        audio, rate = sf.read(audio_path)
        reference = parse_labels(label_path, row.duration_s)
        predictions, references = [], []
        for block in windows(audio, rate, reference, config, valid_end_s=row.valid_end_s, coverage=True):
            probability = np.asarray(model(np.clip((block["features"] - mean) / std, -5, 5)[None], training=False))[0]
            if probability.shape != block["targets"].shape or not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
                raise ValueError("Invalid final predictions")
            valid_samples = min(round(row.valid_end_s * config["sample_rate"]) - block["start_sample"], round(config["window_seconds"] * config["sample_rate"]))
            predictions.append((block["start_sample"], probability, valid_samples))
            references.append((block["start_sample"], np.concatenate([block["targets"], block["mask"]], axis=1), valid_samples))
        geometry = {"sample_rate": config["sample_rate"], "hop_length": config["hop_length"], "n_fft": config["n_fft"]}
        times, probability = merge_predictions(predictions, **geometry)
        _, target_mask = merge_predictions(references, **geometry)
        n = len(config["classes"])
        truth, mask = (target_mask[:, :n] > .5).astype(float), (target_mask[:, n:] > .999).astype(float)
        predicted = decoder(times, probability, config["classes"], thresholds, hop_s=config["hop_length"] / config["sample_rate"], duration_s=row.valid_end_s, **post)
        usable_reference = [event for event in reference if event["end_s"] <= row.valid_end_s and event["label"] in config["classes"]]
        recordings.append({"recording_id": row.recording_id, "group": row.group, "device": row.device,
            "frame_metrics": frame_metrics(truth, probability, mask, thresholds),
            "event_metrics": {label: event_metrics([e for e in usable_reference if e["label"] == label], [e for e in predicted if e["label"] == label]) for label in config["classes"]},
            "reference_respiratory": respiratory_measurements([e for e in usable_reference if e["label"] in {"inhalation", "exhalation"}], row.valid_end_s),
            "predicted_respiratory": respiratory_measurements([e for e in predicted if e["label"] in {"inhalation", "exhalation"}], row.valid_end_s)})
        truths.append(truth); scores.append(probability); masks.append(mask)
    result = {"evaluation_role": "locked_official_test", "model_version": model_version, "model_sha256": model_hash,
        "config_sha256": digest(candidate / "config.json"), "normalization_sha256": digest(candidate / "normalization.npz"),
        "split_sha256": digest(manifest / "recordings.csv"), "classes": config["classes"], "thresholds": thresholds,
        "threshold_selection_role": selection["role"], "postprocessing": post, "localization_version": localization_version, "group_disjoint": True,
        "grouping": "shifted_recording_date", "patient_disjoint_verified": False, "deployment_eligible": False,
        "metrics": frame_metrics(np.concatenate(truths), np.concatenate(scores), np.concatenate(masks), thresholds),
        "recordings": recordings, "event_boundary_tolerance_s": .1}
    with (candidate / "evaluation.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    return result
