# ROADMAP.md

L019 launched by explicit user request (2026-11-10): fixed-reference Lung GPU
training with full epoch trajectory, control L017, standalone WSL PID 26483.
Post-fit diagnostics/localization/parity and same-label-population comparison are
predeclared; no adaptive successor or automatic deployment. Initial GPU startup
and cache preflight pass. See AI-Pipeline/docs/lung_l019_fixed_reference.md.

Lung representation/observability implementation (2026-11-10): opt-in fixed dB
reference/floor and v7 epoch checkpoints/probe metrics are implemented and tested.
New cache preparation/verification preserves old labels, splits and models.
Next fitting must use fresh provenance and TRAIN normalization, with grouped
research selection; no model training is launched by this implementation task.
See AI-Pipeline/docs/lung_fixed_reference_trajectory.md.

Completed L016–L018 (2026-11-10): all queue checks passed, no candidate meets the
research gate. The next Lung priority is an opt-in fixed-reference/fixed-floor
feature representation with overlap invariance tests, predeclared trajectory
checkpoints/class/source metrics and TRAIN-only grouped comparisons. A paired
frozen-model probe demonstrates sensitivity to window dB reference; source
generalization and temporal supervision remain open. No further training is
launched by this review. See AI-Pipeline/docs/lung_l016_l018_deep_review.md.

Lung objective continuation (2026-11-10): implemented and verified versioned
stable BCE/deterministic float32, per-window-mass weighting and TRAIN-only
empty-window filtering. A bounded serial L016/L017/L018 protocol isolates later
objective changes and adds parity/source-stratified evidence; 148 tests pass.
No performance or deployment claim follows from these engineering checks.
See [execution protocol](AI-Pipeline/docs/lung_objective_experiments.md).
Standalone GPU queue launched as WSL PID 19198, with L016 active and L017/L018
pending successful predecessor checks. No completed-run metrics exist at launch.

L015 status (2026-11-10): completed, best epoch 2 / stopped epoch 10; narrowing
to three labels did not resolve degradation. The next Lung work is a versioned
stable-loss verification, explicit weighting/mask objective, inference parity and
source-stratified TRAIN-only evaluation protocol, followed by compatible targeted
data acquisition if supported. No additional run was launched during the audit.
See [prioritized investigation](AI-Pipeline/docs/lung_l015_pipeline_investigation.md).
The launch notes below are historical; no deployment candidate is approved.

Temporary three-label Lung priority (2026-11-10): user-authorized L015 trains
wheeze/rhonchi/crackle only against L011, preserving original HF data and other
training settings. 135 tests pass; WSL GPU supervisor PID 14888 is launched.
No new metrics are claimed at launch. Phase/product requirements and official
test roles remain unchanged. See AI-Pipeline/docs/lung_three_sound_experiment.md.

Compact Lung execution (2026-11-10): error review, user listening confirmation,
opt-in bottleneck policies, tests and GPU kernel checks completed. L013 phase
vs L010 and L014 sounds vs L011 are launched serially with unchanged HF data and
early-stopping rules; WSL supervisor PID 11139, L013 active at startup. No new
metrics or deployment eligibility are claimed. See
AI-Pipeline/docs/lung_compact_experiments.md for protocol, counts and artifacts.

Latest Lung planning checkpoint (2026-11-10): L007–L011 queue completed.
Separate phase head L010 improves frame ranking and reduces phase conflict to
42.31%, but event localization/respiratory availability remain poor. Next plan:
bounded error/annotation review, then controlled compact phase/sound comparisons
against L010/L011, followed conditionally by weighting/sampling/decoder studies.
No additional training is launched by this planning update. See
AI-Pipeline/docs/lung_next_steps.md. Official test and deployment remain closed.

Lung completed-result review (2026-11-10): L012 is completed and not promoted.
Epoch-ten stopping is the configured best-epoch-two plus patience-eight behavior.
Same-population common-weight/ranking/phase analysis does not show overall
improvement from this source addition. L007/L008 are also completed; L009 was
active at the review's initial queue snapshot. No new training or threshold
selection was launched for the review. See AI-Pipeline/docs/lung_l012_review.md.

Lung additional-source pilot (2026-11-10): pinned SPRSound 2022 TRAIN acquisition,
patient/blob exclusions, acoustic masks and immutable mixed-cache preparation are
implemented. L012 was launched as WSL PID 3621 with GPU active; 116 Lung/source
tests pass. HF validation is unchanged, official tests remain closed, and source
rare-class support remains limited. No new model metrics exist at launch. See
AI-Pipeline/docs/lung_sprsound_training.md for source counts, assumptions and paths.

Lung generalization probes (2026-11-10): L006 is completed, best epoch two,
validation loss 0.82691; phase conflict/positive-prediction and boundary issues
remain. L007–L011 separately study lower initial LR, weight decay, TRAIN frequency
masking and independent phase/sound heads under GPU-only serial execution.
Official test and model activation remain closed. Additional-source assessment
prioritizes SPRSound acoustic labels, considers ICBHI cycle-level supervision,
and records restricted incremental HF labels; no new source is merged yet.

Launch checkpoint: WSL supervisor PID 384, queue running with L007 active,
108 Lung engineering tests passing. New-run metrics remain pending. Evidence:
`AI-Pipeline/artifacts/lung-launch/EXP-L007-L011-20261110/queue/`.

Lung execution update (2026-11-10): local GPU development training is requested.
The [Lung improvement plan](LUNG_IMPROVEMENT_PLAN.md) defines L006 context dilation,
annotation review, grouped comparisons and conditional next experiments. Windows
base-data preflight passes; Ubuntu WSL2 sees the RTX 5060 and TensorFlow 2.21.0
passes actual model forward/backward GPU checks. All 85 Lung tests pass.
EXP-L006-temporal-cnn-context was launched as WSL PID 2489; startup reached
TRAIN statistics. No completed model metrics or official-test evaluation exist
at launch. Logs/protocol are in `AI-Pipeline/artifacts/lung-launch/EXP-L006-20261110/`.

## Current priority

**Heart first: preserve Murmur research discipline, validate the implemented DSP prototype, complete the unified demo, and confirm physical hardware integration.**

Heart = Rhythm DSP + Cardiac Event DSP + Murmur AI.

---

## Milestone 1 — Murmur research foundation

Status: substantially established.

- [x] participant-aware dataset/split discipline
- [x] reproducible CNN experiment framework
- [x] full evaluation metrics beyond accuracy
- [x] immutable named experiments
- [x] H014 frozen validation benchmark
- [x] H015 site-aware MIL study
- [x] H016 fold-local pretrained site-aware MIL study
- [x] H017–H020 participant-training, pooling, and classifier studies
- [x] H021 train-only acoustic hard-negative mining result frozen
- [x] H022 protocol and leakage-safe preflight prepared
- [ ] H022 training and OOF evaluation (not started)

Exit condition:

- current research state can be reproduced and explained without reopening the sealed holdout.

---

## Milestone 2 — Murmur deployment candidate

Model audit/package preparation now supports structural verification, optional
synthetic inference, and immutable engineering candidates for Heart and Abdomen.
A005 is preliminary; no Heart deployment model is selected. The H021 fold weights,
normalization and scaler artifacts are absent from this Windows checkout (the
freeze manifest is present). See `AI-Pipeline/docs/model_candidate_audit.md`.

- [x] audit H016–H020 operating points and failure mechanisms
- [x] preserve sensitivity-first threshold discipline in completed experiments
- [x] reduce train-only OOF FP from H020 179 to H021 117 at 0.90 sensitivity
- [x] use participant-safe train-only OOF for research selection
- [ ] separately authorize and run H022; no results exist yet
- [ ] open external validation only after the predefined gate
- [x] freeze H021 research protocol, OOF threshold, and artifact provenance
- [ ] define and evaluate a final deployment model or predeclared inference rule
- [ ] create mobile-compatible export candidate

Exit condition:

- one Murmur candidate is frozen for integration with documented limitations and reproducible metadata.

---

## Milestone 3 — Cardiac Event DSP

Progress: a CPU-only S1/S2 and interval candidate prototype now exists in
`AI-Pipeline/src/auriscore/heart_dsp.py`. The milestone remains open until
representative labeled-recording validation and integration are complete.

- [x] prototype S1 candidate detection
- [x] prototype S2 candidate detection
- [x] systolic/diastolic interval derivation
- [x] experimental S3 candidate logic
- [x] experimental S4 candidate logic
- [x] event timestamp serialization
- [x] synthetic engineering tests
- [ ] representative labeled-recording validation and robustness evaluation
- [ ] complete event visualization annotations

Exit condition:

- Heart recordings can produce inspectable event annotations through a stable API.

---

## Milestone 4 — Rhythm DSP

Progress: the same prototype provides median S1-interval BPM, configurable
rate categories, and an insufficient-data-aware irregularity flag. Clinical
performance and real-recording robustness remain unverified.

- [x] beat interval computation
- [x] BPM estimation
- [x] Normal/Tachycardia/Bradycardia prototype rule
- [x] irregularity prototype logic
- [x] invalid/insufficient-data behavior
- [x] synthetic engineering tests
- [ ] real/labeled recording validation

Exit condition:

- Heart recordings can produce reproducible BPM/rhythm output through a stable API.

---

## Milestone 5 — Unified Heart result

Step 2 shared service infrastructure is implemented: real recorded PCM/WAV,
quality checks, explicit Heart/Abdomen routing, versioned envelope/errors and
cached backend lifecycle. It retains Heart DSP while reporting missing model
branches explicitly. Organ-model adapters and WebApp wiring are implemented;
activation still requires approved final model/evaluation packages.

Progress: `AI-Pipeline/src/auriscore/heart_result.py` assembles a prototype
`heart-analysis-v1` result with an optional Murmur adapter. The WebApp service
integration exists; offline mobile integration remains open. Murmur AI completion alone does not complete Heart.
H021 development evidence is frozen, but its outer-fold pipelines are not a
defined deployment model. The optional Murmur service reports unavailable
until a separate deployment decision and evaluation are completed.

- [x] implement `heart-analysis-v1`
- [x] serialize Rhythm and Cardiac Event DSP results
- [x] represent Murmur explicitly as unavailable when no model is supplied
- [x] include branch/model/algorithm versions where available
- [x] explicit low-quality fail-safe result
- [x] integration tests for the prototype contract
- [ ] connect a separately evaluated deployment-ready Murmur model
- [ ] validate the complete three-branch product path

Exit condition:

- one analysis call returns a versioned result representing all three branches.

---

## Milestone 6 — Heart mobile demo

Progress: the WebApp has a CPU-backed Heart WAV file demo and a ten-second
WebSocket/mock PCM capture path to the same versioned result view. This is a
server-backed development slice; mobile/offline, physical BLE, waveform
markers, Murmur deployment inference, and persistence remain open.

- [ ] Flutter analysis screen
- [x] WebApp WAV file simulator
- [x] WebApp mock/WebSocket PCM capture to the same Heart service
- [ ] live/static waveform
- [x] WebApp recording/playback (real PCM/WAV)
- [x] WebApp BPM/rhythm display
- [x] WebApp numeric candidate/event and interval display
- [ ] S1/S2 markers
- [ ] systole/diastole regions
- [ ] S3/S4 candidate markers
- [ ] Murmur probability/result
- [ ] local session save

Exit condition:

- complete Heart demo works without physical hardware.

---

## Milestone 7 — Hardware integration

- [ ] BLE service contract locked (UUIDs and packet layout need firmware confirmation)
- [ ] packet decoder
- [ ] buffer management
- [ ] packet-loss/duplicate detection
- [ ] reconnect behavior
- [ ] real 8 kHz device audio test

Exit condition:

- physical stethoscope stream can replace the file simulator without changing Heart analysis behavior.

---

## Milestone 8 — Session/report/backend

- [ ] patient/session metadata
- [ ] recording metadata/reference
- [ ] analysis-result persistence
- [ ] report generation
- [ ] authentication integration as implemented
- [ ] offline-safe sync behavior

Exit condition:

- session/report workflow works without turning backend availability into a local-analysis dependency.

---

## Milestone 9 — Tele-auscultation

- [ ] WebRTC signaling
- [ ] remote client/browser path
- [ ] live audio stream
- [ ] latency/jitter/packet-loss measurement
- [ ] failure recovery

Exit condition:

- stable remote listening demo with measured performance.

---

## Milestone 10 — Lung

The user selected HF_Lung_V1 as the single initial Lung dataset on 2026-10-10.
See `LUNG_TRAINING_PLAN.md` for six proposed phases: dataset/annotation audit,
preprocessing and aligned targets, task-specific training, grouped evaluation,
verified package/inference, then existing backend/app integration. Planning does
not complete these milestones or launch training. Exact released subtype labels
and grouping limitations must be audited before setting supervised targets.

- [ ] respiratory phase analysis
- [ ] respiratory rate / durations where supported
- [ ] I:E ratio
- [ ] wheeze analysis
- [ ] crackle analysis
- [ ] rhonchi analysis
- [ ] visualization/result schema

---

## Milestone 11 — Abdomen

- [ ] bowel event detector
- [ ] bowel rate
- [ ] bowel-rate variability / inter-event metrics
- [ ] report-defined pattern categories
- [ ] Harmonic Sound indicator handling
- [ ] visualization/result schema

---

## Product completion guardrail

Never mark **Heart complete** when only Murmur AI is complete.

Consult the Heart Definition of Done in `PRD.md`.

## Six-step implementation progress: Heart inference

Step 3 inference code and the existing Heart WAV backend connection are implemented.
Activating Murmur remains dependent on a final model and matching recording-level
validation/selection evidence. Abdomen inference is step 4; broader app integration
and persistent worker lifecycle are step 5. No model training was performed.

## Six-step implementation progress: Abdomen inference

Phase 4 implements the bowel-activity window backend, final-package validation,
window timestamps/summary and both-organ shared worker registration. A005 remains
a research candidate; deployment needs corrected window evidence and explicit
model/gate selection. Phase 5 connects Abdomen upload/results in the existing app.
PRD bowel-event DSP and rate/pattern outputs remain separate implementation gaps.

## Six-step implementation progress: app integration

Phase 5 implements shared Heart/Abdomen upload, real main recording capture,
organ-specific results, playback and in-memory status history in the existing app.
Persistent Python lifecycle, correlation, deadlines and Windows tree cleanup are
implemented. Final model/evaluation packages remain an activation prerequisite;
physical BLE, native-mobile offline execution and Abdomen event DSP remain gaps.
Phase 6 completes integrated engineering verification and readiness handoff.
See `WebApp/docs/phase6-readiness.md`; this does not complete model eligibility,
physical BLE, native offline execution or the full Heart/Abdomen PRD.

## Wi-Fi streaming implementation progress

Protocol/gateway/browser decoding, live listening, sample-clock recording and
WAV export are implemented. ESP-IDF network source exists with an explicit PCM
producer interface. No capture driver or physical validation exists yet. Remaining
acceptance: hardware handoff, SDK build/flash, actual audio source, sustained stream
and measured listening latency. See WebApp/docs/device-streaming.md.

## Lung implementation progress — training held

Data acquisition/audit, preprocessing, authorized-only training commands,
evaluation/package checks and existing backend/UI integration are implemented.
Official test annotations remain sealed. Initial Linux EXP-L002 development
training completed with poor reported metrics; no candidate is approved. Seeded
training shuffling/known batch cardinality are now corrected in both trainers.
The feature cache is reusable. Next is a fresh development comparison, frozen final selection,
one-shot holdout decision and physical/mobile validation. See
AI-Pipeline/docs/lung_training.md.

Completed Linux EXP-L003 improves some development outputs but remains
ineligible. Read-only label/mask/weight diagnostics and explicit research WAV
temporal localization are now implemented. Next: run saved-prediction score and
onset/offset diagnostics on that Linux checkpoint, review annotation assumptions,
then predeclare controlled context/task/weight comparisons before more fitting.
The official test remains sealed. See AI-Pipeline/docs/lung_localization.md.
