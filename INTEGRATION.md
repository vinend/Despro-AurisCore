# INTEGRATION.md

Cloud account access (2026-11-21): GET /api/device-access accepts Authorization:
Bearer <Supabase access token> and returns only device availability/label or 403.
The cloud WebSocket authenticate.token is that account token for the browser;
the device continues using its private device credential. Browser credentials
are checked against verified Supabase identity and AURISCORE_DEVICE_ACCOUNT_EMAILS
(a server-only comma-separated assignment for the single namespace/device).
The existing X-AurisCore-Operator-Token analysis header carries the account
token in production. Legacy static analysis credentials remain only for local
engineering deployments without the assignment setting. Missing assignment in
Vercel production fails closed.
The account token and operator/device secrets are never returned by device-access.

Account UI starts at `/`; `/settings` manages profiles and requests Auth email
changes with a confirmation redirect to `/settings`. Database/result schemas
and private WAV ownership are unchanged.

Authenticated account persistence uses Supabase Auth and the tables
`auriscore_profiles` and `auriscore_sessions`. Email comes from Auth;
profiles contain name, date of birth and gender. Saved sessions retain the
versioned `organ-analysis-v1` result, recording time, organ, source,
duration, immutable audio SHA-256, size, and private object path.
The WAV path is `<auth-user-uuid>/<session-uuid>.wav` in
`auriscore-recordings`. RLS limits rows and object reads to their owner.
Uploads progress from `uploading` to `ready`. Retries reuse their UUID and
verify an already uploaded object's bytes before finishing. Session results
are immutable after insertion. The UI paginates saved history and downloads
audio with the user's token for local playback.

The Vercel engineering gateway accepts authenticated WebSockets at
`/api/gateway/device` and `/api/gateway/browser`, with separate device/account
credentials and an exact allowed browser origin. The v2 binary frame and JSON
control formats are shared with LAN. A device profile uses
`wss://<hostname>` to select TLS on port 443 and the cloud device path.
The browser sends its account credential as `X-AurisCore-Operator-Token`
for cloud requests to the existing analysis API. Its backend forwards raw PCM
or WAV to `POST /v1/analysis/{mode}/{pcm|wav}` over HTTPS with a server-only
bearer token. Cloud WAV inputs are capped at 4 MiB. Existing analysis result
schemas and 8 kHz live window sizes apply in both modes.

Cloud capture tolerates up to 7 seconds without incoming audio while the
connection remains open. Firmware 0.3.3 uses a PSRAM queue for up to 140
50 ms blocks and discards an entire stream if queued audio exceeds 6.5 seconds.
Boards without available PSRAM use 40 blocks. Buffered frames retain their
original order and sample clock. The recording clock advances only on received
samples. Disconnects and sample gaps still invalidate an active recording.
The binary frame and LAN stall threshold are unchanged. Cloud device uploads
can group up to four consecutive frames in one WebSocket message. The gateway
verifies the entire group before publishing it to the relay and sends individual
v2 frames to the browser. Previous devices sending one frame remain supported.
Redis PCM publishes are ordered with at most 32 responses pending. If the
deployment configures HTTPS Redis credentials, a single in-flight HTTP
pipeline publishes queued audio into the same instance as the TCP subscriber.
A slow publish reply or connection health check does not stall PCM parsing.
Lease loss, publish failure or backlog overflow still ends the stream.
Each authorized publish renews its 20-second lease in the same Redis operation.
Browser heartbeats also renew the browser lease, independently of server timers.
The WebApp pins its cloud gateway function to Singapore (`sin1`) to shorten
the relay path for the current deployment; the analysis route is independent.

Abdomen engineering A105 returns a partial `abdomen-analysis-v1` result
with `event_detection.schema_version=abdomen-event-candidates-v1`.
`bowel_events` contains ordered candidate intervals in seconds with their
uncalibrated peak scores. The scope is `engineering_test_only`. The result
identifies the analyzed duration, discarded tail, and thresholds. Window
activity, bowel rate, variability and pattern categories are null for this
backend. The existing window-classifier payload continues to use null events.

2026-11-16 device integration: normal use remains the main AurisCore `/` workspace,
with Heart/Lung/Abdomen. `/device-link-test` is an isolated engineering diagnostic;
it never requests audio or inference and is not the normal examination page.
The main device form now includes browser-based Wi-Fi setup instructions.

Wi-Fi capture 0.3.0 retains gateway v2, GPIO16/18/17, stereo I2S input and organ-only
8 kHz PCM. A temporary, per-device WPA2 setup AP serves `/setup` at 192.168.4.1.
It opens on an unconfigured device, after a full unsuccessful profile cycle (at
least 30 s), or after holding BOOT/GPIO0 for 3 s after normal boot. It closes after
10 minutes, or reboots after a valid configuration save. Setup HTTP is rejected
on the ordinary station/LAN interface; configuration requires an AP-origin session
nonce. No password or existing pairing token is returned in HTML. Four-profile
upsert, priority and fallback remain intact. Setup preserves the current pairing
when the submitted token is blank. Ordinary boot/status never prints the setup key;
the physically connected owner may explicitly request SETUP_INFO once for labeling.
SETUP_WIFI/SETUP_CLOSE are diagnostic serial controls. Saved Wi-Fi reconnects
automatically; the ESP32 does not discover or follow a phone's current SSID.
Local gateway reachability and correct per-network host are still required;
cloud WSS deployment is separate. This does not add a cellular modem or BLE relay.

The 127-tap FIR now skips discarded odd-phase sums while retaining every input,
coefficients, emitted accumulation order, rounding and phase. CAPTURE_FAULT_CODE
distinguishes read errors (1), short reads (2), DMA faults (3), and full output
queues (4), while existing source_error still terminates failed streams.
No model, scientific parameter, preprocessing coefficient or medical claim changes.

Wi-Fi init-only bench control (2026-11-14): WIFI_INIT_ONLY_V1 separates direct
driver initialization from manual esp_wifi_start. S reports DRIVER_READY,
RADIO_STARTED, ATTEMPTED and uptime; R attempts one radio start per boot. It
does not connect or scan. Default brownout protection remains enabled. The
original S3 completes driver initialization but resets with a brownout message
on esp_wifi_start. This diagnostic serial interface is separate from gateway
audio transport. README was not updated at user request.

Wi-Fi diagnostic build fix (2026-11-14): DisableBrownout now adds a C++ compiler
flag while preserving PSRAM/board defines. Serial RUNTIME_SDK, FLASH_BYTES,
PSRAM_BYTES and BUILD_PSRAM_ENABLED expose effective configuration. The pre-radio
BROWNOUT_HW_ENABLE reads the actual detector enable bit. WIFI_MODE_READY is
printed only if WiFi.mode succeeds; a returned failure sets radio recovery hold
and prints WIFI_MODE_FAILED. These diagnostic fields do not change PCM/GATT or
model contracts. Reset during WiFi.mode remains unresolved after the build fix.

BLE manual bench control v2 (2026-11-14) waits for serial R before one radio
initialization per boot. After reset it returns to waiting. S reports READY,
CONNECTED, ATTEMPTED and UPTIME_MS with STANDALONE_BLE_RADIO_TEST_V2_MANUAL.
The PowerShell monitor logs R requests, device markers and host elapsed time.
Supply and EN voltage remain external measurements. Public GATT bench UUIDs
and synthetic payloads stay compatible with the first bench version.

BLE bench test (2026-11-14): `Firmware/diagnostics/ble_radio_minimal` implements
only public synthetic connectivity data on ESP32-S3. Advertised name is
`AurisCore-BLE-Test`; service UUID is dce83010-8196-4ef1-ae1b-13b634324624,
read/notify UUID is dce83011-8196-4ef1-ae1b-13b634324624, write UUID is
dce83012-8196-4ef1-ae1b-13b634324624. ASCII PING requests PONG;
BEAT counters are synthetic transport-test data. Firmware uses the default CPU
clock and PHY table, with brownout disabled per user request. A -12 dBm request
occurs after BLE init succeeds. Current hardware resets at BLE_INIT_BEGIN before
advertising. This adds a bench interface only; audio transport and a phone
receiver remain unimplemented. See the sketch README for complete UUIDs.

User-selected bench firmware option (2026-11-14): `build_wifi_firmware.ps1
-DisableBrownout` builds a separate image calling ESP-IDF's brownout-disable
function at setup. The serial boot marker is `BROWNOUT_DETECTOR_DISABLED`.
The selection persists through reboot by reapplication at setup. Flash a plain
build to restore the detector. Wi-Fi/PCM contracts and continuity checks remain
in force. Physical voltage and audio acceptance must be measured for this build.

LED status preparation (2026-11-14): capable Wi-Fi publishers advertise optional
`indicatorProtocol: 1` in device_hello. The authenticated controlling browser sends
`{type:"indicator",mode:"heart"|"lung"|"abdomen",phase:"idle"|"recording"|"processing"|"done"|"error"}`.
Gateway validates and forwards these advisory messages only to capable devices.
They never start/stop acquisition. Legacy publishers receive no such messages.
Firmware computes red/green/blue boot test (300 ms each), slow white disconnected
blink (300 ms on / 2 s), dim white before mode selection, mode color with two
confirmation blinks, breathing during recording, and three blinks on successful
completion. Processing/error retain mode color; neither triggers completion.
Wi-Fi capture 0.3.4 drives a 4-pin common-anode RGB LED at 5 kHz. The common
anode goes to 3.3 V and the R/G/B cathodes each go through a 150–220 Ω resistor
to GPIO4/5/6 respectively. Heart is red, Lung is blue, and Abdomen is purple
(red plus blue). The green channel remains available for boot and white status.
Do not share these GPIOs with the AD8232 while running this build. The separate
USB ECG sketch still documents its own wiring and is unchanged.

USB diagnostics connector selection: the Wi-Fi build script accepts `-NativeUsb`
to enable hardware CDC on boot in a separate build directory. USB 115200 then
carries STATUS/RETRY/provisioning and diagnostics over native USB instead of the
default CH343 UART. Network control/audio contracts are identical. The monitor
accepts `-NativeUsb` to assert DTR for this connector.

Wi-Fi firmware v0.2 update (2026-11-14): local USB provisioning accepts optional
`kind=wifi|hotspot` and `primary=true|false`; existing ssid/password/host/token
fields remain compatible. Profile writes upsert by SSID, retain other entries,
support four entries and reject a fifth without eviction. Each profile stores
its own reachable gateway host. Unsuccessful association rotates profiles after
15 seconds; a working association is retained. Loss stops audio, clears the WS
session and retries with a new stream identity. Browser/PCM/model schemas remain
unchanged. A five-second pre-radio configuration window and brownout recovery
hold permit diagnostics; a held/off radio is never reported as audio readiness.

Wi-Fi capture addition (2026-11-14): `Firmware/wifi-capture` uses the existing
gateway v2 header/control messages unchanged. Hardware identity becomes
`ESP32S3-INMP441-WIFI`. It preserves the original GPIO16/18/17 stereo I2S capture
and moves organ-slot FIR/16-to-8kHz conversion onto the board. Its USB 115200
interface carries provisioning/diagnostics only, never audio. Network credentials
are arbitrary user-selected 2.4 GHz Wi-Fi/hotspot settings stored in NVS. The new
setup CLI sends secrets only after a `STATUS` response identifies this firmware.
Current endpoint is local WS port 8082; WSS cloud acceptance and native BLE remain
separate work. ECG synchronization remains available only in the original USB-v4.

scripts/serial_to_gateway.py accepts physical serial v4 at 921600 baud. It verifies
CRC, sequence and short-write flags, selects the left organ channel and uses a
stateful 127-tap FIR (3600 Hz cutoff) before 16-to-8 kHz decimation. FIR delay is
63 input samples (3.9375 ms); sample numbering begins with this filtered stream.
It emits original gateway v2 frames, 400 samples each, hardware source.
No noise cancellation or EKG processing is claimed. Only EKG sample counts are
logged. Raw probe data stays local. Corrupt frames and sequence gaps stop the
source instead of inserting zero-filled audio. A browser disconnect releases
the publisher; restart the serial adapter to reconnect.

Research artifact extension (2026-11-10): Lung config may explicitly select
`lung_feature_policy.schema_version=lung-fixed-logmel-v1`, bound by the existing
full config hash; absence preserves legacy features. v7 research training emits
`lung-trajectory-v1` protocol/epoch metrics, weights and fixed probe predictions.
These artifacts do not change HTTP/organ result schemas or activate models.
Existing models/normalization must never be combined with the new feature cache.
See AI-Pipeline/docs/lung_fixed_reference_trajectory.md.

Research-only source addition (2026-11-10): L012 fits on an audited HF+SPRSound
development cache. SPR event taxonomy provides acoustic supervision, not I/E
phase labels; missing phases and uncovered intervals are masked. No research
checkpoint is auto-registered, and HTTP/result schemas remain unchanged. See
AI-Pipeline/docs/lung_sprsound_training.md for mapping and limitations.

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
With the introduction of the validated CRNN SED models (EXP-A104/EXP-A105), the
previously null event branches are now populated via `abdomen_sed_analytics`:
- `bowel_events`: list of timestamped discrete acoustic events (`start_s`, `end_s`, `duration_ms`, `confidence`, `pattern`);
- `bowel_rate_per_minute`: numeric rate, clinical motility category (`hypoactive|normoactive|hyperactive`), and assistive screening interpretation;
- `bowel_rate_variability`: inter-event interval (IEI) statistics (`mean_interval_s`, `std_interval_s`, `cv_interval`, `rhythm_regularity`);
- `pattern_categories`: breakdown of Single Burst (SB), Multiple Burst (MB), and Prolonged / CRS sounds.
Legacy window-activity packages retain null event fields to preserve backward compatibility.
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

Lung package evidence may freeze `localization_version` as
`lung-frame-events-v2`; inference uses the versioned onset/offset decoder while
preserving the existing interval schema. Missing fields retain legacy v1 rules;
unknown decoder versions are rejected. Research-only WAV exports use the separate
`lung-localization-research-v1` JSON schema and cannot activate production models.
See AI-Pipeline/docs/lung_localization.md for command/output contracts.

## Continuous PCM analysis

`POST /api/analysis/live?mode=heart|lung|abdomen` accepts raw mono PCM16LE at
8 kHz (`application/octet-stream`) and an `X-AurisCore-Start-Sample` header.
Transport windows are 10 s Heart, 30 s Lung and 5 s Abdomen. The response
contains `startSample`, exclusive `endSample` and the existing
`organ-analysis-v1` as `result`. Bounds are relative to the current
contiguous buffer; event times inside the result are relative to that window.
HTTP 429 means skip this window because the shared worker is busy.

LED status preparation (2026-11-14): capable Wi-Fi publishers advertise optional
`indicatorProtocol: 1` in device_hello. The authenticated controlling browser sends
`{type:"indicator",mode:"heart"|"lung"|"abdomen",phase:"idle"|"recording"|"processing"|"done"|"error"}`.
Gateway validates and forwards these advisory messages only to capable devices.
They never start/stop acquisition. Legacy publishers receive no such messages.
Firmware computes red/green/blue boot test (300 ms each), slow white disconnected
blink (300 ms on / 2 s), dim white before mode selection, mode color with two
confirmation blinks, breathing during recording, and three blinks on successful
completion. Processing/error retain mode color; neither triggers completion.
An unset LED GPIO disables physical output. Wiring/type is pending hardware team
integration; `AURISCORE_RGB_DATA_PIN` supports a confirmed addressable RGB LED only.
The built-in diagnostic LED is not assumed to be the external RGB LED.

Rhythm display update (2026-11-14): DSP 0.1.1 adds nullable `interval_cv` to
heart-analysis-v1 rhythm output, calculated as population SD / mean of the same
retained S1-S1 intervals, with at least two intervals and a positive mean.
SD remains in milliseconds; CV is dimensionless. The parser accepts older
responses without CV. The UI displays BPM, SD and CV and marks rhythm regularity
as awaiting evaluation. The legacy `irregular` field and 5 ms rule remain for
compatibility but do not drive the UI finding. No CV decision threshold or
regularity percentage is introduced. Validation of timing and rhythm remains
an implementation gap.

Mobile LAN controls (2026-11-14): the main workspace defaults to an unconnected
physical ESP32 source; there is no simulator selector or automatic mock socket.
The gateway form derives `ws(s)://<page-host>:8082/browser`, accepts an explicit
override, and retains pairing authentication. Command IDs are non-secret
correlation counters and do not require secure-context `crypto.randomUUID`.
Disconnect releases the single browser controller; applying identical settings
can reconnect. The LAN launcher supplies its selected IP through
`AURISCORE_ALLOWED_DEV_ORIGINS` for Next development-resource access; no wildcard
origin is added. AudioWorklet listening still requires HTTPS or localhost.
No audio/result schema or analysis/model/threshold behavior changes.

Live diagnostic addition: `heartbeat` with an optional correlation ID has a
gateway-local `heartbeat_ack` response (protocol v2, backward-compatible).
The UI shows the latest browser–gateway RTT and latest live analysis request
duration separately. A client-side rolling one-second PCM meter shows RMS dBFS
and exact signed-PCM16 rail saturation; it does not estimate SNR, raw microphone
clipping, physiological validity, or sensor-to-screen latency. Audio/analysis
readings clear on audio loss; RTT clears on socket close or its own probe timeout
(gateway responsiveness can still be measured without device audio).
Backend quality gates and all model thresholds remain unchanged.


## Timed evidence for organ results — 2026-11-14

heart-analysis-v1 adds optional murmur.temporal_evidence for a configured verified
Heart CNN backend. Version heart-window-evidence-v1 contains kind
exploratory_window_scores, threshold_scope recording_reference_only, duration_s,
discarded_tail_s and windows of start_s/end_s/score. Timestamps follow frozen
preprocessing and complete segmentation windows. Recording aggregation and its
threshold are preserved. The recording threshold is a descriptive comparison on
individual windows and has no independently validated segment operating point.
Older responses without the optional field remain accepted.

The common UI renders positive-reference Heart windows, existing Abdomen activity
windows and Lung model-frame intervals as absolute seconds from recording start.
Overlapping windows remain separate. Unanalyzed tails receive no score. An absent
or unconfigured model produces no inferred intervals. This addition does not
register historical H022 fold encoders, Temporal MIL, or A103 as deployment models.

## Uji lokal model dan jembatan USB — 2026-11-14

User explicitly authorizes engineering testing on this laptop. The optional
AURISCORE_ENGINEERING_MODELS points to an ignored, local hash manifest.
AnalysisService accepts an engineering_test_only registration only when
allow_engineering=True is explicitly selected. Default candidate and final
deployment checks remain in effect. Results carry usage_scope=engineering_test_only
and the UI displays that scope. No training, final promotion or held-out
evaluation is performed.

Current local test configuration uses H022 fold 1 (frozen encoder, normalization
and logistic head), with historical pooled-OOF threshold as descriptive reference,
and Abdomen A005 window classification. Fold 1 was chosen as the explicit first
diagnostic instance, without selection on these device recordings. This is not an
ensemble or a final refit. H022 whole-record scoring preserves mean embedding then
logistic head. Per-window head scores are exploratory. Lung remains unavailable
until the weights/normalization/config/thresholds are supplied.

Live result timelines offset their local model windows using the received stream
startSample / 8000. WAV upload starts at zero. Stream samples omit no synthetic
padding, and model discarded tails remain explicitly unanalyzed.

Completed and saved sessions display a waveform and spectrogram computed in the
browser from the same PCM16 mono WAV used by playback. Result labels use the
recording-relative timestamps, support overlapping intervals, and can seek the
player. The browser uses candidate timestamps already returned by each backend.
Heart DSP events remain visible when Murmur results or window evidence are
unavailable. No result schema or recording format changes.

## Lung release and live-only main screen — 2026-11-14

The local hardware launcher and private hosting image now enable
`AURISCORE_LUNG_ENGINEERING_L030=1`. The retained worker loads tracked L030
on its first Lung request. An explicit verified Lung deployment package
has precedence. Heart and Abdomen keep their existing configuration.
L030 thresholds apply to complete 62-frame clips for wheeze, rhonchi and
crackle. The reported intervals may overlap and represent positive clips.
Respiratory fields are null because L030 has no phase outputs. The result
uses the existing `lung-analysis-v1` wire shape.

On Windows, the launcher respects `AURISCORE_PYTHON`, then checks the
existing repository runtime and `%LOCALAPPDATA%/AurisCore/py/Scripts/python.exe`.
The latter can be created with Python 3.12 and populated from
`hosting/requirements.txt` to keep TensorFlow installation paths short.

The explicitly authorized local test manifest now also selects
EXP-L006-temporal-cnn-context/fold-0 from GitHub release lung-research-models.
Archive SHA-256 faf89db277d6814ed7e4cc47581b981387f506086f0ffaad80eba0f587ee66fc
and model SHA-256 fcb29b63ae77004132ad5e4350636a80e8bb3616523773c6e21b169353c228c2
match the release index on origin/master b45db72. Source configuration,
normalization and development thresholds come from that same archive.
L006 was selected for six-class integration coverage, without a new performance
selection or a claim that it is the best Lung model. Research scope and false
deployment eligibility are preserved. No training or new held-out scoring occurs.

LungTestBackend caches its model and uses the existing research feature/frame
decoder and respiratory measurement rules. It returns lung-analysis-v1, with
partial status when respiratory cycles are insufficient. Three local modes
are now configured: H022 fold 1, Lung L006 fold 0, Abdomen A005.

The main screen removes the WAV upload section across all organ selections and
its upload-busy state. Recording from the device, playback/download of device
captures, and live analysis remain available. WAV endpoints and file-simulation
tooling remain supported for engineering tests. There is no result-schema change
from removing the UI section.
