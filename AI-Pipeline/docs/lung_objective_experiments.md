# Lung numerical and objective experiments — 2026-11-10

Completed status: L016/L017/L018 and all queue evidence checks finished on
2026-11-10. No candidate meets the research gate and no training is active from
this queue. See [completed deep review](lung_l016_l018_deep_review.md). Launch
PID/status notes below are historical evidence.

## Scope

User-authorized continuation of the L015 investigation. Implements opt-in
research corrections for the PRD Lung wheeze/rhonchi/crackle findings. Upstream:
the original immutable HF development cache and grouped fitting partitions.
Downstream: experiment artifacts and research diagnostics, not the WebApp worker
or a deployed package. No production response/schema, clinical interpretation,
source labels, feature cache or split changes. The PRD respiratory-phase and
measurement requirements remain in scope outside this temporary three-label head.

## Numerical verification

Manual clipping can zero gradients on confidently wrong predictions. v6 uses
public Keras binary cross-entropy on the Dense sigmoid output and multiplies by
the same positive-label weight factor. It retains independent sigmoid outputs,
binary unknown masks and per-window supervised-cell normalization. Tests cover
the actual model path at logits +/-30, masked-class zero gradients, finite
gradients for all trainable arrays, a logits reference and reload inference.
It does not replace multi-label outputs with softmax.

The parity investigation distinguishes historical numerical replay from model
serialization. The unchanged L015 model produces exactly identical scores after
reload and across two fresh processes for each of CPU and GPU when deterministic
ops are enabled and TF32 disabled. Both cross-process maximum differences are
zero on the frozen 16-window probe. Historical L015 saved scores still differ by
up to 0.0005514 under that explicit runtime; one sampled threshold decision
changes. This does not retroactively make historical strict parity pass, prove a
unique kernel cause, or establish equality across all possible machines.

v6 explicitly freezes `runtime={deterministic_ops:true, tf32:false}` for fitting
and scoring. L016 combines this numerical runtime boundary with stable BCE;
therefore its comparison with historical L015 is **not a one-factor estimate of
the BCE change alone**. The combined boundary is justified by the reproducible
gradient defect and the need for a reproducible numerical reference. L017 and
L018 each change one objective setting from their immediate control.

## Predeclared bounded queue

| Run | Immediate control | Change |
|---|---|---|
| EXP-L016-numerical-contract | L015 | Stable BCE plus explicit deterministic float32 runtime |
| EXP-L017-window-objective | L016 | Estimate positive weights from actual per-window objective mass |
| EXP-L018-supervised-windows | L017 | Exclude zero-supervision fitting windows only |

All preserve seed 42, HF source/date-group split, three canonical columns 2/3/5,
original all-class supervised TRAIN normalization scope, 269,315 parameters,
dilation 16, dropout 0.2, Adam LR 0.001, zero decay, no feature augmentation,
batch eight, maximum 50 epochs, val_loss patience eight and restored best weights.
Legacy v1-v5 policies retain their existing numerics, counts and runtime behavior.
v6 is research-only and is explicitly rejected by final-package fitting.

Weights retain the historical [.25, 20] bounds. For L017, positive/negative
mass is computed per fitting window using the same total masked-cell denominator
as the loss; the ratio is then aggregated over the fitting partition only.
Mask-zero cells never become negative targets. L016's global-frame weights
reproduce L015's selected class weights. Counts/weights/fitting filenames are
saved before fitting in each fold's `objective.json` and summary events.

L018 removes 3,128 empty TRAIN windows from the original 28,620, giving 25,492
fitting windows and 3,187 batches/epoch instead of 3,578. These counts are
expected from the frozen audit and are remeasured at launch. The full 17,688
validation windows and their prediction order remain unchanged, including empty
ones; validation loss remains comparable within the new weighted objective.
Raw losses across different class weights or fitting populations are not direct
performance comparisons. A later best epoch, smaller loss or fewer steps does
not by itself establish improvement.

Threshold selection retains maximum-F1 per class on the existing internal
development population, grid .05 through .95 (37 points), lowest-threshold tie.
The original HF official test remains sealed. This bounded protocol permits
these three predeclared internal-development comparisons, not unlimited adaptive
tuning or external-validation selection. There is no automatic promotion or
fourth run. Future broader research selection should use TRAIN-only grouped CV.

The review gate, relative to L015, is stored in `configs/lung_objective_queue.json`:
macro PR-AUC improvement >=.01, no class PR-AUC drop >.01, crackle ROC-AUC >=.60,
crackle specificity >=.10 and no class sensitivity drop >.02 at the declared
threshold rule. These are modest research review criteria, not clinical standards
or deployment eligibility. Queue comparisons report each immediate control;
the L015 gate is a subsequent artifact review, not automated model activation.

## Automatic evidence and fail behavior

Each completed run saves complete per-class confusion counts, sensitivity,
specificity, precision, F1, ROC/PR-AUC, accuracy/balanced accuracy, threshold and
support; localization uses the existing frozen decoder. Additional pipeline
reports include fixed-threshold device/date-group metrics, TRAIN-derived
device-only nuisance ranking, target/normalization audits and deterministic
TRAIN/validation diagnostic subsamples. Group/frame metrics do not establish
independent-patient validation; shifted dates remain an imperfect grouping proxy.

After fitting, a fresh GPU process must pass strict same-runtime historical-score
and reload parity at atol/rtol 1e-4. Failure preserves the run/reports and stops
the queue before the next comparison. Prior experiment directories are never
overwritten. Missing GPU or unsupported fitting-class support also stops execution.
The existing source-confounding/annotation/representation limitations remain;
these changes do not guarantee an accuracy increase or solve dataset diversity.

## Verification and paths

- Full suite: **148 passed**, zero skips, 271 dependency deprecation warnings,
  17.90 seconds in WSL/TensorFlow 2.21.0.
- All three real-cache preflights pass 46,308 development windows without fitting.
- Actual RTX 5060 check: output [2,309,3], all ten gradient arrays finite,
  exact reload parity, zero optimizer steps, 3,072 MiB memory cap.
- Evidence: `artifacts/lung-launch/objective-checks-20261110/` including
  `full-tests.log`, three `preflight-*.json`, `parity-summary.json` and
  `actual-gpu-check.json`.
- Frozen code/config/test snapshot:
  `/home/vinend/auriscore-lung-runs/EXP-L016-20261110`.
- Queue plan: `configs/lung_objective_queue.json`.
- Output: `results/EXP-L016-numerical-contract/`,
  `results/EXP-L017-window-objective/`, `results/EXP-L018-supervised-windows/`.
- Queue protocol/status/logs:
  `artifacts/lung-launch/EXP-L016-20261110/queue/`.

Training is launched as a standalone GPU queue after these checks. Report its
PID and log locations, then stop active polling. No model is activated and no
performance gain is claimed at launch.

Launch observed: WSL supervisor PID **19198**, L016 trainer PID **19217**;
queue status is `running` with `EXP-L016-numerical-contract` active. The frozen
`queue/protocol.json` was written before the trainer launch. L017/L018 remain
queued and require prior run completion plus successful automatic evidence.
