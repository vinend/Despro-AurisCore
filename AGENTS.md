# AGENTS.md

## Purpose

This file defines how AI coding agents and human contributors should work inside the AurisCore software repository.

The goal is to prevent agents from:
- inventing architecture not agreed by the team,
- silently changing medical assumptions,
- mixing experimental AI code with production integration code,
- optimizing accuracy while ignoring recall / F1 / class imbalance,
- breaking interfaces between ESP32, mobile, AI, and backend.

---

## 1. Project context

AurisCore is a digital stethoscope system with three primary auscultation domains:

1. Heart
2. Lung
3. Abdomen

The current development priority is **Heart first**.

Current Heart status: Rhythm DSP, Cardiac Event DSP, and `heart-analysis-v1` are implemented as engineering prototypes; representative labeled-recording validation remains open. H021 is the strongest TRAIN-only Murmur development result, without a final deployment model. H022 is protocol-locked and preflight-ready but has not started training. The three-branch Heart product remains incomplete.

The application is an **assistive screening system**, not a final diagnostic system.

Never generate UI copy or API behavior that presents model output as definitive medical diagnosis.

---

## 2. Software architecture

Preferred high-level flow:

```text
ESP32-S3
   |
   | BLE audio / metadata stream
   v
Mobile Application
   |
   +--> DSP / preprocessing
   |
   +--> Local AI inference
   |
   +--> Clinical Decision Support UI
   |
   +--> Session storage / backend sync
   |
   +--> WebRTC tele-auscultation
```

Primary software components:

```text
/mobile
/ai
/backend
/shared
/docs
/tests
```

Recommended responsibility boundaries:

- `mobile/`
  - Flutter / Dart
  - BLE connection
  - live waveform
  - recording
  - patient/session UI
  - AI result presentation
  - report flow
  - tele-auscultation client

- `ai/`
  - dataset preparation
  - preprocessing
  - augmentation
  - log-mel / MFCC feature pipeline
  - CNN training
  - evaluation
  - model export / quantization
  - inference wrapper

- `backend/`
  - API
  - session metadata
  - persistent storage
  - authentication integration
  - report metadata
  - WebRTC signaling if required

- `shared/`
  - schemas
  - constants
  - packet definitions
  - model metadata format

---

## 3. Agent behavior rules

### Before editing code

An agent must first identify:
1. which subsystem is being changed,
2. its upstream input,
3. its downstream consumer,
4. whether the change modifies an interface or data schema.

If an interface changes, update:
- `ARCHITECTURE.md`
- `INTEGRATION.md`
- affected tests

### Do not invent missing requirements

If a requirement is not defined:
- mark it as `TBD`,
- state the assumption,
- avoid hard-coding it into multiple modules.

### Prefer small changes

Do not rewrite the entire codebase to solve a local problem.

Prefer:
- isolated modules,
- explicit interfaces,
- testable functions,
- incremental refactors.

### Preserve reproducibility

For AI work, always track:
- dataset version,
- train / validation / test split,
- random seed,
- preprocessing parameters,
- augmentation configuration,
- model version,
- evaluation metrics.

### Medical-safety rule

Model output must use language such as:
- `Normal / Abnormal`
- `Possible abnormal acoustic pattern`
- `Assistive screening result`

Avoid:
- definitive disease diagnosis,
- treatment recommendation,
- unsupported clinical claims.

### Never optimize on the test set

The test set is for final evaluation only.

Threshold tuning, hyperparameter tuning, feature tuning, and augmentation decisions must use training / validation data.

### Long-running CNN training

**LONG-RUNNING TRAINING MUST NOT BE MONITORED BY REPEATED AGENT POLLING.**

The coding agent should prepare a named experiment, launch the standalone training queue as an independent process when training is authorized, report the PID, log paths and result paths, then stop. Do not repeatedly call `Get-Content` or equivalent to watch epoch or batch progress. A future session should use `AI-Pipeline/scripts/training_status.py` and `AI-Pipeline/scripts/summarize_experiments.py` to inspect disk artifacts. Do not start a new training run when the user has asked only for workflow changes.

---

## 4. Coding conventions

### Python

Use:
- type hints for public functions,
- docstrings for non-trivial modules,
- deterministic seeds where practical,
- configuration files instead of scattered constants.

Suggested tools:
- NumPy
- SciPy
- librosa
- scikit-learn
- TensorFlow / Keras

### Flutter

Use:
- feature-based structure where possible,
- state separated from widgets,
- typed models for BLE packets and AI results,
- no business logic inside large UI widgets.

### Backend

Use:
- explicit request / response schemas,
- versioned endpoints for breaking changes,
- environment variables for secrets,
- structured logging.

Never commit:
- API keys,
- passwords,
- patient-identifying test data,
- private certificates.

---

## 5. Required AI evaluation

Do not report only accuracy.

At minimum report:
- confusion matrix,
- precision,
- recall / sensitivity,
- F1-score,
- ROC-AUC when applicable,
- PR-AUC when class imbalance is relevant.

Also report:
- class distribution,
- validation threshold,
- dataset split method.

Primary success metric for the proposal:
- target F1-score > 90%

This is a project target, not an assumption that the target has already been achieved.

---

## 6. Definition of done

A software task is done only when:

- code runs,
- tests for the changed behavior pass,
- interface changes are documented,
- no secrets are committed,
- relevant documentation is updated,
- output behavior matches the assistive-screening requirement.

For AI model changes, also require:
- reproducible training config,
- before/after metric comparison,
- saved evaluation artifacts,
- model version increment if exported.

---

## 7. Priority order

Unless a sprint explicitly overrides it:

1. Continue disciplined Murmur research and define a separately evaluated deployment candidate.
2. Validate and stabilize the implemented Heart DSP prototypes.
3. Complete the unified Heart result/UI path, including offline mobile integration.
4. Confirm the firmware contract and integrate physical BLE audio.
5. Complete session persistence and report flow.
6. Implement tele-auscultation.
7. Expand to Lung.
8. Expand to Abdomen.
