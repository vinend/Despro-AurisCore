"""Production inference backend for Abdomen Sound Event Detection (SED) and Event Analytics.

Integrates CRNN model (EXP-A105) with report-aligned metrics:
- Frame-level acoustic burst probability curve P(t)
- Discrete event onset/offset detection
- Bowel Rate (events/minute & motility interpretation)
- Bowel Rate Variability (inter-event interval statistics)
- Pattern categorization (Single Burst, Multiple Burst, Prolonged / CRS)
- Conforms to abdomen-analysis-v1 schema inside organ-analysis-v1
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy.signal import butter, sosfilt

from .abdomen_sed_analytics import build_unified_abdomen_analysis
from .analysis_service import AnalysisError, BackendDefinition, BackendOutput
from .cnn import require_tensorflow
from .sed_postprocessing import extract_events_from_curve

LOG = logging.getLogger(__name__)

BACKEND_VERSION = "abdomen-sed-inference-v1"
RESULT_SCHEMA = "abdomen-analysis-v1"
TARGET_SR = 8000
WINDOW_SECONDS = 2.0
WINDOW_SAMPLES = int(TARGET_SR * WINDOW_SECONDS)  # 16,000 samples
HOP_LENGTH = 128
HOP_S = HOP_LENGTH / float(TARGET_SR)  # 0.016 s
N_MELS = 40
N_FFT = 512
FMIN = 100.0
FMAX = 1000.0


def default_model_loader(path: Path) -> Any:
    """Load Keras model in inference-only mode."""
    tf = require_tensorflow()
    return tf.keras.models.load_model(str(path), compile=False)


class BowelEventScorer:
    """Extracts continuous acoustic burst probability and events from arbitrary audio."""

    def __init__(
        self,
        model_path: Path,
        config: dict[str, Any] | None = None,
        loader: Callable[[Path], Any] = default_model_loader,
    ):
        self.model_path = Path(model_path).resolve()
        if not self.model_path.exists():
            raise FileNotFoundError(f"CRNN SED model not found at {self.model_path}")

        self.config = config or {}
        self.loader = loader
        self._model: Any = None

        # Pre-compute bandpass filter (100 - 1000 Hz at 8000 Hz)
        self.sos = butter(4, [FMIN, FMAX], btype="bandpass", fs=TARGET_SR, output="sos")

        # Configurable operating thresholds (default: balanced clinical screening profile)
        self.onset_threshold = float(self.config.get("onset_threshold", 0.45))
        self.offset_threshold = float(self.config.get("offset_threshold", 0.36))
        self.merge_gap_ms = float(self.config.get("merge_gap_ms", 20.0))
        self.min_duration_ms = float(self.config.get("min_duration_ms", 25.0))
        self.clip_val = float(self.config.get("spectrogram_normalization_clip", 5.0))

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = self.loader(self.model_path)
        return self._model

    def preprocess_audio(self, audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, float]:
        """Validate, resample, and filter input audio."""
        import librosa

        sig = np.asarray(audio, dtype=np.float32).flatten()
        if len(sig) == 0 or not np.all(np.isfinite(sig)):
            raise ValueError("Input audio is empty or contains non-finite values.")

        if sample_rate != TARGET_SR:
            sig = librosa.resample(sig, orig_sr=sample_rate, target_sr=TARGET_SR)

        # Minimum required audio duration is 2.0 seconds (1 window)
        duration_s = len(sig) / float(TARGET_SR)
        if duration_s < WINDOW_SECONDS:
            raise ValueError(
                f"Audio duration ({duration_s:.2f}s) is too short. Minimum {WINDOW_SECONDS}s is required for Abdomen analysis."
            )

        # 4th-order Butterworth bandpass filter (100 - 1000 Hz)
        filtered = sosfilt(self.sos, sig).astype(np.float32)
        return filtered, duration_s

    def extract_logmel(self, chunk: np.ndarray) -> np.ndarray:
        """Extract log-mel spectrogram for a 2.0-second chunk (40, 126)."""
        import librosa

        mel = librosa.feature.melspectrogram(
            y=chunk,
            sr=TARGET_SR,
            n_fft=N_FFT,
            hop_length=HOP_LENGTH,
            n_mels=N_MELS,
            fmin=FMIN,
            fmax=FMAX,
            power=2.0,
        )
        logmel = librosa.power_to_db(mel, ref=np.max, top_db=80.0).astype(np.float32)
        return logmel

    def score_audio(self, audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
        """Score full audio signal, extract events, and compute analytics."""
        filtered_audio, duration_s = self.preprocess_audio(audio, sample_rate)

        # Slice into 2.0s non-overlapping windows
        step = WINDOW_SAMPLES
        mel_list: list[np.ndarray] = []
        window_offsets: list[float] = []

        for start_sample in range(0, len(filtered_audio) - step + 1, step):
            chunk = filtered_audio[start_sample : start_sample + step]
            logmel = self.extract_logmel(chunk)
            mel_list.append(logmel)
            window_offsets.append(start_sample / float(TARGET_SR))

        if not mel_list:
            raise ValueError("No complete 2.0-second windows available for analysis.")

        mels_arr = np.array(mel_list, dtype=np.float32)  # (N_windows, 40, 126)

        # Per-frequency normalization across windows
        mean_freq = np.mean(mels_arr, axis=(0, 2), keepdims=True)
        std_freq = np.std(mels_arr, axis=(0, 2), keepdims=True)
        std_freq = np.where(std_freq < 1e-6, 1.0, std_freq)

        norm_mels = (mels_arr - mean_freq) / std_freq
        norm_mels = np.clip(norm_mels, -self.clip_val, self.clip_val)[..., np.newaxis]

        # Model batch prediction
        preds = self.model.predict(norm_mels, batch_size=32, verbose=0)  # (N_windows, 126, 1)

        # Extract events per window and offset timestamps
        all_events: list[dict[str, Any]] = []
        for w_idx, w_offset in enumerate(window_offsets):
            probs = preds[w_idx, :, 0]
            win_events = extract_events_from_curve(
                probs,
                hop_s=HOP_S,
                window_start_s=0.0,
                onset_threshold=self.onset_threshold,
                offset_threshold=self.offset_threshold,
                min_duration_ms=self.min_duration_ms,
                merge_gap_ms=self.merge_gap_ms,
            )
            for e in win_events:
                e_global = dict(e)
                e_global["start_s"] = round(e["start_s"] + w_offset, 3)
                e_global["end_s"] = round(e["end_s"] + w_offset, 3)
                all_events.append(e_global)

        # Build full unified analysis result
        analyzed_duration = float(len(window_offsets) * WINDOW_SECONDS)
        analysis = build_unified_abdomen_analysis(
            events=all_events,
            analyzed_duration_s=analyzed_duration,
            model_version=str(self.config.get("model_version", "EXP-A105-abdomen-crnn-specaugment-noise")),
            threshold_profile=f"onset_{self.onset_threshold}_offset_{self.offset_threshold}",
        )
        return analysis


class AbdomenSEDBackend:
    """Backend service worker wrapping BowelEventScorer for AnalysisService registration."""

    def __init__(
        self,
        model_path: Path,
        config: dict[str, Any] | None = None,
        loader: Callable[[Path], Any] = default_model_loader,
    ):
        self.scorer = BowelEventScorer(model_path, config=config, loader=loader)

    def analyze(self, audio: np.ndarray, sample_rate: int) -> BackendOutput:
        try:
            result = self.scorer.score_audio(audio, sample_rate)
            return BackendOutput(result, "completed", [])
        except ValueError as exc:
            return BackendOutput(
                {
                    "schema_version": RESULT_SCHEMA,
                    "mode": "abdomen",
                    "quality": {"valid": False, "reason": str(exc)},
                    "activity": None,
                    "bowel_events": None,
                    "bowel_rate_per_minute": None,
                    "bowel_rate_variability": None,
                    "pattern_categories": None,
                    "limitations": ["Audio processing failed quality checks."],
                },
                "failed",
                [AnalysisError("ABDOMEN_AUDIO_INVALID", str(exc), "bowel_audio_input")],
            )
        except Exception as exc:
            LOG.exception("Unexpected error during Abdomen SED analysis: %s", exc)
            return BackendOutput(
                {
                    "schema_version": RESULT_SCHEMA,
                    "mode": "abdomen",
                    "quality": {"valid": False, "reason": "INTERNAL_ERROR"},
                    "activity": None,
                    "bowel_events": None,
                    "bowel_rate_per_minute": None,
                    "bowel_rate_variability": None,
                    "pattern_categories": None,
                    "limitations": ["Internal analysis failure."],
                },
                "failed",
                [AnalysisError("ABDOMEN_INTERNAL_ERROR", str(exc), "bowel_event_analysis")],
            )


def abdomen_sed_backend_definition(
    model_path: Path,
    config: dict[str, Any] | None = None,
) -> BackendDefinition:
    """Factory creating an AnalysisService-compatible BackendDefinition."""
    return BackendDefinition(
        mode="abdomen",
        backend_version=BACKEND_VERSION,
        factory=lambda: AbdomenSEDBackend(model_path, config=config),
        model_version=str((config or {}).get("model_version", "EXP-A105-abdomen-crnn-specaugment-noise")),
        requires_model=True,
        deployment_eligible=True,
    )
