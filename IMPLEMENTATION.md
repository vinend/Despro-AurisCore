# IMPLEMENTATION.md

## 1. Objective

Implement a working AurisCore software prototype that can:

1. receive stethoscope audio data,
2. visualize and record it,
3. process the signal,
4. run offline Heart AI inference,
5. display assistive screening output,
6. store session information,
7. support later tele-auscultation integration.

The project should be built incrementally. Do not block the whole system while waiting for final hardware.

---

## 2. Phase A — Stabilize the Heart AI baseline

### Goal
Create a reproducible baseline from the current CNN.

### Tasks
- Freeze current dataset snapshot.
- Document class distribution.
- Define patient-level or source-level train / validation / test split where possible.
- Verify no duplicate or near-duplicate audio crosses splits.
- Reproduce the current ~72% result.
- Save:
  - training history,
  - confusion matrix,
  - precision,
  - recall,
  - F1,
  - ROC-AUC,
  - PR-AUC.

### Deliverables
```text
ai/
  configs/
  datasets/
  preprocessing/
  training/
  evaluation/
  models/
```

Output:
```text
baseline_metrics.json
baseline_confusion_matrix.png
baseline_model.keras
```

---

## 3. Phase B — Improve preprocessing

Test improvements independently before combining them.

Candidate experiments:
- amplitude normalization,
- resampling consistency,
- silence trimming,
- band-pass filtering,
- denoising,
- fixed-duration segmentation,
- log-mel parameter tuning,
- class-aware augmentation.

Track each experiment.

Example:

```text
EXP-H001 baseline
EXP-H002 normalization
EXP-H003 log-mel tuning
EXP-H004 augmentation
EXP-H005 class balancing
EXP-H006 CNN tuning
```

Do not mix five changes into one experiment because the team will not know what caused the improvement.

---

## 4. Phase C — CNN optimization

Candidate model-level improvements:

- filter count,
- kernel size,
- pooling strategy,
- dropout,
- batch normalization,
- learning rate,
- scheduler,
- class weighting,
- early stopping,
- input dimensions.

Evaluation priority:

```text
Recall / Sensitivity
F1-score
PR-AUC
ROC-AUC
Accuracy
```

Accuracy is still recorded but must not be the only decision metric.

---

## 5. Phase D — Freeze inference contract

Before mobile integration, define one stable inference function.

Example conceptual contract:

```python
result = predict_heart(audio, sample_rate)
```

Expected output:

```json
{
  "model_version": "heart-cnn-0.1.0",
  "mode": "heart",
  "quality": {
    "valid": true,
    "score": 0.92
  },
  "prediction": {
    "label": "abnormal",
    "probability": 0.84,
    "threshold": 0.62
  },
  "metrics": {
    "heart_rate_bpm": null
  }
}
```

The exact schema may change, but once mobile integration starts, breaking changes must be versioned.

---

## 6. Phase E — Mobile application

Minimum screens:

1. Device connection
2. Main dashboard
3. Patient / session information
4. Live auscultation
5. Recording
6. AI result
7. Session history
8. Report / share

Minimum functional flow:

```text
Connect device
-> choose Heart mode
-> receive audio
-> show waveform
-> record
-> preprocess
-> run model
-> display result
-> save session
```

Do not implement Lung and Abdomen UI logic deeply until the Heart workflow is stable.

---

## 7. Phase F — BLE integration

Implement BLE through a hardware abstraction layer.

During early development, support two input sources:

```text
REAL_BLE
FILE_SIMULATOR
```

This allows mobile and AI development even when hardware is unavailable.

BLE module responsibilities:
- connect / disconnect,
- service discovery,
- packet buffering,
- sample reconstruction,
- packet-loss detection,
- timestamp handling.

---

## 8. Phase G — Backend

Backend scope should remain narrower than the mobile + AI scope.

Responsibilities:
- user/session metadata,
- recording metadata,
- model result metadata,
- persistent storage references,
- authentication integration,
- report metadata,
- WebRTC signaling if needed.

The backend must not become a hidden dependency for local AI inference.

Offline AI should continue to work without internet.

---

## 9. Phase H — Tele-auscultation

Use WebRTC for real-time audio where practical.

Separate:
- signaling path,
- audio media path,
- database/storage path.

Do not send the live audio path through database persistence.

Measure:
- connection setup time,
- packet loss,
- jitter,
- end-to-end latency.

Proposal target:
- audio transmission latency <100 ms.

---

## 10. Integration milestone

The first meaningful integrated demo should prove:

```text
Audio source
-> mobile waveform
-> record
-> Heart CNN inference
-> result card
-> session save
```

Only after this works reliably should the team expand toward:
- full backend,
- report generation,
- tele-auscultation,
- Lung AI,
- Abdomen AI.
