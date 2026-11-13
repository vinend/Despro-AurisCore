# Compact Lung models — L013 / L014

Date: 2026-11-10. User-authorized implementation and GPU development fitting.
PRD section 7; research-only, with no application schema, clinical claim or
official-test-role changes.

## Evidence before fitting

Completed L010/L011 saved development predictions selected a bounded review set:
phase conflicts/fragmentation, crackle false positives, and rhonchi/stridor misses.
Selection takes the highest review cue per HF device and varies date groups
where possible. This is a deliberately difficult review set, not an unbiased
error-rate estimate. Unknown labels and genuine reference I/E overlap are excluded
from the respective false-error counts. No labels are changed automatically.

Ten development recordings / 60 windows were reprocessed from audited source
audio and annotations: features, targets, masks and timestamps match the original
cache with zero mismatches. The source/cache report initially records a pending
listening review; the user subsequently confirmed listening and no obvious
annotation problem. Confirmation is recorded separately in the launch's
`authorization.json`. This is not independent expert validation of all labels.

The listenable HTML displays REF annotation lanes and saved PRED intervals for
both separate models on the same seconds axis:
`artifacts/lung-launch/compact-error-review-20261110/review.html`.
Cases and mechanical evidence are in the same ignored directory.

## One declared architecture change per comparison

The previous model flattens the remaining frequency positions to 768 features
before a five-wide, 64-output temporal convolution. A learned pointwise Conv1D
now optionally projects these 768 frequency features to 64 channels, with ReLU,
before the existing temporal convolution. This tests whether excessive capacity
contributes to memorization. It may also discard useful spectral information;
better accuracy or later best epochs are hypotheses, not established outcomes.

| Run | Matching control | Model parameters | Time/class output |
| --- | --- | ---: | --- |
| L010 phase control | — | 269,250 | 309 frames x 2 classes |
| L013 compact phase | L010 | 93,186 | unchanged |
| L011 sound control | — | 269,380 | 309 frames x 4 classes |
| L014 compact sound | L011 | 93,316 | unchanged |

Parameter count falls by about 65%. The pointwise layer adds no temporal span:
theoretical context remains 71 feature frames / 1.184 s with symmetric padding.
Mel bins, feature geometry, physical padding, annotation overlap and all class
validity masks remain unchanged. Existing policies create the original model
without the bottleneck; the extension is opt-in `lung-training-policy-v5`.

Versioned policies are `configs/lung_training_compact_phase.json` and
`configs/lung_training_compact_sound.json`. Each preserves HF-only data, TRAIN-only
normalization/class weights, seed 42, LR 0.001, dropout 0.2, dilation 16, batch
eight, maximum 50 epochs, zero weight decay and no feature augmentation.
Early stopping remains val_loss/patience eight/restored best weights. Increasing
patience or changing the monitored metric mid-run is not part of the experiment.

## Frozen selection and comparisons

Each run uses a fresh experiment directory and a separate single-run queue plan
with its actual control (L010 or L011). The queue verifies identical audited
cache/config, freezes code/policy/package/control hashes before fitting, and
saves normal histories/checkpoints/predictions/metrics. Per-class comparison
requires matching validation groups and class support. Generic delta fields
now name the correct baseline; existing L006 consumers retain their legacy alias.

After each run, saved-score diagnostics and the frozen unsmoothed v2 localization
evaluation are saved without changing thresholds. Threshold selection remains
the declared per-class maximum-F1 development grid (0.05..0.95, 37 points,
lowest tie). Review sensitivity, specificity, precision, accuracy/balanced
accuracy, F1, ROC/PR-AUC, confusion counts, threshold, support, phase conflict,
event matching and respiratory-result availability. More epochs alone is not
acceptance. A promising direction still needs seed/grouped-fold confirmation.

Subset heads remain research-only and cannot silently become final inference
packages. Official test, original caches/experiments, Heart/Abdomen and the
existing worker/API remain unchanged. No automatic deployment promotion occurs.

## Verification and launch checkpoint

- Complete Lung/source suite: **132 passed**, no skips, 221 dependency
  deprecation warnings, 14.48 s under WSL/TensorFlow.
- Tests cover strict v5 configuration, legacy model preservation, shape and
  parameter counts, Keras save/load parity, masked review cues, matching baseline
  identity and actual compact trainer wiring without fitting weights.
- Both compact models passed finite forward/backward on RTX 5060 GPU:0 with
  zero optimizer steps and synthetic inputs only.
- User confirmation of the ten-case listening review was received before launch.
- Launched approximately 12:30 WIB on 2026-11-10 as WSL supervisor PID **11139**.
  L013 is active; L014 is scheduled after it. Startup passed the original
  46,308-window preflight and reached TRAIN statistics with GPU active.
- Fitting population: 28,620 windows / 94 date groups; validation: 17,688 windows /
  24 date groups. These groups are not verified patient identities.
- No completed L013/L014 metrics exist at launch; active polling stops here.

Code snapshot: `/home/vinend/auriscore-lung-runs/EXP-L013-L014-20261110`.
Results: `results/EXP-L013-compact-phase` and `results/EXP-L014-compact-sound`.
Supervisor status/authorization/log:
`artifacts/lung-launch/EXP-L013-L014-20261110/`.
Per-run queue status/protocol/log/analyses: its `phase/` and `sound/` directories.
Test/GPU evidence: `artifacts/lung-launch/compact-checks-20261110/`.

Known gaps: sampled review does not establish annotation completeness; independent
patient/generalization validity, reliable phase boundaries, sufficient rare-class
data and deployment eligibility remain unproven. Neither compactness nor this
launch establishes that early degradation has been fixed.
