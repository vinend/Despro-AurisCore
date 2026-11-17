"""Frozen A105 candidate event detection for an authenticated engineering demo."""
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from .abdomen_sed_inference import BowelEventScorer, N_MELS, WINDOW_SECONDS
from .analysis_service import AnalysisError, BackendDefinition, BackendOutput
from .model_audit import digest

VERSION = "EXP-A105-abdomen-crnn-specaugment-noise"
MODEL_SHA256 = "7d4a2c0eee1bb08fbda7df02c5272aa5fd3956b6f870a471acce43cfa6b90010"
METADATA_SHA256 = "22ae0c2438c2475fc9256e36e8c81879feb56bf60958e21a8308d471b3d0a690"


class A105EngineeringBackend:
    def __init__(self, folder: Path):
        raw_metadata = (folder / "tflite_metadata.json").read_bytes().replace(b"\r\n", b"\n")
        if digest(folder / "best_model.keras") != MODEL_SHA256 or sha256(raw_metadata).hexdigest() != METADATA_SHA256:
            raise ValueError("A105 asset hash mismatch")
        metadata = json.loads(raw_metadata)
        normalization = metadata["audio_preprocessing"]["normalization"]
        mean, std = (np.asarray(normalization[key], dtype=np.float32) for key in ("mean_freq", "std_freq"))
        if mean.shape != (N_MELS,) or std.shape != mean.shape or not np.isfinite([mean, std]).all() or np.any(std <= 0):
            raise ValueError("Invalid A105 normalization")
        policy = metadata["event_detection_postprocessing"]
        profile = policy["operating_profiles"][policy["default_profile"]]
        self.scorer = BowelEventScorer(folder / "best_model.keras", {
            "onset_threshold": profile["onset"], "offset_threshold": profile["offset"],
            "min_duration_ms": policy["min_duration_seconds"] * 1000,
            "merge_gap_ms": policy["merge_gap_seconds"] * 1000,
            "spectrogram_normalization_clip": normalization["clip_max"],
        }, frozen_normalization=(mean, std))

    def analyze(self, audio: np.ndarray, sample_rate: int) -> BackendOutput:
        events, analyzed, duration = self.scorer.score_events(audio, sample_rate)
        intervals = []
        for event in events:
            # The last centered frame sits on the next window's start.
            start = event["start_s"]
            window_end = (int(start / WINDOW_SECONDS) + 1) * WINDOW_SECONDS
            end = min(event["end_s"], window_end, analyzed)
            if start < end:
                intervals.append({"start_s": start, "end_s": end, "score": event["peak_confidence"]})
        analysis = {
            "schema_version": "abdomen-analysis-v1", "mode": "abdomen",
            "quality": {"valid": True, "reason": None}, "activity": None,
            "bowel_events": intervals, "bowel_rate_per_minute": None,
            "bowel_rate_variability": None, "pattern_categories": None,
            "event_detection": {
                "schema_version": "abdomen-event-candidates-v1", "model_version": VERSION,
                "analyzed_duration_s": analyzed, "discarded_tail_s": max(0., duration - analyzed),
                "onset_threshold": self.scorer.onset_threshold, "offset_threshold": self.scorer.offset_threshold,
            },
            "limitations": ["Engineering acoustic candidates. Event boundaries and motility measures require validation."],
        }
        return BackendOutput(analysis, "partial", [
            AnalysisError("ABDOMEN_MOTILITY_NOT_VALIDATED", "Motility metrics require validation.", "bowel_events")
        ])


def a105_definition(pipeline: Path) -> BackendDefinition:
    folder = pipeline / "results" / VERSION
    return BackendDefinition("abdomen", "abdomen-a105-engineering-v1", lambda: A105EngineeringBackend(folder),
                             VERSION, requires_model=True, deployment_eligible=False, engineering_test_only=True)
