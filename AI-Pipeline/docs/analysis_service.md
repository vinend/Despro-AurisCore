# Shared recorded-audio analysis service — step 2

`auriscore.analysis_service.AnalysisService` is the shared boundary between
recorded audio and organ-specific analysis. It accepts actual PCM/WAV data;
it does not generate simulator signals or classifications. Hardware, WebApp,
research training, and future mobile transports remain outside this service.

## Python API

```python
from pathlib import Path
from auriscore.analysis_service import AnalysisService

service = AnalysisService()  # retain this instance across recordings
result = service.analyze_wav(Path("recording.wav").read_bytes(), "heart")
result = service.analyze_pcm(samples, 8000, "abdomen", encoding="int16",
                             request_id="session-recording-1")
```

PCM must be mono, either normalized finite float values in [-1, 1] or signed
int16 integer samples explicitly identified by `encoding="int16"`. The service
scales int16 by 32768, but does not filter, resample, or apply model normalization;
those operations belong to each model backend's frozen preprocessing contract.
WAV input must be RIFF/WAVE bytes with one audio channel. Stereo is rejected.

`AudioPolicy` centralizes configurable engineering limits: 16 MiB WAV input,
2 million decoded samples, 120 seconds, 1000–192000 Hz, minimum 3 seconds for
Heart and 5 for Abdomen, centered RMS >=1e-6 and clipping fraction <=1%.
These are initial software/quality defaults, not clinical validation claims.
Empty, malformed, nonfinite, out-of-range, silent/DC-only, short and severely
clipped inputs cannot reach a backend. WAV dimensions are checked before decoding.

## Stable response

Every response uses `organ-analysis-v1`:

```json
{
  "schema_version": "organ-analysis-v1",
  "request_id": "session-recording-1",
  "mode": "heart",
  "source": "pcm",
  "status": "partial",
  "quality": {"valid": true, "reason": null},
  "backend_version": "heart-dsp-prototype-0.1.0",
  "model_version": null,
  "analysis": {"schema_version": "heart-analysis-v1", "mode": "heart"},
  "errors": [{"code": "MODEL_UNAVAILABLE", "message": "...", "component": "murmur", "retryable": false}]
}
```

The nested example abbreviates the existing full Heart result. Status is
`completed`, `partial`, `unavailable`, or `error`. `partial` retains a valid
independent analysis while naming its missing branch. `unavailable` means audio
is valid but the backend/model is not configured or eligible. Invalid audio
and backend failures never fabricate analysis. Errors contain stable codes,
user-facing messages, component and retryability, without exception text or paths.

Codes: `UNSUPPORTED_MODE`, `INVALID_REQUEST`, `INVALID_SAMPLE_RATE`,
`INVALID_AUDIO`, `AUDIO_TOO_LARGE`, `LOW_SIGNAL_QUALITY`, `MODEL_UNAVAILABLE`,
`MODEL_NOT_AUTHORIZED`, `MODEL_LOAD_FAILED`, `INFERENCE_FAILED`, and
`INVALID_ANALYSIS_RESULT`. Results must be finite JSON and match the requested mode.

## Backend lifecycle and model eligibility

`BackendDefinition` registers an explicit mode, backend version, factory, and
optional model version. `OrganBackend.analyze(audio, sample_rate)` returns a
`BackendOutput` with the organ's versioned analysis and any branch errors.
Factories are invoked lazily only after audio/eligibility checks. One service
instance caches one backend per mode and serializes its calls; concurrent
recordings do not reload a model. Initialization failures are cached as well;
restart/reconstruct the service after repairing configuration. Inference failures
return structured errors and do not leak implementation details.

A model-backed registration must declare `requires_model`, a version, and explicit
deployment eligibility. `candidate_backend(package, factory)` verifies step-1
package hashes and retains its `deployment_eligible: false` decision. It cannot
promote A005 or older Heart candidates into production models. The application
must not manufacture an eligibility decision by changing registration flags.

Default registration runs existing Heart DSP and returns `partial` with Murmur
unavailable. Unconfigured Abdomen returns `unavailable`. Step 3 adds the verified
Heart model adapter; phase 4 adds the window-level Abdomen inference backend.
Neither establishes new thresholds, trains models or changes H021's research status.

## CLI and persistent worker

From `AI-Pipeline` in this Windows workspace:

```powershell
$analysisPython = "$env:USERPROFILE\.codex\envs\auriscore-audit\Scripts\python.exe"
& $analysisPython scripts\analyze_recording.py --wav "recording.wav" --mode heart
& $analysisPython scripts\analyze_recording.py --serve
```

One-shot mode writes one response and exits 0 for completed/partial results,
1 for analysis errors/unavailability, or 2 for CLI/file-open errors. Worker mode
reads one JSON object per line and writes one flushed response per line, retaining
the service/backend instances until EOF. It accepts either `samples`,
`sample_rate`, `encoding`, `mode`, optional `request_id`, or `wav_base64`, `mode`,
optional `request_id`. Base64 and PCM inputs cannot be combined. Invalid requests
receive an error response and do not prevent the next recording from being read.
Lines over 24 MiB receive an error and terminate the worker with exit code 2.
The worker exposes no arbitrary file-path or model-loading command.

Phase 4 also accepts one-shot WAV bytes with `--stdin --mode heart|abdomen`.
`--heart-package` and `--abdomen-package` (or `AURISCORE_HEART_PACKAGE` and
`AURISCORE_ABDOMEN_PACKAGE`) register verified final packages before requests.
An Abdomen-only configuration preserves default Heart DSP. Both models can be
retained in one worker. See `abdomen_inference.md` for window activity semantics.

Step 3 connects the existing WebApp Heart bridge to an optional verified final
package through `AURISCORE_HEART_PACKAGE`, retaining `heart-analysis-v1`.
See `heart_inference.md`. This worker is local Python execution, not mobile
or browser-only inference and not a continuously running live classifier.

## Verification (2026-10-10)

38 service tests and 51 existing focused compatibility/audit tests passed
(89 total). Checks cover known 75 BPM synthetic Heart pulses, float/int16/WAV
parity, early invalid-input rejection, mode dispatch, concurrent one-time backend
loading, blocked candidate loading, cached initialization failures, finite-result
validation, organ-specific quality rejection, JSON-lines recovery, and base64 WAV
transport. Existing Heart DSP/bridge and H021 freeze checks remain passing.

No model training, external validation or sealed-test evaluation was performed.
