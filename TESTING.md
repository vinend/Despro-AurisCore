# TESTING.md

## 1. Test strategy

```text
Unit tests
DSP/AI component tests
Schema/contract tests
Integration tests
End-to-end tests
Hardware-in-loop tests
Locked AI evaluation
```

Tests should reflect `PRD.md` requirements rather than only current implementation coverage.

---

## 2. Murmur AI tests

### Reproducibility

Same experiment config, split assignment, preprocessing provenance, and seed should produce reproducible/comparable behavior within the limits of the framework/hardware.

### Preprocessing

Test:

- sample-rate conversion;
- tensor shape;
- normalization;
- short/empty/silent input;
- invalid values;
- segmentation behavior;
- augmentation excluded from evaluation paths.

### Data governance

Test:

- participant/source separation;
- exactly one OOF prediction per expected participant when applicable;
- no forbidden fold leakage;
- normalization/calibration fitted only on allowed data;
- external validation and sealed holdout are not touched by train-only tasks.

### Evaluation

Automatically produce/validate:

- accuracy;
- precision;
- sensitivity/recall;
- specificity;
- F1;
- balanced accuracy when used;
- ROC-AUC;
- PR-AUC;
- confusion matrix;
- threshold and selection rule;
- finite predictions.

### Quantization/export

Compare pre/post export or quantization behavior, including:

- sensitivity/F1/precision as applicable;
- output compatibility;
- model size;
- latency;
- metadata presence.

---

## 3. Cardiac Event DSP tests

Test at minimum:

- no-signal input;
- short recording;
- noisy recording behavior;
- ordered S1/S2 timestamps;
- impossible/overlapping event rejection;
- systole/diastole interval construction;
- S3/S4 timing-window logic;
- configurable report-derived timing parameters;
- serialization of timestamps/intervals;
- deterministic behavior for deterministic input.

Where labeled data exist, report event-detection performance rather than relying only on visual inspection.

The Python prototype's focused CPU engineering suite is
`AI-Pipeline/tests/test_heart_dsp.py`. Run it from `AI-Pipeline` with
`python -m pytest -q tests/test_heart_dsp.py` in an environment where pytest
can collect the repository normally. It covers invalid audio, deterministic
filtering, synthetic event timing, interval/BPM/rate rules, candidate windows,
and the optional-Murmur `heart-analysis-v1` serialization. Synthetic pulses
are not labeled clinical validation; event detection still needs evaluation on
representative annotated recordings before product claims.

---

## 4. Rhythm DSP tests

Test:

- BPM calculation from known intervals;
- Normal threshold boundaries;
- Tachycardia threshold behavior;
- Bradycardia threshold behavior;
- irregular-interval metric/Arrhythmia indicator logic;
- missing/insufficient beat events;
- implausible BPM handling;
- serialization into the unified Heart result.

Report-derived thresholds are prototype configuration, not universal diagnostic truth.

---

## 5. Unified Heart result / contract tests

The WebApp file-demo tests run with `node --experimental-strip-types --test
tests/heart-analysis.test.mjs` from `WebApp`. They cover valid/invalid
`heart-analysis-v1` parsing, missing BPM, Murmur available/unavailable,
result-component rendering, service errors, and fail-closed behavior for
malformed responses. The Python
byte-stream bridge has CPU tests in `AI-Pipeline/tests/test_heart_bridge.py`.
The integrated route should also be smoke-tested with a synthetic WAV, a
silent WAV, and malformed bytes; expected outcomes are valid structured JSON,
invalid quality with no fabricated branches, and HTTP 415 respectively.
These are engineering tests, not clinical validation.

The Windows development checkout additionally runs `npm run test:heart` from
`WebApp` for the shared WAV/mock-PCM Heart path, packet gaps and malformed
packets, injected BLE software boundary, and result rendering. Those tests
do not verify physical BLE hardware.

Validate:

- supported schema version;
- `quality` behavior;
- Rhythm branch serialization;
- Cardiac Event branch serialization;
- Murmur branch serialization;
- branch algorithm/model version fields;
- nullable/unavailable branch behavior during transition;
- no fabricated outputs when quality is invalid;
- backward/transition adapters where intentionally supported.

---

## 6. Mobile tests

Test:

- device/input connection state;
- disconnect recovery;
- file simulator;
- waveform rendering;
- recording/playback;
- invalid signal warning;
- BPM/rhythm rendering;
- S1/S2 and interval annotations;
- S3/S4 candidate rendering;
- Murmur probability/result rendering;
- session save/history;
- schema-version handling.

---

## 7. BLE tests

Test:

- sequential packets;
- missing packet;
- duplicate packet;
- malformed/corrupted packet;
- reconnect;
- sustained stream;
- effective 8 kHz reconstruction;
- buffer stability.

Measure:

- packet loss;
- buffer underruns;
- effective throughput;
- timing continuity.

---

## 8. Backend tests

Test:

- valid session creation;
- schema validation;
- unavailable database/network;
- duplicate requests/idempotency where required;
- authentication failures;
- invalid analysis-result payload;
- unknown schema version;
- offline client behavior when backend is unavailable.

---

## 9. End-to-end tests

### Minimum Heart file-simulator E2E

```text
WAV/file input
-> mobile/analysis adapter
-> signal quality
-> Heart Rhythm DSP
-> Cardiac Event DSP
-> Murmur AI
-> unified Heart result
-> waveform/annotations/result UI
-> session persistence
```

This must work with prerecorded audio before hardware becomes mandatory.

### Hardware E2E

```text
physical stethoscope
-> BLE
-> reconstructed audio
-> same HeartAnalysisService
-> same result schema/UI
```

The analysis API should not need to change merely because the audio source changes.

---

## 10. Acceptance criteria

### Heart product acceptance

Use the Heart Definition of Done in `PRD.md`.

Murmur model completion alone is insufficient.

### Murmur AI engineering direction

Current internal targets are:

```text
Sensitivity >= 0.90
Specificity >= 0.85
Precision   >= 0.65
F1          >= 0.75
ROC-AUC     >= 0.92
PR-AUC      >= 0.85
```

These are engineering targets, not regulatory/clinical standards.

### H021 freeze and Heart adapter checks

The CPU-only `AI-Pipeline/tests/test_h021_freeze_adapter.py` checks H021
protocol/metrics hashes, five fold manifests, fold scaler/logistic and
normalization shapes, fail-closed unavailable behavior, and Heart DSP
continuity when Murmur is missing or errors. The read-only
`AI-Pipeline/scripts/audit_h021_fold_artifacts.py` verifies the original five
fold checkpoint hashes and lightweight artifact compatibility. Neither command
loads a CNN for inference, opens external validation/test, or trains a model.

The historical report/proposal F1 >90% target remains aspirational and should not be reported as achieved unless a valid locked evaluation demonstrates it.

### H022 preflight (training not started)

Before any authorized H022 launch in the research checkout, run
`python -m pytest -q tests/test_h022_preflight.py` from `AI-Pipeline`, then
`./scripts/start_h022.sh --check`. The launcher must match the locked protocol
SHA-256 `ab7331b77e92ba8353706d60be1606434095f44915d10e10ab1294f46452b913`
and the persisted H021 hard-negative provenance. Tests must reject outer-eval
leakage and any use of global H021 OOF false-positive identities as H022
training labels. The preflight also checks TensorFlow 2.20, GPU visibility,
and closed external-validation and sealed-test boundaries.

As of 2026-10-09, focused H022 preflight tests and launcher `--check` passed.
**H022 has not been trained and has no model metrics.** These checks establish
launch readiness only; they do not validate clinical performance.

### Streaming

Report target:

- stable nominal 8 kHz audio flow.

### Tele-auscultation

Report target:

- <100 ms end-to-end latency where achievable.

Always report measured values rather than assuming targets are met.

### Safety

If signal quality is insufficient:

- warn/request re-recording;
- do not present a confident clinical-looking result;
- do not invent missing branch outputs.
