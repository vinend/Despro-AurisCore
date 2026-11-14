# TESTING.md

Branch publication checks (2026-11-14): 14 serial bridge/provisioning tests pass
from this branch's source; all six added PowerShell scripts parse successfully.
No board was reflashed or radio retry issued for these publication checks.
Radio startup remains a failed physical acceptance, as detailed below. Diagnostic
README files are preserved at the user's request; current manual BLE control and
staged Wi-Fi behavior are authoritative in this document and the sketches.

Staged Wi-Fi init-only diagnostic (2026-11-14): default brownout enabled and
no SSID/connect/scan. The direct ESP-IDF sequence returns ESP_OK for NVS init,
netif init, default event loop, esp_wifi_init and esp_wifi_set_mode on the S3.
It remains ready during seven seconds before R. One R invokes esp_wifi_start;
brownout messages occur and the chip restarts. Driver initialization succeeds
again after reset and returns to waiting. Thus earlier WiFi.mode failures cannot
be described as proof that esp_wifi_init itself fails: the Arduino wrapper also
calls esp_wifi_start. Source is Firmware/diagnostics/wifi_init_only and evidence
is `.runtime/hardware/wifi-init-only-test/result.json`. No audio/model data used.

User-supplied simple Wi-Fi control (2026-11-14): a separate WiFi.h sketch calls
WiFi.mode(WIFI_STA), then WiFi.begin for the locally provisioned router, with a
20-second connection timeout. Brownout protection is enabled for this specific
test at user request; runtime reads BROWNOUT_HW_ENABLE=1. Compiled flags preserve
the normal S3/OPI board setup; there is no PHY table override, microphone or
gateway code. Flash hash passes. In 24 seconds repeated brownout messages and
POWERON resets occur after WIFI_MODE_BEGIN, without WIFI_MODE_OK or WIFI_BEGIN.
Connection/password code has not been reached. Evidence, source and read-only
PowerShell live monitor are in `.runtime/hardware/wifi-simple-test`. Local
credentials remain ignored by Git and are not printed. README is untouched.

SDK/build re-audit (2026-11-14): official archive SHA256 values match and 35
selected installed compiler/core/SDK runtime files match the official archives.
Actual build commands select ESP32-S3 qio_opi. The copied root sdkconfig's quad
PSRAM defaults are not the effective qio_opi headers. A real build-script bug
was found: brownout override used build.defines and replaced BOARD_HAS_PSRAM.
The override now uses compiler.cpp.extra_flags, preserving the board flag.
The fixed image retains the 10 dBm startup table, passes image/flash verification,
and reports IDF v5.5.5, 16 MiB flash, 8 MiB PSRAM and BUILD_PSRAM_ENABLED=1.
Three POWERON resets occur in 21 seconds with BROWNOUT_HW_ENABLE=0 immediately
before each WIFI_INIT_BEGIN. Thus this confirmed build bug is fixed, but its
causality for reset is not established and startup still fails. Sources and
observations are in `.runtime/hardware/wifi-flags-fixed-test`, with package audit
at `.runtime/hardware/sdk-integrity-audit.json`. No further flash erase occurred.

User-requested flash factory reset (2026-11-14): initial full read failed at
91.5% with invalid serial packet head; no erase had occurred. Sixteen 1 MiB
chunks and the assembled 16 MiB backup subsequently pass esptool verification.
Flash is erased once, then the preserved AurisCore Wi-Fi 10 dBm/brownout-off
app is installed and its hash verified. Two Windows-saved profiles are securely
reprovisioned locally and PROFILE_COUNT=2 is observed. Post-reset observation
shows four POWERON resets at WIFI_INIT_BEGIN plus the expected configuration
software reboot. No WIFI_MODE_READY or gateway authentication occurs.
Evidence is `.runtime/hardware/factory-reset-wifi/result.json`; raw flash backup
is private local material containing stored configuration. README is untouched.

Manual BLE v2 control verifies eight seconds idle without radio startup, one R
causing exactly one BLE_INIT_BEGIN, one POWERON reset, and return to idle with
ATTEMPTED=0 and uptime/status available. No automatic radio retry occurs during
the subsequent seven seconds. Compile/upload hashes and PowerShell parsing pass.
Evidence is in `.runtime/hardware/ble-manual-v2/result.json`. Host R-relative
timestamps are serial timing only; no voltage measurement is claimed.

Further USB-only controls (2026-11-14): a locally retained 20 KiB NVS backup and
active-entry inventory find the provisioning namespace but no active `phy`
namespace/calibration keys. No calibration erase is performed. For the same BLE
app on S3, an esptool-verified bootloader header at 40 MHz flash clock still
produces three POWERON reset markers during 20 seconds before BLE_INIT_READY.
Original bootloader is restored with flash hash verification. Evidence is in
`.runtime/hardware/phy-calibration-audit` and `ble-flash40-control`. These checks
have not isolated the shared USB power/EN path from all firmware/SDK causes.

Independent SDK control (2026-11-14): Arduino core 2.0.14 / ESP-IDF 4.4.6 is
installed under ignored `.runtime/hardware/arduino-core-2.0.14`, with isolated
CLI data/download/user paths. The existing 3.3.12 installation is preserved.
An API-compatible BLE bench sketch (CPU 240 MHz, brownout disabled, default PHY)
builds and flashes with hash verification. The running S3 prints CORE_VERSION=
2.0.14 and produces four POWERON resets at BLE_INIT_BEGIN during 24 seconds.
A ten-second service-filtered scan again finds no target. Changing these SDK
versions has not resolved the reset. Root cause remains unproven. Core 3 BLE
source/ELF/app/boot artifacts were saved before the control and are restored
after testing. Evidence is in `.runtime/hardware/ble-core2-test`.

BLE isolation on original S3 (2026-11-14): core 3.3.12 compilation and esptool
flash hash verification pass. Runtime confirms brownout disabled and CPU 240 MHz.
During 24 seconds, four POWERON reset markers occur at BLE_INIT_BEGIN, with no
BLE_INIT_READY or advertising. A separate local Windows BLE scan using the
specific service UUID finds no target in ten seconds. Therefore GATT PING/PONG,
notifications and reconnect cannot be verified. The BLE bench firmware remains
installed. Logs, isolated client dependency lock and results are retained in
`.runtime/hardware/ble-radio-test`; a dedicated COM3 PowerShell monitor is open.
This observation leaves SDK and electrical reset causes unresolved.

Second-board minimal test (2026-11-14): COM6 is classic ESP32-D0WD-V3 revision
3.1, MAC 80:f3:da:61:66:28. Separate classic firmware builds and uploads with
hash verification. The packaged PHY table has six capped values of 40 quarter-dBm
units; CPU is 80 MHz and brownout is disabled. Twenty-five seconds produces one
TG1WDT_SYS_RESET and three SW_CPU_RESET markers, with LoadStoreError/debug panics
at startup and no WIFI_MODE_READY or completed scan. An additional eight-second
capture records another watchdog reset. These observations do not identify an
electrical or SDK cause. Minimal classic firmware remains installed; original
4 MB backup SHA256 is verified and retained in `.runtime/hardware/new-esp32-com6`.
Evidence and COM6 live monitor are in `.runtime/hardware/radio-minimal-esp32-off-test`.

Standalone radio isolation (2026-11-14): `Firmware/diagnostics/wifi_radio_minimal`
compiles under core 3.3.12, CPU 80 MHz, brownout disabled. Its packaged PHY init
table contains fourteen 10 dBm values; map verification confirms the standalone
table object. Esptool verifies the existing AurisCore app against its saved copy
before uploading and verifies the minimal image after writing. On the original
S3 MAC 28:84:85:50:b6:2c, 24 seconds yields four POWERON reset markers during
WiFi.mode, before WIFI_MODE_READY or any scan. Radio startup remains unsuccessful
without AurisCore/sensor/gateway code. This does not isolate Arduino/PHY SDK from
electrical reset causes. Minimal firmware remains installed. Source, ELF, image,
hashes and restore script for the prior combined AurisCore app are preserved at
`.runtime/hardware/saved-auriscore-before-radio-minimal/`; current observation is
`.runtime/hardware/radio-minimal-off-test/physical-result.json`.

Combined startup-power bench test: the 10 dBm PHY init table with brownout
disabled passes binary-difference checks and esptool upload hash verification
on MAC 28:84:85:50:b6:2c. During 38 seconds of observation there are six
`POWERON` reset markers, each after `WIFI_INIT_BEGIN`, with no `WIFI_MODE_READY`
or gateway authentication. This tested cap has not resolved startup resets.
The combined image remains flashed at the user's request. Artifacts are in
`.runtime/hardware/phy-startup-10dbm-brownout-off/`. Supply/EN causes remain
unresolved without measurements; emitted RF power and current were not measured.

Brownout-off bench build (2026-11-14, explicitly requested by user): separate UART
build compiles on core 3.3.12. Disassembly confirms setup calls
`esp_brownout_disable`. Upload to MAC 28:84:85:50:b6:2c passes esptool flash
verification. Runtime prints `BROWNOUT_DETECTOR_DISABLED`, then reboots during
`WIFI_INIT_BEGIN` with `rst:0x1 (POWERON)` before `WIFI_MODE_READY`.
This confirms a reboot remains with the detector disabled. Its physical cause
requires rail measurement. Evidence and pre-flash app backup are retained in
ignored `.runtime/hardware/brownout-off-uart`. The requested bypass stays flashed.

Serial monitor logging now uses one auto-flushed writer with shared read/write
access. A concurrent-reader check and a simulated writer failure pass: failed
file logging is disabled while console/serial monitoring remains active.

LED preparation (2026-11-14): native USB firmware with the LED state engine
compiles successfully. Four gateway tests and seven streaming tests pass,
including validated indicator forwarding and legacy publisher capability gating.
TypeScript checking passes. Physical RGB output is disabled pending wiring.
The embedded SELFTEST includes boot, disconnected, mode, breathing and completion
patterns; running it on the intended S3 board remains pending after board removal.

Portable monitor `scripts/monitor_auriscore.ps1` parses successfully and lists
ports under Windows PowerShell 5.1. Hardware acceptance on the second laptop is
pending. R is gated by the Wi-Fi firmware identity and sends a single manual
RETRY. The monitor preserves diagnostic timestamps and closes the serial port
on exit. It does not provision credentials or alter firmware.

## Wi-Fi/router plus phone-hotspot profiles — 2026-11-14

Eleven provisioning tests pass for Wi-Fi/hotspot roles, priority flags, UTF-8
SSID limits, gateway host validation and boot/brownout errors. Actual ESP32 SELFTEST
passes profile upsert/priority/four-entry capacity, fallback timing/index wrap,
and exact packet/FIR parity against independent synthetic Python references.
SELFTEST restores real RAM configuration and never writes credentials to NVS.
Firmware build and flash hashes pass. One stored real profile is observed.
A bounded delayed/recovery radio retry still brownouts before Wi-Fi initialization
finishes, so physical association/failover/streaming acceptance remains incomplete.
See Firmware/wifi-capture/README.md. No deep sleep during streaming, detector bypass,
model retraining, external validation, sealed-test use or clinical relabeling occurs.

## Local Wi-Fi capture firmware — 2026-11-14

Physical follow-up finds repeated brownout boot resets after configuration is
saved; radio/audio acceptance is blocked on stable power. Three generated-line
tests cover explicit brownout classification, normal single boot/authentication,
repeated boot detection and capture-init errors. No brownout protection is disabled.
After a cable change, a real startup-isolation probe with I2S deferred still
records 16 brownout messages in eight seconds during Wi-Fi initialization, before
the I2S task starts. Compile/flash hashes pass; radio/audio acceptance remains
blocked by the observed supply reset. Evidence is retained under `.runtime/hardware/`.

Arduino core 3.3.12 / WebSockets 2.7.2 compile passes on ESP32-S3 N16R8 settings.
Upload on COM3 confirms chip identity and all flash hashes; a separate USB STATUS
probe identifies the running Wi-Fi sketch. Original serial-v4 source SHA-256
remains 75c2602082ba37340fe186377e3355c86c2dcaba8ea15dd27323b6c74eea3574.
Evidence: ignored `.runtime/hardware/wifi-preflight.json`. This does not verify
radio audio delivery: password provisioning, complete recording, reconnection,
FIR runtime parity, sustained continuity and latency remain acceptance checks.
No dataset split, model weight or medical label changed.


Hardware laptop bring-up commands and measured software checks are recorded in
[HARDWARE_BRINGUP_2026-11-14.md](HARDWARE_BRINGUP_2026-11-14.md).

Arduino serial-capture bring-up: exact provided firmware compiled successfully with
esp32:esp32 3.3.12 for the documented UART configuration (898667 bytes sketch,
56752 bytes globals). See HARDWARE_BRINGUP_2026-11-14.md. Physical USB/capture
acceptance and Native USB settings remain pending board access.

Physical serial-v4 integration adds three tests covering fragmented packets,
CRC/sequence/short-write rejection, continuous FIR parity and binary v2 layout.
Two engineering model tests enforce explicit authorization and input hash/scope
rejection. Actual COM3 capture reached the gateway as 80,000 continuous samples;
both live inference endpoints returned completed using real captured PCM.
Engineering tests do not validate disease or event-boundary performance.

## Fixed-reference features and trajectory — 2026-11-10

40 focused checks pass for Lung-only fixed-reference/floor features, identical
shared/legacy tensors, overlap/tail/mask behavior, closed v7 policy, grouped
probe selection and pre-restoration epoch checkpoints with unchanged optimizer
counter. Broader regression: 297 pass, one existing Abdomen constructor validation
test fails and reproduces on exported Git HEAD source. That unrelated failure
is preserved in the evidence and not counted as a passing test. Full real-cache
payload/overlap verification is required before the new representation is used.
See AI-Pipeline/docs/lung_fixed_reference_trajectory.md.
Complete real-cache verification passes all 46,308 non-feature payloads and
38,590 overlap pairs (maximum feature delta zero). Real v7 preflight and RTX 5060
forward/backward/trajectory snapshot pass with zero optimizer updates. Ten final
feature/trajectory tests include actual EarlyStopping restoration. Old/new parsed
indices match; CSV byte hashes are recorded separately, not claimed identical.

## Completed L016–L018 deep review — 2026-11-10

Six focused review tests pass: per-window positive/negative BCE decomposition,
mask-zero windows, monotonic analytic weight inverse, absolute-frame overlap
merge/padding/conflict rejection, and a synthetic reproduction of window-relative
dB offsets, plus existing loss/stopping checks. Completed-run population hashes
match and best losses reconstruct within 0.0000015. A 32-pair deterministic GPU
inference-only probe holds audio/model fixed and reduces overlap disagreement
after in-memory reference alignment. No optimizer updates, cache mutation,
threshold selection or test-label reads. See
[evidence and limits](AI-Pipeline/docs/lung_l016_l018_deep_review.md).

## Lung objective/numerical verification — 2026-11-10

148 complete Lung/source tests pass, no skips, 271 dependency warnings, 17.90 s.
New checks cover closed v6 policies and legacy replay, actual Dense sigmoid
extreme gradients, logits-reference/mask agreement, fitting-only weight support,
zero-window filtering/cardinality, complete validation coverage, fixed-threshold
source/date strata and queue parity/failure preservation. All three real-cache
preflights pass. Actual RTX 5060 forward/backward at [2,309,96] has ten finite
gradient arrays and exact reload parity, without optimizer steps. On frozen L015,
explicit deterministic float32 CPU/GPU probes each have zero cross-process score
difference; historical saved-score parity under that runtime still fails.
See [protocol and evidence](AI-Pipeline/docs/lung_objective_experiments.md).

## L015 pipeline audit — 2026-11-10

Three new `test_lung_loss_audit.py` tests pass in WSL/TensorFlow (no skips):
per-window/global-frame weighting mismatch, unknown-mask zero contribution and
extreme-logit gradient loss under legacy clipping versus stable BCE/reference.
The read-only investigation scans 46,308 development windows and runs frozen
checkpoint inference on deterministic diagnostic samples without optimizer steps.
All ten saved layer arrays equal the best checkpoint. Strict reloaded prediction
parity on 16 windows fails at atol/rtol 1e-4 (max 0.00012337); zero sampled
threshold decisions change. This remains open, not a passing parity claim.
See [scope, evidence and limitations](AI-Pipeline/docs/lung_l015_pipeline_investigation.md).
No training policy, threshold, source split, official test or production contract
was changed by this investigation.

## Three-sound Lung verification — 2026-11-10

135 complete Lung/source tests pass with zero skips and 231 dependency
deprecation warnings (17.18 s). New tests verify L015 differs from L011 only in
selected classes, uses columns 2/3/5, emits 309 x 3 independent sigmoid outputs
with 269,315 parameters, and passes actual development trainer wiring without
fitting. Real HF preflight passes all 46,308 windows. Evidence:
`AI-Pipeline/artifacts/lung-launch/three-sound-checks-20261110/`.
GPU fitting is launched separately; no test labels or deployment model activated.

## Compact Lung verification — 2026-11-10

Latest full Lung/source suite: 132 passed, zero skips, 221 dependency deprecation
warnings, 14.48 s. `test_lung_compact.py` covers strict v5 policies, legacy replay,
parameter/time-shape invariants, serialization, valid-label-only error cues and
matching-control comparison labels. The trainer integration tests include both
compact tasks without fitting. Actual synthetic forward/backward on GPU:0 passes
for both 93k-parameter models with zero optimizer steps. Evidence:
`AI-Pipeline/artifacts/lung-launch/compact-checks-20261110/`.
Ten selected development recordings / 60 windows pass source/cache regeneration;
user listening confirmation was received before L013/L014 launch. This does not
verify all labels or establish model improvement. Official test remains closed.

## Read-only completed Lung review — 2026-11-10

`test_lung_training_review.py`: two tests pass for best-epoch-plus-patience
arithmetic and per-window masked BCE/common-weight loss reconstruction, including
shape/weight guards. The real review validates identical saved truth/mask/group/
class identities across L006/L007/L008/L012 and reconstructs reported best loss
within 0.00004. No fitting, threshold reselection or official-test access occurs.
`scripts/analyze_lung_overfit.py` saves complete metrics and a visually inspected
four-panel PNG. See AI-Pipeline/docs/lung_l012_review.md for findings and limitations.

## SPRSound source-addition verification — 2026-11-10

`test_sprsound.py` verifies test-patient/blob exclusion from metadata only,
millisecond category mapping, combined positives, acoustic-only validity,
unknown interval/phase masking, quality and timestamp rejection, immutable cache
creation, combined manifest counts, and byte-identical original HF validation.
Latest full suite: 116 passed, no skips, 173 dependency deprecation warnings,
7.58 s (CPU execution under the WSL TensorFlow environment). Log:
`AI-Pipeline/artifacts/lung-launch/SPRSound-20261110/full-tests.log`.
Actual multi-source cache preflight passes 48,489 development windows.
L012 startup confirms RTX 5060 GPU:0 with a 3,072 MiB cap; no completed metrics
or clinical validity are claimed. Source test labels/audio were not downloaded.

## Lung generalization policy/queue verification — 2026-11-10

`test_lung_research.py` exercises invalid optimizer/augmentation/class policies,
frozen lower-LR final replay, deterministic TRAIN-only masking with unchanged
targets/masks, validation isolation, actual development wiring for each of the
five policies without fitting weights, comparison population guards, explicit
queue authorization and serial failure preservation. The localization test
also validates projected sound-head predictions against original cache columns.
Older policy and retained-worker tests remain in the complete Lung suite.
These engineering tests do not establish an accuracy improvement.

Latest complete Lung run: 108 passed, no skips, 173 dependency deprecation
warnings, 13.60 s under Ubuntu WSL2 / TensorFlow 2.21.0. Log:
`AI-Pipeline/artifacts/lung-launch/improvement-checks-20261110/pytest.log`.
`git diff --check` also passes. Standalone L007–L011 training was launched only
after these checks; no official-test evaluation was performed.

## Local WSL GPU launch verification — 2026-11-10

Ubuntu-24.04 WSL2 / Python 3.12.3 / TensorFlow 2.21.0 sees the RTX 5060.
An L006-shaped model (309 x 96 input, six outputs, dilation 16) produced finite
outputs and gradients on GPU:0, with zero optimizer steps and synthetic data only.
`python -m pytest tests/test_lung*.py -q` passed all 85 tests, no skips,
with 123 dependency deprecation warnings. `pip check` found no broken requirements.
Linux real-cache preflight passed all 46,308 development windows.
Sampled source/cache review covered six recordings / 36 windows without mismatch;
the user subsequently confirmed listening/annotation review was appropriate.
This does not establish exhaustive label coverage, patient independence or model
performance. Evidence is ignored under
`AI-Pipeline/artifacts/lung-launch/EXP-L006-20261110/`; alignment evidence is
under `artifacts/lung-launch/alignment-gpu-20261110/` within AI-Pipeline.
L006 was launched separately as WSL PID 2489; startup reached TRAIN statistics.
No official-test labels opened, package activated or completed model metrics
claimed at launch. Runtime checks do not validate clinical performance.

## RD-H022-TMIL-P1

For progress_heart, run [the remote GPU checks](AI-Pipeline/research/h022_temporal/README.md) before RD-H022-TMIL-P1. After one completed run, verify-results replays all outer recordings and compares participant decisions before reporting phase and time candidates.

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

Context/alignment verification uses `test_lung_context.py` and
`test_lung_alignment.py`: invalid/legacy/frozen dilation policy, identical model
parameter count and temporal output shape, saved-model parity, source/annotation
hash rejection, regenerated cache targets including deliberate shifted-target
detection, immutable review output, listenable WAV copies and exclusion of
non-development IDs. Trainer stubs verify v3 dilation reaches development and
final builders. No optimizer steps or official-test annotation reads are needed.

Verified 2026-10-10: 85 focused Lung tests passed, with Keras NumPy array-copy
deprecation warnings. The real local development review selected six recordings
covering TRAIN/validation devices plus stridor/rhonchi examples, regenerated 36
windows and found zero source/cache mismatches. Listening-based acoustic alignment
remains unverified. Evidence is ignored under artifacts/lung-launch; no model
fitting or official-test opening was performed.
