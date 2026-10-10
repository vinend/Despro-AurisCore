# TESTING.md

Shared recorded-audio service checks live in
`AI-Pipeline/tests/test_analysis_service.py`: PCM/WAV parity, int16 scaling,
quality/size/rate rejection before backend loading, mode routing, candidate
eligibility, one-time initialization under concurrent requests, failure caching,
finite/versioned outputs, and persistent JSON-lines transport recovery.

Model package preparation: `AI-Pipeline/tests/test_model_audit.py` checks saved
artifact compatibility, invalid thresholds/shapes/normalization, corrupt and
missing weights, immutable packaging, domain normalization and tamper detection.
`scripts/audit_model_candidates.py --runtime` additionally loads saved CNNs and
checks deterministic finite inference on synthetic audio. These checks measure
software compatibility, not screening performance.

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

The WebApp Heart tests run with `npm run test:heart` from `WebApp`. They cover valid/invalid
`heart-analysis-v1` parsing, missing BPM, Murmur available/unavailable,
result-component rendering, service errors, and fail-closed behavior for
malformed responses. They also cover deterministic mock packet capture,
WAV encoding, sequence gaps, malformed packets, disconnects, and the injected
BLE software boundary. These are not physical BLE tests. The Python
byte-stream bridge has CPU tests in `AI-Pipeline/tests/test_heart_bridge.py`.
The integrated route should also be smoke-tested with a synthetic WAV, a
silent WAV, and malformed bytes; expected outcomes are valid structured JSON,
invalid quality with no fabricated branches, and HTTP 415 respectively.
These are engineering tests, not clinical validation.

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

## Heart inference and existing backend verification (2026-10-10)

120 focused Python tests passed across Heart inference, WAV bridge, shared analysis,
model audit, Heart DSP and H021 freeze compatibility. Includes actual saved Keras
inference on synthetic audio and a configured-package subprocess bridge test.
Temporary deployment evaluation fixtures are fictional, not performance evidence.
WebApp TypeScript tests were not run because its dependencies are not installed.
No training, sealed-test evaluation, commit or push was performed.

## Abdomen inference verification (2026-10-10)

180 focused compatibility tests passed across Abdomen inference/dataset handling,
Heart inference/DSP/WAV bridge, shared analysis, model audit and H021 freeze checks.
After adding the stdin WAV adapter, 3 focused WAV/worker checks passed, including
real A005 inference through the byte bridge and retained-worker requests. Two of
those checks are additional cases (182 unique passing tests across both runs).
Fourteen dependency deprecation warnings did not affect results. Test approval
fixtures are fictional; synthetic inference does not establish model performance.
Phase 4 changes only the existing Python pipeline; WebApp Abdomen integration is
phase 5. No training, sealed evaluation, deployment package promotion or push occurred.

## App integration verification (2026-10-10)

29 WebApp tests passed with no skips, including actual Python DSP, temporary
fictional Heart/A005 deployment fixtures, retained-worker reuse, concurrent
correlation, queue limits, timeout/cancellation and Windows process-tree cleanup.
TypeScript checking, linting of affected components/services and npm run build
passed. Type checking was run independently because the existing Next config
skips build-time type errors. Browser checks confirmed 75 BPM synthetic Heart
upload, Abdomen unavailable, silent-audio rejection, real main PCM recording,
playback and status history for both selected organs. Simulator provenance was
visible. The browser check also caught and fixed an incorrect fetch receiver.
No final packages were promoted; no physical BLE/mobile-offline validation,
training, sealed evaluation, commit, push or external deployment occurred.

## Final integrated verification - phase 6 (2026-10-10)

182 Python checks passed in one run, with 14 dependency deprecation warnings.
30 WebApp tests passed with no skips, including real Python recovery after active
cancellation and idle shutdown. Independent TypeScript checking, phase 6 script
lint and the production build passed. Nine real production HTTP scenarios passed
through the shared/organ-specific/legacy endpoints, including concurrent distinct
75/90 BPM recordings, missing models, invalid audio, size limits and recovery.
`npm run verify:integration` repeats the HTTP checks and writes ignored synthetic
evidence to `WebApp/artifacts/phase6-http.json`. See
`WebApp/docs/phase6-readiness.md` for scope, commands and model activation gaps.
Phase 5 browser evidence remains applicable: phase 6 changes verification/docs only.
No clinical/model performance evaluation or model promotion was performed.

## Wi-Fi streaming verification (2026-10-10)

33 WebApp tests and 3 gateway tests passed with no skips. The network test sends
200 real WebSocket binary frames through the gateway and browser decoder, then
checks all 80,000 samples in the ten-second WAV byte for byte. Additional checks
cover authentication/origin rejection, missing frames, overflow, stalled sources,
recording watchdogs and bounded AudioWorklet resampling without source mutation.
Independent TypeScript checking and linting of affected streaming files passed.
The final production build and all nine production HTTP integration scenarios
also passed. A first rebuild was blocked by the running test server's Windows
directory lock; stopping that test server allowed the rebuild to complete.

Production browser verification exercised the explicit engineering publisher:
streaming waveform, synthetic provenance, listening activation/deactivation,
automatic ten-second recording, WAV playback/download control and the existing
Heart API returning 75 BPM with unavailable Murmur. No browser console warnings
or errors were observed. The in-app browser did not report a download event, so
the download itself was not verified there; WAV bytes are covered by the network
test. Audible output, mobile browsers, sustained LAN performance and physical
acquisition have not been verified. No ESP-IDF toolchain or board is available;
the firmware network scaffold has not been compiled or flashed. See
`HARDWARE_TEAM_HANDOFF.md` and `WebApp/docs/device-streaming.md`.

## Lung verification — 2026-10-10

The existing Python suite passed 244 tests, including temporary synthetic Heart
training smoke tests. Running those was an unintended exception to the user's
no-training instruction. No Lung training occurred. Subsequent focused Lung,
package and service checks passed 55 tests without fitting weights; saved-model
checks reload random initialization only. All 37 WebApp tests and ten production
HTTP scenarios passed with Python configured. Build, TypeScript and affected-file
lint passed. Fictional test packages establish no model performance. Official HF
test labels remain unopened; physical audio/mobile/model validation is pending.

Pre-push verification after incorporating the current master packaging changes:
73 focused Python tests passed without fitting model weights. Analytical
spectrogram shapes now match centered/uncentered tensors, frequency-limited STFT
and odd/even FFT sizes. Initial EXP-L001 has no saved epoch/checkpoint; its local
status was corrected to interrupted after finding no active training process.

Lung input-pipeline correction: 25 focused Lung tests passed, including six new
tests for seeded multi-epoch permutations, complete sample coverage, packed
target/mask alignment, stable validation order, known batch counts, retained
partial batches, and malformed/test-cache rejection. A weight-free Keras model
evaluates three iterations without an exhaustion warning; stand-ins verify
both trainers pass shuffle=False and consume the corrected datasets. No model
weights are fitted by these checks and official dataset test labels stay sealed.

Read-only Lung diagnostics are covered by fictional fixtures checking masked
score distributions, always-positive F1 comparisons, concurrent phase outputs,
invalid scores/masks/thresholds, full cache support/weights/tail counts and
rejection of final or stale experiment provenance. No model is loaded or trained
and official test annotation files are not read by the diagnostic command.
The focused Lung suite passed 28 tests, including three new diagnostic tests;
the full local cache audit also completed without fitting or test-label opening.

Lung localization verification: 40 focused Lung tests passed, including 11 new
localization tests and one package/inference version test. Checks cover scored
WAV onset/offset output with a frozen stub, overlap averaging, padded-tail exclusion,
adjacent-frame floating-point stability, threshold equality, gap/duration rules,
missing-timeline separation, simultaneous classes, invalid input/quality/status,
complete held-out prediction coverage and cache alignment, one-to-one matched
boundary errors, version rejection and preservation of the live interval schema.
No weights were fitted. The real Linux EXP-L003 artifact is absent locally;
actual checkpoint localization accuracy and physical-device behavior remain
unverified. Official dataset test annotations were not opened.

## Lung learning-rate policy verification

`AI-Pipeline/tests/test_lung_training_policy.py` simulates Keras callback
lifecycles without fitting weights: reduction before stopping, LR floor,
used/next LR CSV values, unchanged optimizer iterations and weights, fixed-LR
baseline preservation, strict policy rejection, and frozen final replay without
validation. Run with the existing focused Lung dataset/lifecycle/localization
tests. Actual quality and epoch-count effects require a fresh Linux development
run; no sealed test is used to tune this schedule.

Verified 2026-10-10: the focused policy, localization, diagnostics, dataset,
Lung core, lifecycle and inference suite passed 55 tests. Keras emitted existing
NumPy array-copy deprecation warnings. CLI preflight accepted the plateau policy
against the real 46,308-window cache and reported `training_started: false`.

Detailed logging verification: `test_lung_training_log.py` covers UTC timestamps,
stderr/JSONL correspondence, throttled progress, invalid intervals, CPU/GPU
visibility reporting, and simulated best-checkpoint/early-stop callbacks without
optimizing weights. Dataset trainer stubs check persisted preparation/completion
and per-class evaluation events for both development and final paths. The focused
logging, policy, dataset and lifecycle suite passed 30 tests on 2026-10-10, with
Keras NumPy array-copy deprecation warnings; no model training was launched.

`test_lung_dropout.py` verifies v2 dropout validation, v1/default compatibility,
constant-LR/frozen-final semantics, unchanged temporal output shape, saved model
dropout retention and inference parity with identical weights (dropout disabled
at inference). Trainer stubs verify both development and final paths pass 0.4
for the opt-in dropout policy and 0.2 for earlier protocols without fitting.

Verified 2026-10-10: 73 focused Lung tests passed (dropout, logging, policy,
dataset, lifecycle, localization, diagnostics, core and inference), with Keras
NumPy array-copy deprecation warnings. Real-cache v2 preflight accepted 46,308
windows, dropout 0.4 and constant LR 0.001, reporting training_started=false.
No official test labels were opened and no weights were optimized.
