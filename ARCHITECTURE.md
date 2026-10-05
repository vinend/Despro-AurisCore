# ARCHITECTURE.md

## 1. System overview

AurisCore uses a distributed cyber-physical architecture.

```text
+----------------------+
| Physical Stethoscope |
| ESP32-S3             |
+----------+-----------+
           |
           | BLE
           v
+----------------------+
| Mobile Application   |
| Flutter / Dart       |
+----------+-----------+
           |
           +---------------------+
           |                     |
           v                     v
+------------------+    +----------------------+
| DSP / AI Layer   |    | Backend / Storage    |
| Offline on phone |    | Python + DB          |
+------------------+    +----------------------+
           |
           v
+----------------------+
| CDS / Report / UI    |
+----------------------+
```

Optional real-time remote path:

```text
Mobile A
   |
   | WebRTC P2P
   v
Remote Doctor Client
```

---

## 2. Architecture principles

### Offline-first inference
AI inference should not require the backend.

### Clear separation
The following are different concerns:
- acquisition,
- preprocessing,
- inference,
- visualization,
- storage,
- remote streaming.

### Replaceable inputs
The AI layer should accept audio independent of whether it comes from:
- BLE,
- WAV file,
- recorded mobile session.

### Versioned AI
Every exported model must have:
- model version,
- preprocessing version,
- threshold version.

### Heart experiment reporting

The research AI pipeline writes each completed Heart training run to a unique
`AI-Pipeline/results/EXP-HNNN-name/` directory. Numerical JSON/CSV and saved
models are the source of truth; report PNGs are derived artifacts. Validation
figures use linked-participant decisions and validation-selected thresholds.
The test split remains sealed during training and appears only in the one-time
locked-holdout report. Experiment reporting does not change mobile inference.

The standalone Heart CNN queue reads a fixed experiment manifest, runs one
TensorFlow process at a time, and stores epoch recovery state in that same
experiment directory. Its process is independent of an agent session.
`status.json` and `history.csv` are small inspection surfaces; the Keras backup
and best checkpoint are the actual recovery/model sources. A queue process
waits for older trainers before starting new work. The mobile inference path
does not depend on this research queue.

---

## 3. Mobile architecture

Suggested feature modules:

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

The UI must not know the internal details of TensorFlow preprocessing.

Use a service boundary such as:

```text
AuscultationService
AIInferenceService
SessionRepository
DeviceRepository
```

---

## 4. AI architecture

Current Heart flow:

```text
Audio waveform
-> validation
-> resample
-> normalize
-> segment
-> log-mel spectrogram
-> CNN
-> probability
-> threshold
-> Normal / Abnormal
```

Possible later extension:

```text
Heart
  -> heart-specific model

Lung
  -> lung-specific model

Abdomen
  -> abdomen-specific model
```

Do not initially force all organs into a single classifier unless experiments prove that this is better.

---

## 5. Backend architecture

Recommended logical modules:

```text
API
Authentication
Session Service
Patient Metadata Service
Recording Metadata Service
Model Result Service
Report Service
Telehealth Signaling
```

Storage concept:

```text
structured metadata -> MongoDB / selected database
large audio object   -> object/file storage if needed
real-time telemetry  -> only if required by final implementation
```

The proposal mentions Firebase for real-time telemetry and MongoDB for persistent records. The implementation should keep these as separable adapters so the team can change providers without rewriting domain logic.

---

## 6. Security boundaries

Sensitive data must not be:
- logged in plain text unnecessarily,
- committed to Git,
- embedded inside test fixtures using real identities.

Use generated / anonymized data in development.

Transport security should be applied for networked components.

---

## 7. Source of truth

When architecture and implementation differ:

1. working implementation,
2. current architecture decision,
3. this document,
4. older report wording.

If code intentionally deviates from the proposal, document the reason in `DECISIONS.md`.
