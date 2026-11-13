# Lung next experiments after L006–L012

Planning checkpoint: 2026-11-10. Following explicit user authorization, the bounded
error review, compact-model implementation and tests are complete. The user
confirmed the new listening review. L013/L014 are now launched serially on GPU
(WSL supervisor PID 11139; L013 active at startup). The planning text below
records the original hypotheses. See [implementation/launch evidence](lung_compact_experiments.md).

## Objective and scope

Serve PRD section 7 respiratory phases/acoustic findings. Upstream inputs are
audited HF development tensors and completed research predictions; downstream
consumers are research comparisons and a later separately frozen inference
candidate. Keep the production API, test roles and clinical claims unchanged.
Do not accept extra epochs as evidence of better generalization.

The working repository is Despro-AurisCore-Latest, master at 0db6d0d. A fresh
fetch found no difference from origin/master. Local research changes remain
uncommitted. Completed runs used immutable WSL code snapshots copied from this
working tree; results and launch provenance are stored in its AI-Pipeline folder.

## What is now known

All five L007–L011 probes completed. L006–L012 all selected epoch two and stopped
after eight stale epochs. At batch eight this already represents more than
7,000 optimizer updates for the full HF fitting set; epoch two is not inherently
an invalid checkpoint. The concern is weak held-out discrimination/localization
and the subsequent loss divergence, not the numerical epoch index.

| Matched task | Joint L006 PR-AUC | Separate-head PR-AUC |
| --- | ---: | ---: |
| Inhalation | 0.8278 | L010 0.8705 |
| Exhalation | 0.5524 | L010 0.6390 |
| Wheeze | 0.4837 | L011 0.4976 |
| Rhonchi | 0.1770 | L011 0.1843 |
| Stridor | 0.0283 | L011 0.0242 |
| Crackle | 0.3571 | L011 0.3647 |

L010 reduces simultaneous phase predictions to 723,657 / 1,710,259 jointly valid
frames (42.31%), versus L006 59.33% and target overlap 1.08%. Its phase event F1
is still about 0.0024–0.0027 under the frozen unsmoothed decoder. Respiratory
measurements remain unavailable on the 2,948 evaluated records. Separate heads
are promising research controls, not deployment-ready product architecture.
No significance or verified patient-level claim follows from these single-seed
overlapping-frame development estimates.

## First: review the actual failure modes

Create a bounded review set spanning phase conflicts, phase boundaries, crackle
false positives and rare-class misses, stratified by HF device/date group.
Review original audio and source annotations together. Record whether each error
reflects annotation uncertainty, ambiguous negative supervision, signal quality,
boundary fragmentation or a plausible model error. Do not automatically shift
labels or turn unannotated audio into negatives. Keep TRAIN/inner-development
review separate from any outer-fold evaluation used for a future unbiased claim.

If the review identifies a systematic supervision problem, freeze a revised
mask/target protocol and version a fresh cache before more architecture fitting.
Do not silently modify the existing cache to improve its reported metrics.

## First controlled architecture comparisons

Proposed unused IDs L013/L014 must be checked again and protocol-locked before
launch. Each starts fresh and compares against the appropriate separate-head
control, using HF-only data to isolate architecture from source addition.

1. L013 phase compactness vs L010: test one explicit frequency-feature bottleneck
   before the existing temporal convolution. The current flatten-to-Conv1D path
   dominates model parameters; reducing its input width tests capacity/memorization
   without changing temporal labels or promising better performance.
2. L014 acoustic compactness vs L011: apply the same declared architecture change
   to the four-sound head. Preserve independent sigmoid semantics and coverage masks.

Freeze LR, dropout, dilation, class weights, normalization, seed, batch size,
maximum 50 epochs, val_loss monitor, patience eight and best-weight restoration.
Do not combine lower LR, new augmentation, changed supervision and compactness
in the same causal comparison. A narrower bottleneck may remove useful spectral
information; acceptance depends on matching-class ranking, sensitivity and event
behavior, not parameter count or later stopping alone.

## Conditional follow-ups

- If ranking/phase behavior remains weak with correct labels, compare weighted
  versus unweighted masked BCE as a separate declared study. Current TRAIN weights
  alter score interpretation; changing threshold alone cannot fix poor ranking.
- Review recording/group sampling and overlap redundancy. A one-crop-per-recording
  epoch changes the number of optimizer updates; compare equal update/audio
  exposure budgets so a later epoch is not a cosmetic improvement.
- If evidence supports a need for longer temporal context, predeclare a compact
  sequence-model comparison. Specify physical padding separately from unknown
  annotation masks; a five-second input does not imply full-window context today.
- Study minimum-duration/gap decoding separately with inner selection or grouped
  OOF. Preserve raw results and legitimate overlapping I/E annotations. Define
  an explicit overlap policy before introducing any exclusive phase head/rule.
- Expand genuinely independent rare-class annotations. The current SPR addition
  contains only one stridor event/patient and does not solve that support gap.

## Acceptance and evaluation boundary

Report per-class accuracy, balanced accuracy, sensitivity, specificity, precision,
F1, ROC/PR-AUC, confusion counts, threshold, support, score distributions and
always-positive baselines. Match masks/populations and use identical control
weights for checkpoint-loss comparisons. Report phase conflict, one-to-one event
matching and respiratory-metric availability, with device/date stratification.
Do not compensate for lost sensitivity with prettier F1 or accuracy alone.

Predeclare quantitative Lung-specific eligibility gates before final fitting;
do not copy Heart's engineering thresholds as clinical rules. Repeat a promising
direction across seeds/grouped folds before claiming generalization. Keep each
fold's normalization, weights and selection rules inside its permitted fitting
population. HF date groups still do not establish patient independence.

Only after a candidate is selected should final fitting, frozen decoder/thresholds,
separate locked evaluation, package eligibility and physical-device validation
proceed. Official test labels stay closed during these development decisions.
