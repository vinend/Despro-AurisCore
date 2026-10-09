# IMPLEMENTATION.md

## 1. Objective

Implement a working AurisCore prototype that can:

1. receive stethoscope audio;
2. validate/visualize/record it;
3. run the complete report-aligned Heart analysis pipeline;
4. display assistive screening output and annotations;
5. preserve session information;
6. support hardware integration;
7. support later backend/report/tele-auscultation integration;
8. expand to Lung and Abdomen after the Heart path is stable.

The product definition comes from `PRD.md`.

Important: **Heart is not complete when the Murmur CNN is complete.**

---

## 2. Phase A — Maintain a reproducible Murmur AI baseline

### Goal

Preserve the current research baseline and a credible path for model improvement.

### Current state

- H014 is the frozen historical external-validation benchmark.
- H015–H021 are completed train-only OOF research studies. H021 is strongest: 117 FP, 11 FN, sensitivity 0.90, F1 0.6074 among 568 participants; it still misses the full engineering gate.
- H022 has a locked protocol and passed preflight checks but training has not started. External validation and sealed test remain closed.
- H021 has only five outer-fold evaluation pipelines, with no final all-TRAIN deployment model or predeclared ensemble. Murmur deployment inference remains unavailable.

### Required work

- preserve immutable experiment artifacts;
- maintain participant-level leakage protection;
- use predeclared threshold-selection logic;
- maintain external-validation / sealed-holdout boundaries;
- freeze a deployable Murmur candidate when criteria are satisfied.

### Deliverables

```text
AI-Pipeline/results/EXP-HNNN-name/
model metadata
export candidate
reproducible inference wrapper
```

---

## 3. Phase B — Murmur precision / false-positive improvement

### Goal

Reduce false positives without dropping below the declared screening sensitivity requirement.

### Method discipline

- audit failure mode before adding complexity;
- use one evidence-backed major change per experiment where practical;
- evaluate with train-only CV/OOF until a predefined external-validation gate is met;
- do not tune repeatedly on external validation;
- do not optimize the sealed test set.

### Exit condition

A Murmur deployment candidate is selected/frozen with documented reasoning and reproducible artifacts.

The project may proceed to DSP implementation even if the aspirational report F1 target is not yet reached, provided the limitation is documented.

---

## 4. Phase C — Cardiac Event DSP

Implementation status: the CPU prototype emits S1/S2 and experimental S3/S4
candidate timestamps plus systolic/diastolic intervals through
`heart-analysis-v1`. Synthetic engineering tests pass; representative labeled
recording validation and complete visualization annotations remain open.

### Goal

Implement the second Heart branch.

### Required outputs

- S1 event timestamps;
- S2 event timestamps;
- systolic intervals;
- diastolic intervals;
- S3 candidate timestamps;
- S4 candidate timestamps.

### Implementation direction

- keep report-derived frequency/timing thresholds configurable;
- separate event detection from UI rendering;
- serialize events into typed/versioned result structures;
- build deterministic tests with synthetic/known signals where practical;
- add dataset-based validation when suitable labels are available.

### Exit condition

Known Heart recordings can produce stable, inspectable event annotations without requiring the Murmur CNN.

---

## 5. Phase D — Rhythm DSP

Implementation status: the CPU prototype calculates beat intervals, median
BPM, rate categories, and an irregularity indicator, with explicit invalid or
insufficient-data behavior. Labeled-recording validation remains open.

### Goal

Implement the first Heart branch.

### Required outputs

- beat intervals;
- BPM;
- prototype rhythm category: Normal / Tachycardia / Bradycardia / irregular-rhythm indicator.

### Implementation direction

- derive BPM from validated beat/S1 timing;
- keep report thresholds configurable;
- treat rhythm output as screening/assistive information;
- do not present the threshold rule as a definitive medical diagnosis.

### Exit condition

Known Heart recordings can produce reproducible BPM/rhythm results and appropriate invalid-input behavior.

---

## 6. Phase E — Unified Heart Analysis Service

Current development progress: the Python aggregator produces
`heart-analysis-v1`, and the WebApp WAV and mock/WebSocket PCM paths consume it
through a typed `HeartAnalysisService` and a same-origin Next.js/Python bridge. The
Murmur branch can be explicitly unavailable. This does not yet include a
deployment-ready Murmur model or offline mobile execution.
H021 now has a read-only development freeze and a fail-closed participant
Murmur service boundary. Its five outer-fold models are evaluation artifacts,
so the adapter reports unavailable; no deployment-ready H021 model or offline
mobile Murmur inference is present.

### Goal

Combine all three branches:

```text
Heart audio
 -> quality/preprocessing
 -> Rhythm DSP
 -> Cardiac Event DSP
 -> Murmur AI
 -> HeartResultAggregator
 -> versioned Heart result
```

### Required work

- implement result types/schema;
- preserve branch provenance/versions;
- represent unavailable branch outputs explicitly during transition;
- add integration tests;
- define failure behavior.

### Exit condition

One call can accept Heart audio and produce the agreed unified result without UI-specific logic.

---

## 7. Phase F — Heart visualization and mobile integration

Current development progress: a browser user can select a local mono WAV or
capture ten seconds of the existing WebSocket/mock PCM stream. Both flow
through the same Heart service and display quality, BPM/rate, cardiac-event
candidates/intervals, and Murmur availability. The older recording card still
shows a separate simulated classifier. Uploaded-file waveform markers,
physical BLE input, session save, and native mobile integration remain open.

### Minimum functional flow

```text
Connect/select input
-> choose Heart mode
-> receive/load audio
-> show live/static waveform
-> record/playback
-> run HeartAnalysisService
-> display BPM/rhythm
-> display S1/S2 and interval annotations
-> display S3/S4 candidates
-> display Murmur probability/result
-> save session
```

### UI requirements

Support:

- waveform/PCG;
- spectrogram/mel-spectrogram where implemented;
- event markers;
- screening-safe labels;
- invalid/low-quality recording state;
- report/share path.

### Exit condition

The full Heart demo works with a file simulator before hardware is mandatory.

---

## 8. Phase G — BLE / physical hardware integration

Implement BLE through a hardware abstraction layer.

The WebApp now has a transport-independent PCM capture/WAV conversion boundary
and an injected `BleAudioSource` interface. No physical BLE transport or
decoder has been wired because firmware UUIDs, packet layout, and commands
are not yet confirmed. See `HARDWARE_AUDIO_CONTRACT.md`.

Maintain at least two audio adapters during integration:

```text
FILE_SIMULATOR
REAL_BLE
```

BLE responsibilities:

- connect/disconnect;
- service discovery;
- buffering;
- sample reconstruction;
- packet-loss/duplicate detection;
- timestamps;
- reconnect behavior.

### Exit condition

Real device audio can replace the simulator without changing the Heart analysis API.

---

## 9. Phase H — Session storage and backend

Backend scope should remain narrower than local analysis.

Responsibilities may include:

- authentication integration;
- patient/session metadata;
- recording metadata/reference;
- analysis-result metadata;
- report metadata;
- optional telehealth signaling.

Offline analysis must continue to work without internet.

---

## 10. Phase I — Report generation

Generate a report that can include:

- examination/session metadata;
- waveform/PCG snapshot;
- Heart quantitative results;
- Murmur probability/result;
- supported event annotations;
- clinician notes;
- algorithm/model/schema versions when appropriate.

Avoid unsupported definitive diagnostic statements.

---

## 11. Phase J — Tele-auscultation

Use WebRTC where practical.

Separate:

- signaling;
- live media;
- persistence.

Measure:

- setup time;
- packet loss;
- jitter;
- end-to-end latency;
- reconnect/failure behavior.

Report target: <100 ms end-to-end where achievable; measure rather than assume.

---

## 12. Phase K — Lung

Implement report-aligned Lung outputs, including respiratory-phase metrics and wheeze/crackle/rhonchi analysis.

Use DSP and/or trainable models based on available labels and validation evidence; do not assume Lung must copy the Heart architecture exactly.

---

## 13. Phase L — Abdomen

Implement report-aligned bowel-event/rate/variability analysis and report-defined pattern categories.

Keep disease-associated indicators framed as screening findings unless explicit validated disease classification is added later.

---

## 14. Implementation discipline

- Prefer incremental changes.
- Keep product requirements separate from current implementation gaps.
- Version breaking schemas.
- Update relevant documentation in the same change.
- Keep research experiments separate from production integration code.
- Do not block all software work waiting for final hardware.
