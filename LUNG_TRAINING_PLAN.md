# Lung training implementation plan — HF_Lung_V1

Date: 2026-10-10. Status: software implemented; development training authorized.
The initial EXP-L001 launch stopped during preparation; preserve it and start a
fresh experiment when retrying. The user subsequently completed Linux EXP-L002;
its development candidate remains research-only. Training input order/cardinality
are corrected for a fresh comparison; existing feature caches remain reusable.
This document authorizes no training launch or deployment. It addresses PRD
section 7 using one dataset and the existing AI-Pipeline infrastructure.

## Objective and boundaries

Build reproducible Lung training for abnormal acoustic events and respiratory
phases. Event outputs are wheeze, crackle and rhonchi presence/timestamps where
the released labels support them. Phase outputs are inhalation/exhalation
intervals, with respiratory rate, durations and I:E ratio only when sufficient
complete cycles and signal quality support calculation. These are acoustic
screening outputs, not disease diagnoses.

Preserve Heart/Abdomen code, frozen research artifacts and evaluation boundaries.
Reuse mono/resampling, spectrogram utilities and training lifecycle where suitable;
do not relabel Murmur training or overwrite its experiment/model files.
HTTP/UI now support Heart, Abdomen and Lung. Lung returns unavailable until a
verified final model package is explicitly selected.

## Dataset and unresolved acquisition details

- Official repository: https://gitlab.com/techsupportHF/HF_Lung_V1
- Official documentation:
  https://gitlab.com/techsupportHF/HF_Lung_V1/-/raw/master/README.md
- Original study: https://doi.org/10.1371/journal.pone.0254134
- Published release: 9,765 nominal 15-second WAV recordings, 4 kHz/16-bit audio,
  TXT labels, original training/test folders, CC BY 4.0 attribution terms.
- Documentation describes inhalation, exhalation, continuous adventitious sounds
  (wheeze/rhonchi/stridor) and discontinuous sounds (crackles).
- Audit actual label files before promising subtype supervision: verify exact
  syntax, time units, per-event subtype availability and annotation completeness.
  If the release exposes only CAS/DAS categories, train those categories and leave
  specific unsupported subtypes unavailable; do not infer rhonchi from CAS alone.
- Labels were produced by a single annotator. Recording dates are shifted;
  same-date files are recommended as a grouping proxy, not verified patient IDs.
- The release notes identify corrected filenames and one zero-padded recording.
  Record padding/quality findings; do not treat artificial tails as labeled audio.
- Actual accessible archive URLs, release revision, checksums, bytes, required disk
  space and label distribution must be established during phase 1.

## Phase 1 — Acquisition, annotation audit and leakage-safe manifests

Implement `acquisition_lung.py`, `dataset_lung.py`,
`scripts/download_lung_dataset.py` and `scripts/build_lung_manifest.py`.

1. Pin repository revision/archive identities and save attribution/license metadata.
   Download to ignored `data/external/hf-lung-v1/`; use verified HTTPS, resumable
   transfers and safe multipart 7z extraction. Keep original files immutable and out of Git.
2. Inventory WAV/TXT pairs. Inspect rate, channels, duration, clipping, silence,
   malformed audio and missing labels; compute content hashes.
3. Parse labels verbatim into an event table with recording ID, original label,
   start/end seconds, source file and validity. Validate finite ordered bounds,
   recording duration, time units and overlaps. Unknown/missing annotations are
   not negative examples. Do not export private source metadata unnecessarily.
4. Build a recording manifest containing source/version, original split, device,
   known location, sample rate, valid duration, hashes, quality and grouping key.
   Never infer Littmann recording locations from file order.
5. Audit official train/test group overlap and duplicate recordings before fitting.
   Keep all channels, truncations and windows from a source session/date together;
   use real subject IDs if supplied. Check exact hashes and candidate near-duplicates.
6. Preserve the official test role. Split official training groups into development
   folds; seal test labels from training/model selection. If overlap exists, use a
   documented disjoint evaluation subset or quarantine conflicting training groups.
   Report resulting counts and comparison limits rather than silently moving test
   examples into training. Date grouping cannot establish patient independence.

Deliverables: source receipt, recording/event manifests, label ontology,
quality report, immutable split assignment and leakage audit.
Exit: label mapping and split policy are supported by the released files.

## Phase 2 — Lung preprocessing, tensors and aligned targets

Implement `lung_preprocessing.py`, `scripts/preprocess_lung_dataset.py`,
`configs/lung_baseline.yaml` and `configs/lung_cnn.yaml`.

- Resample explicitly from source rate to the product's 8 kHz mono input. Upsampling
  4 kHz does not recover frequencies above the original 2 kHz Nyquist limit.
- Start with the existing configurable log-mel path: 96 mel bins, FFT 512,
  hop 128, five-second windows and 50% overlap. Treat these as baseline parameters,
  not optimal settings. Examine short crackle resolution on development data.
- Define a source-compatible feature band with its upper bound below 2 kHz;
  proposed first configuration 20–1900 Hz. Keep filtering disabled initially,
  then evaluate any filtering change as a separate development experiment.
- Fit per-frequency normalization using only each fold's training partition.
  Include all feature/label/split settings in cache keys and model metadata.
- Construct frame-wise multi-label targets by interval overlap. Wheeze, crackle,
  rhonchi and respiratory phases can overlap; do not force a mutually exclusive
  single class. Retain stridor if reliably labeled rather than treating it as normal.
- Mask padding, unlabeled/ambiguous regions and invalid tails from loss/metrics.
  Background can mean no target event only where annotation coverage supports it;
  absence of an event label does not mean a healthy patient.
- Define and version frame alignment, event occupancy and boundary rules. Include
  final partial windows with masks so end-of-recording events are not lost.
- Apply augmentation only to training. Begin with modest gain/noise variations;
  time shifts must shift targets identically. Avoid time stretching and ordinary
  classification MixUp/CutMix until phase/event target handling is validated.

Deliverables: deterministic tensors, target/mask arrays, development previews,
train-only normalization and preprocessing/target configuration.
Exit: source timestamps round-trip correctly and padding never becomes supervision.

## Phase 3 — Lung baseline models and reproducible training

Implement `lung_models.py`, `lung_training.py`, `scripts/train_lung_cnn.py`,
and a separate Lung experiment queue/status path (`EXP-L001-*` onwards).

Use two independently versioned tasks, allowing either to remain unavailable:

1. Acoustic events: a compact CNN baseline for window-level presence, followed
   by a CNN with temporal output for event localization. Output one sigmoid per
   supported sound class; derive window targets only from verified coverage.
2. Respiratory phases: a compact temporal CNN or CNN-GRU predicting inhalation
   and exhalation per frame. Include masking and overlap policy; no synthetic
   phase labels derived from sound amplitude alone.

Reuse generic training infrastructure after testing its interfaces. Existing
`cnn.py` has a Murmur-specific single-output head and binary metrics; Lung needs
its own heads, masked losses, aggregation and evaluation rather than a config-only
rename. Use training-only class weights; publish class and group counts.

Before a long run, finalize the experiment protocol, development split, metrics,
selection rules, resource preflight and recovery behavior. First run a synthetic
smoke test plus a small TRAIN-only real-data overfit check. A later authorized
launch runs as a standalone process/queue with PID, logs and result paths, not
continuous agent polling. Do not launch training as part of writing this plan.

Deliverables: reproducible configs/seeds, checkpoints, histories, model metadata,
runtime reports and development predictions, without modifying Heart artifacts.
Exit: both task trainers execute correctly and preserve split/target masks.

## Phase 4 — Evaluation and candidate selection

Implement `lung_evaluation.py` and `scripts/evaluate_lung_development.py`.

- Use grouped TRAIN-only CV/OOF to select model, event thresholds, smoothing,
  minimum duration and merge-gap rules. Fit learned preprocessing fold-locally.
- Event metrics: per-class sensitivity, precision, specificity and PR-AUC where
  applicable; macro summaries; event-based F1 with a predeclared onset/offset
  tolerance. Define event matching one-to-one and how false positives are counted.
- Phase metrics: frame-wise F1, event/boundary matching and duration error.
  For recordings supporting reliable complete cycles, compare respiratory-rate
  error and I:E ratio against values derived from verified annotations.
- Report uncertainty at the available independent-group level, device/source
  stratification and sample support. Group/date estimates are not patient-level
  validation. Include noise, short clips, rare classes and quality failures.
- Predeclare Lung-specific eligibility thresholds before experiments. Do not copy
  the Heart 90% sensitivity gate or invent clinical performance requirements.
  Engineering correctness gates can pass while the model remains research-only.
- Freeze selected checkpoints, thresholds, postprocessing and configuration before
  one locked official-test evaluation. Never use test results for iterative tuning.
  HF's official test is an internal dataset benchmark, not an independent device
  or clinical validation cohort. Real ESP32 audio remains a separate future test.

Deliverables: OOF predictions, per-task metrics, error analysis, selected candidate
and a written eligibility decision with unsupported outputs explicitly identified.
Exit: selection is reproducible; sealed evaluation is only opened under its protocol.

## Phase 5 — Frozen package, inference and respiratory measurements

Implement `lung_inference.py`, `lung_dsp.py` and
`scripts/prepare_lung_deployment.py`; document proposed `lung-analysis-v1`.

- Package verified model(s), supported label ontology, hashes, exact preprocessing,
  normalization, thresholds, postprocessing, provenance and selection evidence.
  Missing/invalid/unapproved components return unavailable, never fake findings.
- Inference uses overlapping windows with a deterministic timestamp-based merge
  policy; avoid duplicate events and inconsistent edge probabilities.
- Derive candidate complete cycles from detected phases, reject ambiguous pairs,
  and calculate respiratory rate from supported cycle intervals. Exclude truncated
  edge phases from duration/I:E calculations. Return null with a reason when
  quality, cycle count or coverage is insufficient.
- Proposed result includes quality/status, supported sound probabilities/events,
  phase intervals, respiratory metrics, valid coverage, algorithm/model versions
  and explicit per-branch availability. No disease classification is introduced.
- Verify saved-model reload and training/inference tensor parity. Evaluate TFLite
  export and INT8 using TRAIN-only representative data; check per-class and timing
  regressions and benchmark resources before calling mobile inference ready.

Deliverables: independently verified package and Python recorded-audio adapter.
Exit: deterministic parity, bounded runtime and correct unavailable/invalid states.

## Phase 6 — Existing backend/app integration and acceptance

Extend existing `AnalysisService` and retained Python worker with Lung registration;
update shared mode validation, policy and client types. Reuse `/api/analysis`
with `mode=lung`, adding a fixed Lung endpoint only if useful. Preserve legacy
Heart responses and verify whether envelope versioning is needed before changing it.

Add Lung selection, WAV upload, recording results and event/phase visualizations to
the existing WebApp. The 8 kHz Wi-Fi transport remains organ-independent; no
firmware pin or packet changes are needed merely to select Lung.

Keep short/poor captures explicit; ten seconds may be insufficient for robust
respiratory measurements. Validate duration requirements and allow a longer
bounded Lung capture if supported by all recording/API limits. Do not fabricate
rate/I:E values from too few cycles. Native offline mobile remains a separate gap.

Acceptance tests cover WAV/PCM parity, each branch's partial/unavailable state,
malformed packages, silence/noise, overlapping events, padding, continuity loss,
worker correlation/cancellation and Heart/Abdomen regression. Verify the real HTTP
and browser recording path with an eligible package or clearly marked test fixture.
Physical ESP32 audio and clinical validation remain distinct acceptance stages.

Deliverables: updated contracts/docs, integrated tests and a readiness report.
Exit: complete software flow is verified and remaining model/hardware gaps stated.

## Implementation order and immediate next action

Execute phases sequentially. Start phase 1 with acquisition tooling and a small
released TRAIN annotation/audio sample audit; establish label semantics and
grouping before building target arrays or starting experiments. A full download
must preserve official test boundaries and source attribution.

Implementation handoff: both official splits are downloaded and inventoried;
development preprocessing is separate from model fitting. Acquisition, labels,
temporal targets, guarded development/final training, evaluation, package checks,
Python worker integration and Lung UI are implemented. Initial Linux development
training completed; official-test evaluation has not run and no Lung model is
promoted. The dataset input correction was tested without fitting model weights.

The first runnable baseline shares one temporal CNN with independent sigmoid
outputs for both tasks; class subsets permit separate experiment versions.
Filtering/augmentation are disabled initially. Pooled/GRU comparisons, uncertainty
reports, TFLite benchmarking and model eligibility decisions require subsequent
authorized experiments. See AI-Pipeline/docs/lung_training.md for current audited
counts, exact commands, limits and authorization boundaries.
