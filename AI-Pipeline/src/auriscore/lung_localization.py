"""Development-only temporal localization using existing frame-trained Lung models.

No training, threshold selection or deployment registration happens here.
"""
import json
from io import BytesIO
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import soundfile as sf

from .acquisition_lung import digest
from .analysis_service import AnalysisService, AudioPolicy
from .lung_dsp import respiratory_measurements
from .lung_evaluation import event_metrics, merge_predictions
from .lung_preprocessing import validate_config, windows
from .lung_training import preflight

from .lung_temporal import LOCALIZATION_VERSION, localize_frames
PHASES = {"inhalation", "exhalation"}



def _development(experiment: Path, fold: int) -> tuple[dict, Path, dict]:
    if type(fold) is not int or fold < 0:
        raise ValueError("Nonnegative development fold required")
    source = json.loads((experiment / "source.json").read_text())
    status = json.loads((experiment / "status.json").read_text())
    config = source["config"]
    validate_config(config)
    folder = experiment / f"fold-{fold}"
    evaluation = json.loads((folder / "evaluation.json").read_text())
    thresholds = np.asarray(evaluation.get("thresholds", []))
    if (source.get("evaluation_role") != "development_only" or status.get("status") != "completed"
            or evaluation.get("role") != "development_only" or evaluation.get("classes") != config["classes"]
            or thresholds.shape != (len(config["classes"]),) or not np.isfinite(thresholds).all()
            or np.any((thresholds < 0) | (thresholds > 1))):
        raise ValueError("Completed development-only experiment and saved thresholds required")
    return config, folder, evaluation


def predict_frames(audio: np.ndarray, rate: int, config: dict, mean: np.ndarray,
                   std: np.ndarray, model: Callable) -> tuple[np.ndarray, np.ndarray]:
    """Infer all windows, average duplicate absolute frames and drop padded tails."""
    validate_config(config)
    if (mean.shape != (config["n_mels"],) or std.shape != mean.shape
            or not np.isfinite(mean).all() or not np.isfinite(std).all() or np.any(std <= 0)):
        raise ValueError("Invalid Lung normalization")
    blocks = []
    for block in windows(audio, rate, [], config):
        x = np.clip((block["features"] - mean) / std, -5, 5)
        prediction = np.asarray(model(x[None], training=False))
        if (prediction.shape != (1, len(x), len(config["classes"])) or not np.isfinite(prediction).all()
                or np.any((prediction < 0) | (prediction > 1))):
            raise ValueError("Invalid temporal Lung model output")
        valid = min(round(len(audio) / rate * config["sample_rate"]) - block["start_sample"],
                    round(config["window_seconds"] * config["sample_rate"]))
        blocks.append((block["start_sample"], prediction[0], valid))
    return merge_predictions(blocks, sample_rate=config["sample_rate"], hop_length=config["hop_length"], n_fft=config["n_fft"])


def _result(times: np.ndarray, scores: np.ndarray, config: dict, thresholds: list,
            duration: float, minimum_s: float, merge_gap_s: float) -> dict:
    events = localize_frames(times, scores, config["classes"], thresholds,
                             hop_s=config["hop_length"] / config["sample_rate"], duration_s=duration,
                             minimum_s=minimum_s, merge_gap_s=merge_gap_s)
    phases = [event for event in events if event["label"] in PHASES]
    return {"sound_events": [event for event in events if event["label"] not in PHASES],
            "phase_intervals": phases, "respiratory": respiratory_measurements(phases, duration),
            "analyzed_duration_s": duration}


def localize_wav(experiment: Path, wav: Path, *, fold: int = 0, minimum_s: float = 0,
                 merge_gap_s: float = 0, loader: Callable | None = None) -> dict:
    """Localize an explicitly supplied WAV with research weights; never register live."""
    config, folder, evaluation = _development(experiment, fold)
    localize_frames(np.array([]), np.empty((0, len(config["classes"]))), config["classes"], evaluation["thresholds"],
                    hop_s=config["hop_length"] / config["sample_rate"], duration_s=1,
                    minimum_s=minimum_s, merge_gap_s=merge_gap_s)
    policy = AudioPolicy()
    if wav.stat().st_size > policy.max_wav_bytes:
        raise ValueError("WAV exceeds the recorded-audio limit")
    data = wav.read_bytes()
    checked = AnalysisService().analyze_wav(data, "lung")
    if not checked["quality"]["valid"]:
        raise ValueError(f"Invalid Lung WAV: {checked['quality']['reason'] or checked['errors'][0]['code']}")
    with sf.SoundFile(BytesIO(data)) as file:
        rate, audio = file.samplerate, file.read(dtype="float64")
    with np.load(folder / "normalization.npz", allow_pickle=False) as normalization:
        mean, std = normalization["mean"], normalization["std"]
    if loader is None:
        from .heart_inference import load_keras_model
        loader = load_keras_model
    model = loader(folder / "model.keras")
    times, scores = predict_frames(audio, rate, config, mean, std, model)
    if not len(times):
        raise ValueError("No complete analyzed frames")
    result = _result(times, scores, config, evaluation["thresholds"], len(audio) / rate, minimum_s, merge_gap_s)
    return {"schema_version": "lung-localization-research-v1", "role": "development_only",
            "deployment_eligible": False, "training_started": False, "official_test_labels_opened": False,
            "localization_version": LOCALIZATION_VERSION, "classes": config["classes"], "fold": fold,
            "model_sha256": digest(folder / "model.keras"), "normalization_sha256": digest(folder / "normalization.npz"),
            "source_sha256": digest(experiment / "source.json"), "audio_sha256": digest(wav),
            "thresholds": evaluation["thresholds"], "postprocessing": {"minimum_s": minimum_s, "merge_gap_s": merge_gap_s},
            "frame_hop_s": config["hop_length"] / config["sample_rate"],
            "fft_support_s": config["n_fft"] / config["sample_rate"],
            "boundary_rule": "frame_center_plus_or_minus_half_hop; no extrapolation into unanalyzed edges",
            "frames": {"times_s": times.tolist(), "scores": scores.tolist()}, **result,
            "limitations": ["Research candidate; not authorized for live inference or diagnosis.",
                             "Onset/offset are frame-grid estimates, not validated timing accuracy.",
                             "Crackle labels describe crackle-containing periods, not individual clicks.",
                             "Independent phase outputs may overlap; unsupported respiratory measurements remain null.",
                             "Scores are uncalibrated; gap merging can include below-threshold frames."]}


def evaluate_development_localization(cache: Path, audit: Path, experiment: Path, *, fold: int = 0,
                                      minimum_s: float = 0, merge_gap_s: float = 0,
                                      tolerance_s: float = .1) -> dict:
    """Evaluate saved held-out predictions against source event intervals, without a model.

    Deduplicate overlapping windows by recording before one-to-one event matching.
    Cached truth/masks are checked against saved arrays to prove row alignment.
    """
    if not np.isfinite(tolerance_s) or tolerance_s < 0:
        raise ValueError("Nonnegative finite event tolerance required")
    config, folder, evaluation = _development(experiment, fold)
    localize_frames(np.array([]), np.empty((0, len(config["classes"]))), config["classes"], evaluation["thresholds"],
                    hop_s=config["hop_length"] / config["sample_rate"], duration_s=1,
                    minimum_s=minimum_s, merge_gap_s=merge_gap_s)
    cached_config, index = preflight(cache, audit)
    source = json.loads((experiment / "source.json").read_text())
    if (config != cached_config or source.get("index_sha256") != digest(cache / "index.csv")
            or source.get("audit_sha256") != digest(audit)):
        raise ValueError("Development predictions are not bound to this cache")
    order = json.loads((experiment / "prediction_index.json").read_text())
    order = [row for row in order if row["fold"] == fold]
    if not order or len({row["file"] for row in order}) != len(order):
        raise ValueError("Unique held-out prediction index required")
    held_groups = {str(group) for group in evaluation["groups"]}
    expected_files = set(index.loc[index.group.astype(str).isin(held_groups), "file"])
    if {row["file"] for row in order} != expected_files:
        raise ValueError("Prediction index must cover every held-out cache window")
    selected = index.set_index("file")
    recordings = pd.read_csv(audit.parent / "recordings.csv", dtype={"group": str}).set_index("recording_id")
    events = pd.read_csv(audit.parent / "events.csv")
    predictions = {}
    path = folder / "development_predictions.npz"
    with np.load(path, allow_pickle=False) as saved:
        truth, scores, masks = (saved[key] for key in ("truth", "scores", "mask"))
    if (truth.ndim != 2 or truth.shape[1] != len(config["classes"])
            or truth.shape != scores.shape or truth.shape != masks.shape
            or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1))
            or not np.isin(truth, [0, 1]).all() or not np.isin(masks, [0, 1]).all()):
        raise ValueError("Saved frame arrays disagree")
    offset = 0
    for row in order:
        if row["file"] not in selected.index:
            raise ValueError("Prediction row is not in development cache")
        item = selected.loc[row["file"]]
        if str(row["group"]) != str(item.group) or str(item.group) not in held_groups:
            raise ValueError("Prediction row is not in the held-out fold")
        record = recordings.loc[item.recording_id]
        if record.split not in {"train", "validation"} or record.split != item.split or str(record.group) != str(item.group):
            raise ValueError("Non-development recording rejected")
        with np.load(cache / row["file"], allow_pickle=False) as block:
            y, mask, start = block["targets"], block["mask"], int(block["start_sample"])
        end = offset + len(y)
        if not np.array_equal(truth[offset:end], y) or not np.array_equal(masks[offset:end], mask):
            raise ValueError("Saved predictions are misaligned with cache targets")
        valid = min(round(record.valid_end_s * config["sample_rate"]) - start,
                    round(config["window_seconds"] * config["sample_rate"]))
        predictions.setdefault(item.recording_id, []).append((start, scores[offset:end], valid))
        offset = end
    if offset != len(scores):
        raise ValueError("Unused/missing saved prediction frames")
    results = []
    totals = {label: {"tp": 0, "fp": 0, "fn": 0, "onset_error_sum_s": 0., "offset_error_sum_s": 0.}
              for label in config["classes"]}
    for identity, blocks in predictions.items():
        record = recordings.loc[identity]
        times, probability = merge_predictions(blocks, sample_rate=config["sample_rate"],
                                                hop_length=config["hop_length"], n_fft=config["n_fft"])
        result = _result(times, probability, config, evaluation["thresholds"], float(record.valid_end_s), minimum_s, merge_gap_s)
        predicted = result["phase_intervals"] + result["sound_events"]
        reference = events[(events.recording_id == identity) & (events.end_s <= record.valid_end_s)
                           & events.label.isin(config["classes"])].to_dict("records")
        metrics = {}
        for label in config["classes"]:
            metric = event_metrics([event for event in reference if event["label"] == label],
                                   [event for event in predicted if event["label"] == label],
                                   onset_tolerance_s=tolerance_s, offset_tolerance_s=tolerance_s)
            metrics[label] = metric
            for key in ("tp", "fp", "fn"):
                totals[label][key] += metric[key]
            if metric["tp"]:
                totals[label]["onset_error_sum_s"] += metric["onset_mae_s"] * metric["tp"]
                totals[label]["offset_error_sum_s"] += metric["offset_mae_s"] * metric["tp"]
        results.append({"recording_id": identity, "group": str(record.group), "device": record.device,
                        "reference_events": [{key: event[key] for key in ("label", "start_s", "end_s")} for event in reference],
                        "event_metrics": metrics, **result})
    for metric in totals.values():
        denominator = 2 * metric["tp"] + metric["fp"] + metric["fn"]
        metric["f1"] = 2 * metric["tp"] / denominator if denominator else None
        metric["onset_mae_s"] = metric.pop("onset_error_sum_s") / metric["tp"] if metric["tp"] else None
        metric["offset_mae_s"] = metric.pop("offset_error_sum_s") / metric["tp"] if metric["tp"] else None
        metric.pop("onset_error_sum_s", None)
        metric.pop("offset_error_sum_s", None)
    return {"schema_version": "lung-localization-evaluation-v1", "role": "development_only",
            "deployment_eligible": False, "training_started": False, "official_test_labels_opened": False,
            "localization_version": LOCALIZATION_VERSION, "prediction_sha256": digest(path),
            "index_sha256": digest(cache / "index.csv"), "source_sha256": digest(experiment / "source.json"),
            "classes": config["classes"], "thresholds": evaluation["thresholds"], "fold": fold,
            "postprocessing": {"minimum_s": minimum_s, "merge_gap_s": merge_gap_s},
            "boundary_tolerance_s": tolerance_s, "event_metrics": totals, "recordings": results,
            "limitations": ["Held-out development evaluation, not an independent final test.",
                             "Date groups do not establish patient independence.",
                             "Source labels are imperfect; crackles denote periods containing clicks."]}
