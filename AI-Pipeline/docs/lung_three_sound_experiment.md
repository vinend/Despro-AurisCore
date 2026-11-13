# L015 — wheeze, rhonchi and crackle only

Date: 2026-11-10. Explicit user request to temporarily train only these three
acoustic labels. This is research scope, not deletion of the PRD's respiratory
phase/measurement requirements or a change to production result schemas.

## Controlled comparison

ID: `EXP-L015-three-sound`. Control: `EXP-L011-sound-only`.
The sole declared task change removes stridor from the four-sound training head.
The canonical cache order is preserved: wheeze, rhonchi, crackle (columns 2, 3, 5).
Each output is an independent sigmoid; wheeze and crackle may coexist. There is
no extra Normal class or forced softmax choice. Missing/unannotated source labels
retain their existing masks; excluding a class does not label its recordings as
clinically normal.

L011 is used instead of compact L014 to avoid changing task and architecture
simultaneously, and because its PR-AUC is higher for each of these three classes.
HF-only data is retained rather than mixing another source change into this run.
The architecture has 269,315 parameters and emits 309 frames x three scores.
The time dimension and source timestamps are unchanged.

Frozen settings: seed 42, dilation 16, dropout 0.2, LR 0.001, Adam with zero weight
decay, no feature augmentation, batch eight, maximum 50 epochs. Early stopping
monitors val_loss with patience eight and restores best weights. All prior
experiments remain intact. The reviewed source/audio and original feature cache,
TRAIN normalization rule, class counts and date-group split remain unchanged.
Normalization uses the same original TRAIN scope; weights/targets/masks are
projected onto the requested outputs only.

Thresholds use the existing maximum-F1 development rule (37 points, 0.05..0.95,
lowest tie). Compare matching-class sensitivity, specificity, precision, F1,
ROC/PR-AUC, accuracy/balanced accuracy, confusion counts, support, thresholds and
one-to-one localization at frozen decoder settings. Raw loss from a three-output
head is not directly comparable with the four-output loss denominator. A later
best epoch alone is not success, and no improvement is guaranteed at launch.

## Verification and artifacts

- 135 complete Lung/source tests pass, no skips, 231 dependency deprecation
  warnings, 17.18 s under WSL/TensorFlow.
- New checks verify the one-factor policy difference, correct source column
  projection, independent sigmoid head, 309 x 3 output, parameter count and actual
  trainer wiring without fitting test weights.
- HF preflight passes all 46,308 cached development windows with the selected
  three-class policy. Fitting is 28,620 windows / 94 date groups; validation is
  17,688 windows / 24 date groups. These are not verified independent patients.
- Policy: `configs/lung_training_three_sound.json`.
- Frozen single-run queue: `configs/lung_three_sound_queue.json`.
- Test/preflight evidence: `artifacts/lung-launch/three-sound-checks-20261110/`.
- Code snapshot: `/home/vinend/auriscore-lung-runs/EXP-L015-20261110`.
- GPU queue supervisor launched as WSL PID **14888**.
- Results: `results/EXP-L015-three-sound/`.
- Protocol/status/log/automatic diagnostics/comparison:
  `artifacts/lung-launch/EXP-L015-20261110/queue/`.

Official test remains sealed; no model is activated. The three-class head remains
research-only until a separate final-package/evaluation contract is selected.
Performance, rare-class robustness and reliable localization remain pending.
Active agent polling stops after the initial startup verification.

## Completed result and investigation

L015 completed at epoch 10, restoring epoch 2 (validation loss 1.000534).
Three-label training did not resolve the early optimum. Full validation PR-AUC
is 0.5135 / 0.1770 / 0.3737 for wheeze / rhonchi / crackle; crackle specificity
is only 0.0567 at its frozen maximum-F1 threshold. No candidate is activated.
See [pipeline investigation](lung_l015_pipeline_investigation.md) for measured
source shift, nuisance baselines, loss weaknesses and ordered implementation work.
