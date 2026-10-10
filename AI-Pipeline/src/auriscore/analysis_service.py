"""Recorded-audio routing independent of hardware, UI, and research experiments."""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Protocol

import numpy as np
import soundfile as sf

from .heart_result import analyze_heart

SCHEMA_VERSION = "organ-analysis-v1"
MODES = {"heart", "abdomen"}


@dataclass(frozen=True)
class AudioPolicy:
    """Central configurable engineering limits, not clinical quality thresholds."""

    max_wav_bytes: int = 16 * 1024 * 1024
    max_samples: int = 2_000_000
    max_duration_s: float = 120.0
    min_sample_rate: int = 1000
    max_sample_rate: int = 192000
    heart_min_duration_s: float = 3.0
    abdomen_min_duration_s: float = 5.0
    min_centered_rms: float = 1e-6
    max_clipping_ratio: float = 0.01

    def __post_init__(self) -> None:
        numbers = (self.max_duration_s, self.heart_min_duration_s,
                   self.abdomen_min_duration_s, self.min_centered_rms, self.max_clipping_ratio)
        if (not all(np.isfinite(value) for value in numbers)
                or self.max_wav_bytes <= 0 or self.max_samples <= 0
                or not 0 < self.min_sample_rate <= self.max_sample_rate
                or not 0 < self.heart_min_duration_s <= self.max_duration_s
                or not 0 < self.abdomen_min_duration_s <= self.max_duration_s
                or self.min_centered_rms <= 0 or not 0 <= self.max_clipping_ratio <= 1):
            raise ValueError("Invalid recorded-audio policy")


@dataclass(frozen=True)
class AnalysisError:
    code: str
    message: str
    component: str
    retryable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "component": self.component, "retryable": self.retryable}


@dataclass
class BackendOutput:
    """An organ result plus branch availability; no UI or transport dependency."""

    analysis: dict[str, Any]
    status: str = "completed"
    errors: list[AnalysisError] = field(default_factory=list)


class OrganBackend(Protocol):
    def analyze(self, audio: np.ndarray, sample_rate: int) -> BackendOutput: ...


class HeartDSPBackend:
    """Real existing DSP; a trained Murmur backend belongs to the next step."""

    def analyze(self, audio: np.ndarray, sample_rate: int) -> BackendOutput:
        result = analyze_heart(audio, sample_rate)
        return BackendOutput(result, "partial", [AnalysisError(
            "MODEL_UNAVAILABLE", "Heart DSP is available; no deployment Murmur model is configured.", "murmur")])


@dataclass(frozen=True)
class BackendDefinition:
    """Explicit integration registration; candidate packages are not auto-promoted."""

    mode: str
    backend_version: str
    factory: Callable[[], OrganBackend]
    model_version: str | None = None
    requires_model: bool = False
    deployment_eligible: bool = False


def candidate_backend(package: Path, factory: Callable[[], OrganBackend]) -> BackendDefinition:
    """Register an audited candidate while retaining its deployment prohibition."""
    from .model_audit import verify_package

    manifest = verify_package(package)
    version = f"{manifest['experiment_id']}:{manifest['files']['model.keras']['sha256'][:12]}"
    return BackendDefinition(manifest['mode'], "candidate-model-v1", factory,
                             model_version=version, requires_model=True,
                             deployment_eligible=manifest['deployment_eligible'])


class BackendSlot:
    """Load once and serialize calls for a potentially non-thread-safe model."""

    def __init__(self, definition: BackendDefinition):
        self.definition = definition
        self._backend: OrganBackend | None = None
        self._load_failed = False
        self._lock = RLock()

    def run(self, audio: np.ndarray, sample_rate: int) -> BackendOutput:
        with self._lock:
            if self._load_failed:
                raise BackendFailure("MODEL_LOAD_FAILED")
            if self._backend is None:
                try:
                    self._backend = self.definition.factory()
                    if not callable(getattr(self._backend, "analyze", None)):
                        raise TypeError("Backend must implement analyze")
                except Exception:
                    self._load_failed = True
                    raise BackendFailure("MODEL_LOAD_FAILED") from None
            try:
                return self._backend.analyze(audio, sample_rate)
            except Exception:
                raise BackendFailure("INFERENCE_FAILED") from None


class BackendFailure(Exception):
    def __init__(self, code: str):
        self.code = code


class AnalysisService:
    """Reusable synchronous service; one instance per worker/application process."""

    def __init__(self, *, backends: list[BackendDefinition] | None = None,
                 policy: AudioPolicy = AudioPolicy()):
        definitions = backends if backends is not None else [BackendDefinition(
            "heart", "heart-dsp-prototype-0.1.0", HeartDSPBackend)]
        self.policy = policy
        self._slots: dict[str, BackendSlot] = {}
        for definition in definitions:
            if not isinstance(definition.requires_model, bool) or not isinstance(definition.deployment_eligible, bool):
                raise ValueError("Backend eligibility flags must be booleans")
            if (definition.mode not in MODES or definition.mode in self._slots
                    or not isinstance(definition.backend_version, str) or not definition.backend_version):
                raise ValueError("Unsupported, duplicate, or unversioned backend")
            if definition.requires_model and (not isinstance(definition.model_version, str) or not definition.model_version):
                raise ValueError("Model-backed registrations require a model version")
            if definition.model_version is not None and not definition.requires_model:
                raise ValueError("Model versions must declare a model-backed registration")
            self._slots[definition.mode] = BackendSlot(definition)

    def _response(self, mode: str, request_id: str | None, source: str) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "request_id": request_id,
                "mode": mode, "source": source, "status": "error",
                "quality": {"valid": False, "reason": None}, "analysis": None,
                "backend_version": None, "model_version": None, "errors": []}

    @staticmethod
    def _error(result: dict[str, Any], code: str, message: str,
               component: str = "input", *, status: str = "error") -> dict[str, Any]:
        result["status"] = status
        result["errors"] = [AnalysisError(code, message, component).as_dict()]
        return result

    def _check_request(self, result: dict[str, Any]) -> bool:
        if not isinstance(result["mode"], str) or result["mode"] not in MODES:
            result["mode"] = None
            result["request_id"] = None
            self._error(result, "UNSUPPORTED_MODE", "Choose Heart or Abdomen analysis.")
            return False
        request_id = result["request_id"]
        if request_id is not None and (not isinstance(request_id, str) or len(request_id) > 128):
            result["request_id"] = None
            self._error(result, "INVALID_REQUEST", "Request ID must be a string of at most 128 characters.")
            return False
        return True

    def invalid_request(self, message: str) -> dict[str, Any]:
        """Return the same complete envelope for malformed transport requests."""
        return self._error(self._response(None, None, "unknown"), "INVALID_REQUEST", message, "transport")

    def analyze_pcm(self, samples: Any, sample_rate: int, mode: str, *,
                    encoding: str = "float", request_id: str | None = None,
                    _source: str = "pcm") -> dict[str, Any]:
        """Accept normalized mono float samples or explicitly encoded signed int16."""
        result = self._response(mode, request_id, _source)
        if not self._check_request(result):
            return result
        if (not isinstance(sample_rate, (int, np.integer)) or isinstance(sample_rate, (bool, np.bool_))
                or not self.policy.min_sample_rate <= sample_rate <= self.policy.max_sample_rate):
            return self._error(result, "INVALID_SAMPLE_RATE", "Audio sampling rate is unsupported.")
        try:
            audio = np.asarray(samples)
            if audio.ndim != 1 or audio.dtype.kind not in "iuf":
                raise ValueError("Expected numeric mono samples")
            if audio.size == 0:
                raise ValueError("Empty audio")
            if audio.size > self.policy.max_samples or audio.size / sample_rate > self.policy.max_duration_s:
                return self._error(result, "AUDIO_TOO_LARGE", "Recording exceeds the configured audio limit.")
            if encoding == "int16":
                if audio.dtype.kind not in "iu" or np.any(audio < -32768) or np.any(audio > 32767):
                    raise ValueError("Invalid signed int16 PCM")
                audio = audio.astype(np.float64) / 32768.0
            elif encoding == "float":
                audio = audio.astype(np.float64)
            else:
                raise ValueError("Unsupported PCM encoding")
            if not np.isfinite(audio).all() or np.any(np.abs(audio) > 1.0):
                raise ValueError("Samples must be finite normalized PCM")
        except (TypeError, ValueError, OverflowError):
            return self._error(result, "INVALID_AUDIO", "Provide finite mono PCM with an explicit supported encoding.")
        duration = float(audio.size / sample_rate)
        rms = float(np.sqrt(np.mean((audio - audio.mean()) ** 2)))
        clipping = float(np.mean(np.abs(audio) >= 0.999))
        minimum = self.policy.heart_min_duration_s if mode == "heart" else self.policy.abdomen_min_duration_s
        reason = ("signal_too_short" if duration < minimum else
                  "silent_signal" if rms < self.policy.min_centered_rms else
                  "clipped_signal" if clipping > self.policy.max_clipping_ratio else None)
        result["quality"] = {"valid": reason is None, "reason": reason,
                             "sample_rate": int(sample_rate), "duration_s": duration,
                             "centered_rms": rms, "clipping_ratio": clipping}
        if reason:
            return self._error(result, "LOW_SIGNAL_QUALITY", "Recording quality is insufficient; record again.", "quality")
        slot = self._slots.get(mode)
        if slot is None:
            return self._error(result, "MODEL_UNAVAILABLE", "No analysis backend is configured for this mode.", mode, status="unavailable")
        definition = slot.definition
        result.update(backend_version=definition.backend_version, model_version=definition.model_version)
        if definition.requires_model and not definition.deployment_eligible:
            return self._error(result, "MODEL_NOT_AUTHORIZED", "Configured model has no deployment eligibility decision.", mode, status="unavailable")
        audio.setflags(write=False)
        try:
            output = slot.run(audio, int(sample_rate))
        except BackendFailure as exc:
            return self._error(result, exc.code, "Analysis backend could not load or process this recording.", mode)
        try:
            if (not isinstance(output, BackendOutput) or output.status not in {"completed", "partial"}
                    or not isinstance(output.analysis, dict) or output.analysis.get("mode") != mode
                    or not isinstance(output.analysis.get("schema_version"), str)):
                raise ValueError("Backend result contract mismatch")
            if output.status == "completed" and output.errors:
                raise ValueError("Completed results cannot contain branch errors")
            result.update(status=output.status, analysis=output.analysis,
                          errors=[error.as_dict() for error in output.errors])
            json.dumps(result, allow_nan=False)
            if output.analysis.get("quality", {}).get("valid") is False:
                result["quality"].update(valid=False, reason=output.analysis["quality"].get("reason", "backend_quality_failure"))
                result["analysis"] = None
                return self._error(result, "LOW_SIGNAL_QUALITY", "Organ-specific signal quality is insufficient; record again.", "quality")
        except (TypeError, ValueError, AttributeError):
            result["analysis"] = None
            return self._error(result, "INVALID_ANALYSIS_RESULT", "Analysis backend returned an invalid result.", mode)
        return result

    def analyze_wav(self, data: bytes, mode: str, *, request_id: str | None = None) -> dict[str, Any]:
        """Decode bounded RIFF/WAVE bytes; preserve mono sample-rate information."""
        result = self._response(mode, request_id, "wav")
        if not self._check_request(result):
            return result
        if not isinstance(data, bytes) or not data or len(data) > self.policy.max_wav_bytes:
            return self._error(result, "INVALID_AUDIO", "Provide a nonempty WAV within the configured byte limit.")
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return self._error(result, "INVALID_AUDIO", "Audio must be a supported RIFF/WAVE recording.")
        try:
            with sf.SoundFile(BytesIO(data)) as recording:
                if recording.channels != 1:
                    return self._error(result, "INVALID_AUDIO", "Mono audio is required.")
                if recording.frames > self.policy.max_samples or recording.frames / recording.samplerate > self.policy.max_duration_s:
                    return self._error(result, "AUDIO_TOO_LARGE", "Recording exceeds the configured audio limit.")
                if not self.policy.min_sample_rate <= recording.samplerate <= self.policy.max_sample_rate:
                    return self._error(result, "INVALID_SAMPLE_RATE", "Audio sampling rate is unsupported.")
                audio = recording.read(dtype="float64")
                sample_rate = recording.samplerate
        except (OSError, RuntimeError, ValueError):
            return self._error(result, "INVALID_AUDIO", "WAV recording could not be decoded.")
        return self.analyze_pcm(audio, sample_rate, mode, request_id=request_id, _source="wav")
