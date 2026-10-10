# INTEGRATION.md

## 1. Purpose

Define versioned interfaces between:

- ESP32;
- mobile;
- local DSP/AI analysis;
- backend/storage;
- tele-auscultation.

This document should change before or together with any breaking interface change.

Product-required outputs come from `PRD.md`.

---

## 2. Research artifact interface

The preparatory `model-candidate-v1` package contains a normalized `manifest.json`,
`model.keras`, `source_metadata.json`, and `source_metrics.json`. Its manifest
records mode, acoustic target, source experiment, preprocessing, input shape,
threshold value/selection unit, runtime audit status, and file SHA-256/byte counts.
It always has `deployment_eligible: false` and no authorized inference rule.
This is an artifact-audit contract, not a live analysis response or model registry.
See `AI-Pipeline/docs/model_candidate_audit.md` for commands and limitations.

Heart AI experiments use immutable directories such as:

```text
AI-Pipeline/results/EXP-HNNN-name/
```

Research artifacts may include:

- `protocol.json`;
- `config.json`;
- `metrics.json`;
- predictions/fold metrics;
- threshold/calibration analysis;
- training history;
- model checkpoint;
- plots;
- `summary.md` / `summary.json`.

These research artifacts are **not** the mobile result contract.

Managed training may also create request/status/checkpoint artifacts. The final holdout remains outside normal training-queue iteration.

---

## 3. ESP32 -> Mobile

Transport: BLE.

Target stream concept:

- mono PCM/integer audio samples;
- nominal sample rate: 8000 Hz;
- sequence/timestamp metadata sufficient for reconstruction and packet-loss detection.

Exact packet format remains versioned/TBD until firmware contract is locked.

Recommended metadata:

```text
sequence_number
timestamp
sample_count
payload
```

Mobile must detect at least:

- duplicate packets;
- missing sequence numbers;
- buffer underrun;
- malformed packets;
- unsupported sample rate.

---

## 4. Mobile -> Analysis

Step 2 introduces `organ-analysis-v1` for the shared Python recorded-audio service.
PCM inputs declare mode (`heart|abdomen`), sample rate, mono samples, encoding
(`float|int16`) and optional request ID. WAV bytes are accepted through the same
boundary. Responses include request ID, mode, source, status, quality, backend/
model versions, nested organ analysis, and structured component errors. Missing
or ineligible models remain unavailable. The current WebApp endpoint still uses
`heart-analysis-v1`; no existing client schema is replaced in this step.
See `AI-Pipeline/docs/analysis_service.md` for the complete contract and worker.

Stable logical input:

```json
{
  "audio_samples": "<buffer>",
  "sample_rate": 8000,
  "mode": "heart|lung|abdomen",
  "session_metadata": "optional"
}
```

Analysis code must not depend directly on BLE implementation details.

Preferred boundary:

```text
AudioBuffer -> OrganAnalysisService
```

For Heart:

```text
AudioBuffer -> HeartAnalysisService
```

---

## 5. Heart internal analysis contract

Heart analysis fans out into three branches:

```text
HeartAnalysisService
  +--> HeartRhythmDSP
  +--> CardiacEventDSP
  +--> MurmurInferenceService
  +--> HeartResultAggregator
```

The aggregator is responsible for producing a single versioned result.

A branch may be temporarily unavailable during implementation, but missing functionality must be explicit rather than fabricated.

### Current WebApp file-simulator bridge

For the development demo, `WebApp` implements `HeartAnalysisService` through
`POST /api/heart/analyze` (same-origin Next.js route). The request is
`multipart/form-data` with one `audio` WAV file, maximum 16 MiB. The route
requires a RIFF/WAVE header, passes bytes through stdin to the existing
`AI-Pipeline/scripts/analyze_heart_wav.py --stdin`, validates the returned
`heart-analysis-v1` JSON, and sends it to the browser. It does not store the
uploaded file. Malformed uploads receive a JSON `error` and HTTP 4xx; a
missing local Python environment receives HTTP 503. The UI treats a malformed
schema as a service failure.

This is a local, server-backed development adapter. It is not browser-only
Python execution and does not satisfy the PRD's eventual offline smartphone
inference requirement. The WebApp now also captures validated PCM packets from
its existing WebSocket/mock-device stream, converts them to mono WAV, and uses
the **same** `HeartAnalysisService` and `heart-analysis-v1` result view as file
input. Sequence gaps/malformed packets invalidate the capture instead of
inventing analysis samples. The older recording card still shows a simulated
classification and must not be confused with the Heart DSP stream panel.
No Murmur model is loaded by this bridge, so a valid DSP result reports
`murmur.status: unavailable`. Physical BLE and session persistence remain open.
`HARDWARE_AUDIO_CONTRACT.md` records the known mock format and the unknown
physical BLE UUIDs, packet bytes, and control commands.

H021 research metadata is now frozen under
`AI-Pipeline/analysis/HEART-DEVELOPMENT-FREEZE-H021/`. The Python WAV bridge
loads its lightweight manifest through a participant-level Murmur service
boundary. This service deliberately returns `unavailable`: H021 produced only
five fold-evaluation pipelines, with no final deployment model or predeclared
ensemble. It never uses a fold checkpoint, logistic head, or the pooled OOF
threshold for a single WAV. Heart DSP still returns `heart-analysis-v1` when
this manifest is missing, incompatible, or the Murmur service fails. The
contract fields remain unchanged; `model_version` and probability stay null
while Murmur is unavailable. Participant inference will require one or more
recordings and a separately approved deployment pipeline. Single-recording
H021 performance cannot be inferred from participant-level OOF metrics.

---

## 6. Analysis -> Mobile: unified Heart result

Target schema concept:

```json
{
  "schema_version": "heart-analysis-v1",
  "mode": "heart",
  "quality": {
    "valid": true,
    "score": null,
    "reason": null
  },
  "rhythm": {
    "algorithm_version": "heart-dsp-prototype-0.1.0",
    "heart_rate_bpm": 78,
    "label": "normal",
    "irregular": false,
    "interval_std_ms": 2.0,
    "beat_intervals_ms": [],
    "usable_intervals": 0
  },
  "cardiac_events": {
    "algorithm_version": "heart-dsp-prototype-0.1.0",
    "status": "paired_candidates",
    "candidate_times_s": [],
    "s1_times_s": [],
    "s2_times_s": [],
    "s3_candidates_s": [],
    "s4_candidates_s": [],
    "systolic_intervals": [],
    "diastolic_intervals": [],
    "systolic_interval_ms": null,
    "diastolic_interval_ms": null
  },
  "murmur": {
    "status": "available",
    "model_version": "",
    "preprocessing_version": "",
    "threshold_version": "",
    "probability": 0.82,
    "threshold": 0.3,
    "label": "present"
  },
  "visualization": {
    "waveform_available": true,
    "spectrogram_available": false,
    "event_annotations_available": true
  }
}
```

Exact field names may evolve through a versioned decision, but the result must remain capable of representing all three Heart branches.

The Python prototype in `AI-Pipeline/src/auriscore/heart_result.py` emits this
`heart-analysis-v1` structure from `analyze_heart(mono_audio, sample_rate,
murmur=...)`. Its DSP branch is CPU-only. `murmur` is an optional already-scored
result with probability, threshold, and model version; the aggregator does not
load a CNN or select a model. With no supplied Murmur result, `murmur.status`
is `unavailable` and its value fields are null. With insufficient S1/S2 evidence,
the audio can be valid while `cardiac_events.status` is
`insufficient_evidence`, BPM is null, and the rhythm label is `unknown`.
S1/S2 and S3/S4 timestamps are candidate detections. The rhythm label and
irregularity flag are prototype screening rules, not disease diagnoses.
`spectrogram_available` is false because this CPU adapter does not generate a
spectrogram visualization. The WebApp now displays the structured file-demo
result; mobile/BLE integration and labeled-recording validation remain pending.

### Transitional compatibility

A temporary murmur-only implementation may return only the `murmur` branch during development, but must not be called the final Heart contract.

---

## 7. Invalid/low-quality signal contract

Do not force clinical-looking results from unusable input.

Example:

```json
{
  "schema_version": "heart-analysis-v1",
  "mode": "heart",
  "quality": {
    "valid": false,
    "score": 0.12,
    "reason": "low_signal_quality"
  },
  "rhythm": null,
  "cardiac_events": null,
  "murmur": null
}
```

The current Python implementation uses `quality.score: null` for invalid audio;
it has not calibrated a numerical quality score. It rejects empty, nonfinite,
too-short, silent/near-silent, non-mono, or unsupported-rate input. It suppresses
all analysis branches when quality is invalid, even if a Murmur result was
supplied separately.

Reason codes should be explicit/versioned where possible.

---

## 8. Lung and Abdomen result direction

Lung and Abdomen must use their own versioned organ-result schemas rather than overloading Heart fields.

Lung result should eventually represent respiratory-phase metrics and wheeze/crackle/rhonchi findings.

Abdomen result should eventually represent bowel events, rate/variability, report-defined pattern categories, and annotations.

Phase 4 adds `abdomen-analysis-v1` inside the shared `organ-analysis-v1` envelope.
Its `activity` branch reports timestamped binary bowel-activity window scores,
labels, threshold and model/preprocessing/threshold versions. The active-window
fraction counts overlapping windows; it is not event rate or duration fraction.
Event/rate/variability/pattern fields remain explicitly null until separately
implemented and validated. Missing or failed models never create activity labels.
See `AI-Pipeline/docs/abdomen_inference.md` for the full contract. The shared Python
worker supports both packages; WebApp Abdomen transport and display are now wired
in phase 5 through the existing backend.

---

## 9. Mobile -> Backend

Recommended resource direction:

```text
POST /api/v1/sessions
GET  /api/v1/sessions/{id}
POST /api/v1/sessions/{id}/analysis
POST /api/v1/sessions/{id}/recordings
```

Exact endpoints may change, but breaking changes require versioning.

Store result schema version and algorithm/model versions with persisted analysis metadata.

The backend must not become a hidden requirement for local inference.

---

## 10. Tele-auscultation

Preferred media path:

```text
Mobile -> WebRTC -> Remote Client
```

Backend may provide:

- room creation;
- signaling;
- authentication;
- session metadata.

Do not route live audio through database persistence unless a deliberate media-server architecture is accepted.

Measure actual latency; do not assume the report target is automatically achieved.

---

## 11. Error model

Use explicit errors instead of generic failures.

Examples:

```text
BLE_DISCONNECTED
BLE_PACKET_LOSS
AUDIO_BUFFER_UNDERRUN
INVALID_SAMPLE_RATE
LOW_SIGNAL_QUALITY
DSP_ANALYSIS_FAILED
MODEL_LOAD_FAILED
INFERENCE_FAILED
SCHEMA_VERSION_UNSUPPORTED
BACKEND_UNAVAILABLE
WEBRTC_CONNECTION_FAILED
```

Mobile UI maps technical failures into safe, useful user actions.

## Existing Heart backend configuration (step 3)

The existing /api/heart/analyze route now shares the retained analyze_recording.py
worker with /api/analysis and /api/abdomen/analyze. Configure
AURISCORE_HEART_PACKAGE with an absolute verified final package path and configure
AURISCORE_PYTHON with the CNN-capable runtime. Invalid packages return HTTP 503;
no package retains DSP with unavailable Murmur. The response remains heart-analysis-v1.
The shared bridge retains Python/models across requests. See WebApp/docs/organ-analysis.md.

## Shared app analysis endpoint (phase 5)

POST /api/analysis accepts multipart audio (mono WAV) and mode (heart|abdomen),
returning organ-analysis-v1. /api/abdomen/analyze fixes Abdomen mode; the existing
/api/heart/analyze preserves heart-analysis-v1 for older clients. Partial results
return 200, invalid audio 422, and model unavailable 503. Typed unavailable/quality
responses remain renderable. Actual multipart body, WAV and worker output sizes
are bounded. Correlation IDs isolate queued requests; timeout/cancellation clears
the active process tree. The firmware protocol and physical BLE contract remain
unchanged. See WebApp/docs/organ-analysis.md for fields/lifecycle details.

## Wi-Fi physical device software contract (2026-10-10)

User-selected Wi-Fi/WebSocket now supplements the earlier BLE target. v2 uses
/device publisher and /browser controller routes with explicit pairing, 8 kHz
mono PCM16 little-endian in 832-byte binary frames, JSON handshake/acknowledged
commands and sample-clock continuity. See DEVICE_STREAMING_PROTOCOL.md for the
exact header, queue/timeout limits, error states and source provenance. Legacy
mock JSON v1 is retained; its mirrored quality enum adds unknown for the normalized
physical-source boundary (no fabricated quality measurement). Physical capture
needs the acquisition driver and bench verification. Model activation is unchanged.

## Lung recorded-audio contract

POST /api/analysis with mode=lung, or /api/lung/analyze with multipart audio WAV.
The organ-analysis-v1 envelope adds Lung and nullable lung-analysis-v1 output;
Heart/Abdomen shapes are preserved. Older strict mode validators need updating.
AURISCORE_LUNG_PACKAGE selects a verified package. Missing packages return HTTP503
unavailable with analysis=null. Minimum Lung audio is five seconds, capture is
30 seconds and API maximum remains 120 seconds. The result contains supported
classes, phase/sound intervals, uncalibrated frame scores and thresholds, nullable
respiratory metrics with a reason, analyzed duration and model version. At least
three complete unambiguous cycles are required. The strict schema is in
WebApp/src/lib/auriscore/lung-result.ts. Unsupported outputs never become diagnoses.
