# ARCHITECTURE.md

## 1. Architecture authority

Product requirements come from `PRD.md`. This document defines **how the current architecture satisfies those requirements**.

If implementation is incomplete relative to the PRD, record an implementation gap. Do not silently redefine the product around current code.

Accepted cross-module architecture decisions belong in `DECISIONS.md`.

---

## 2. System overview

AurisCore uses a distributed cyber-physical architecture.

```text
+----------------------+
| Physical Stethoscope |
| ESP32-S3             |
+----------+-----------+
           |
           | BLE audio / metadata
           v
+----------------------+
| Mobile Application   |
| Flutter / Dart       |
+----------+-----------+
           |
           +----------------------------+
           |                            |
           v                            v
+---------------------------+   +----------------------+
| Local Analysis Layer      |   | Backend / Storage    |
| quality + DSP + local AI  |   | optional sync        |
+-------------+-------------+   +----------------------+
              |
              v
+---------------------------+
| CDS / Visualization /     |
| Session / Report UI       |
+---------------------------+
```

Optional real-time remote path:

```text
Mobile
  |
  | WebRTC P2P
  v
Remote clinician/browser client
```

Core examination analysis must remain offline-capable.

---

## 3. Architecture principles

### 3.1 Offline-first analysis

Core organ analysis must not require backend connectivity.

### 3.2 Clear separation of concerns

Keep these concerns separable:

- acquisition;
- signal-quality validation;
- preprocessing;
- DSP/event analysis;
- AI inference;
- result aggregation;
- visualization;
- storage;
- remote streaming.

### 3.3 Replaceable audio sources

The analysis layer should accept audio independent of whether it originated from:

- BLE;
- WAV/file simulator;
- mobile recording/session cache.

In the Windows development checkout, WAV files and captured mock/WebSocket
PCM both reach the same `HeartAnalysisService` through a PCM-to-WAV boundary.
`BleAudioSource` is an injected software boundary only; physical BLE discovery
and packet decoding await confirmed firmware UUIDs and byte layout.

### 3.4 Versioned analysis

Version independently where practical:

- result schema;
- preprocessing;
- DSP algorithm configuration;
- AI model;
- threshold/calibration;
- mobile integration contract.

### 3.5 Research/production separation

Experiment directories and research scripts are not production APIs.

The mobile path consumes a frozen/versioned analysis package or service boundary, not arbitrary files from the latest experiment directory.

---

## 4. Heart architecture — required three-branch design

The Heart product architecture is:

```text
                         HEART AUDIO
                              |
                    SignalQualityGate
                              |
                     HeartPreprocessor
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
      HeartRhythmDSP   CardiacEventDSP    MurmurInference
              |               |               |
          BPM / beat       S1 / S2        probability
          intervals        systole /       threshold
              |            diastole       Present/Absent
              v               |
      rhythm category      S3 / S4
              |               |
              +---------------+---------------+
                              |
                              v
                    HeartResultAggregator
                              |
                              v
                    Unified Heart Result
```

**The Murmur CNN is one branch, not the entire Heart system.**

### 4.1 Branch A — Heart Rhythm DSP

Responsibilities:

- consume Heart audio and/or S1 event timing;
- compute beat intervals;
- compute BPM;
- produce report-aligned prototype rhythm category;
- expose algorithm/config version.

### 4.2 Branch B — Cardiac Event DSP

Responsibilities:

- identify S1/S2 events;
- derive systolic/diastolic regions;
- identify S3/S4 candidates using configured report-derived logic;
- emit event timestamps for visualization;
- expose algorithm/config version.

### 4.3 Branch C — Murmur AI

Responsibilities:

- consume the configured murmur preprocessing representation;
- produce murmur probability/score;
- apply a versioned threshold;
- return `present|absent` screening output;
- expose model/preprocessing/threshold versions.

Current trained target remains Murmur Absent vs Present. It is not a disease classifier.

### 4.4 Heart result aggregation

The aggregator combines the three branches into one versioned Heart result without hiding branch-level provenance.

The UI should not need to know TensorFlow/Keras internals or DSP implementation details.

For the current Windows WebApp demo, the browser sends a selected or
mock/WebSocket-captured PCM WAV to a
Next.js route handler. That handler invokes the existing CPU-only Python Heart
DSP CLI with WAV bytes on stdin and returns `heart-analysis-v1`. The browser
validates the versioned JSON and renders it through a `HeartAnalysisService`
interface. This development bridge does not replace the eventual offline
mobile analysis service or its device audio adapter.

The current Python prototype implements the CPU-only quality gate, Rhythm DSP,
Cardiac Event DSP, and result assembly in `AI-Pipeline/src/auriscore/heart_dsp.py`
and `heart_result.py`. The DSP uses a separate 20–150 Hz path and does not
change Murmur AI preprocessing. `analyze_heart(audio, sample_rate, murmur=...)`
accepts an optional frozen Murmur result through a small adapter; an unavailable
Murmur branch remains explicit. This is a research/integration boundary, not yet
the mobile `HeartAnalysisService`. Synthetic engineering tests do not establish
event-detection accuracy on labeled recordings.

---

## 5. Organ-level architecture

Do not force Heart, Lung, and Abdomen into one universal classifier merely for convenience.

```text
Auscultation mode router
        |
        +--> HeartAnalysisService
        |       +--> Rhythm DSP
        |       +--> Cardiac Event DSP
        |       +--> Murmur AI
        |
        +--> LungAnalysisService
        |
        +--> AbdomenAnalysisService
```

Lung and Abdomen may use different combinations of DSP and AI depending on the validated design.

---

## 6. Mobile architecture

Suggested feature structure:

```text
lib/
  core/
    ble/
    audio/
    storage/
    networking/
    models/
  features/
    device/
    dashboard/
    auscultation/
    analysis/
    patients/
    reports/
    telehealth/
```

Recommended service boundaries:

```text
AudioInputService
SignalQualityService
HeartAnalysisService
LungAnalysisService
AbdomenAnalysisService
SessionRepository
DeviceRepository
TelehealthService
```

The UI consumes typed, versioned results.

---

## 7. Research experiment architecture

Each completed Heart AI experiment writes to a unique immutable directory:

```text
AI-Pipeline/results/EXP-HNNN-name/
```

Machine-readable JSON/CSV and saved models are sources of truth. PNG figures are derived artifacts.

Long-running managed training may use request/status/history/checkpoint artifacts. Research queues must remain independent from the mobile inference path.

External validation and sealed test access follow `AI_PIPELINE.md` and `AGENTS.md`.

---

## 8. Backend architecture

Recommended logical responsibilities:

```text
API
Authentication integration
Session Service
Patient Metadata Service
Recording Metadata Service
Analysis Result Service
Report Service
Telehealth Signaling
```

Storage concept:

```text
structured metadata -> selected database
large audio object   -> file/object storage when required
live media           -> WebRTC path, not database persistence
```

Backend availability must not be required for local Heart/Lung/Abdomen analysis.

---

## 9. Security and privacy boundaries

Sensitive data must not be:

- unnecessarily logged in plain text;
- committed to Git;
- embedded in fixtures using real identities;
- sent to cloud services without an explicit approved design.

Use anonymized/generated development data.

Project-report references to encryption, standards, or compliance are design targets unless implementation and verification establish otherwise.

---

## 10. Source-of-truth order

When documents/code disagree:

1. `PRD.md` for required product behavior;
2. accepted `DECISIONS.md` entries for architecture choices;
3. this document for component structure;
4. `INTEGRATION.md` for interface details;
5. subsystem documentation;
6. current implementation state.

If implementation intentionally deviates from product requirements, resolve it explicitly through PRD/ADR updates rather than silently accepting the drift.
