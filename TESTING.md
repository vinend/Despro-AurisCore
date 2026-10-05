# TESTING.md

## 1. Test pyramid

```text
Unit tests
Integration tests
End-to-end tests
AI evaluation tests
Hardware-in-loop tests
```

---

## 2. AI tests

### Reproducibility
Same config + same seed should produce comparable results.

### Preprocessing
Test:
- sample rate conversion,
- tensor shape,
- normalization,
- silence behavior,
- invalid input handling.

### Evaluation
Automatically generate:
- confusion matrix,
- precision,
- recall,
- F1,
- ROC-AUC,
- PR-AUC.

### Quantization
Compare pre- and post-quantization metrics.

---

## 3. Mobile tests

Test:
- device connection state,
- disconnect recovery,
- file simulator input,
- waveform rendering,
- start / stop recording,
- invalid signal handling,
- AI result rendering,
- local session save.

---

## 4. BLE tests

Test:
- sequential packets,
- missing packet,
- duplicated packet,
- corrupted packet,
- reconnect,
- sustained stream.

Measure:
- packet loss,
- buffer stability,
- effective throughput.

---

## 5. Backend tests

Test:
- valid session creation,
- schema validation,
- unavailable database,
- duplicate requests,
- authentication errors,
- invalid model result payload.

---

## 6. End-to-end test

Minimum demo case:

```text
audio source
-> mobile
-> waveform
-> recording
-> Heart AI
-> result
-> session persistence
```

This must work with a file simulator before hardware is considered mandatory.

---

## 7. Acceptance criteria

### Heart AI
Project target:
- F1-score >90%

This target should be measured on a locked, appropriate test set.

### Streaming
Proposal target:
- stable 8 kHz audio flow.

### Tele-auscultation
Proposal target:
- end-to-end audio latency <100 ms.

### Safety
If signal quality is insufficient:
- system must warn or request re-recording,
- system must not present a confident clinical-looking result.
