# L015 pipeline investigation — 2026-11-10

## Scope and conclusion

Investigates the completed three-acoustic-label development run, not a production
model change or a new fitting experiment. Serves the PRD Lung acoustic-findings
requirement: wheeze, rhonchi and crackle. Input is the frozen HF development cache;
output is research diagnostics for the next protocol. No interface, clinical
claim, source split, training policy, cache, threshold or model weight changes.
The PRD phase requirements remain required outside this temporary research head.

The repeated early optimum is consistent with poor generalization and source
confounding, especially for crackle. It is not evidence of an epoch counter bug.
There are also reproducible loss-objective/numerical weaknesses. The evidence
does **not** establish a single causal root cause or show that fixing loss
numerics alone will improve held-out performance. More epochs are not a remedy
demonstrated by these results.

## Frozen run and evidence

- Run: `results/EXP-L015-three-sound/`; completed at epoch 10, best epoch 2.
- TRAIN: 28,620 windows / 94 shifted-date groups. Validation: 17,688 windows /
  24 groups. Patient independence is unverified. Five-second overlapping windows
  and frame metrics are not independent clinical samples.
- Best validation loss: 1.000534; final validation loss: 1.377519. TRAIN loss
  decreases from 0.829199 to 0.469606. LR remains 0.001. Patience eight explains
  stopping at epoch ten after best epoch two; it does not explain the degradation.
- Audit: `artifacts/lung-launch/L015-investigation-20261110/analysis/report.json`.
  Includes cache/audit/model SHA-256, counts, normalization, gradients and scores.
- Inference/weight check:
  `artifacts/lung-launch/L015-investigation-20261110/roundtrip.json`.
- Saved diagnostic samples: `analysis/train-sample.csv` and
  `analysis/validation-sample.csv` under the same artifact directory.
- Reproduce with `scripts/investigate_lung_pipeline.py --cache CACHE --audit AUDIT
  --experiment results/EXP-L015-three-sound --output FRESH_DIRECTORY` in the
  GPU-enabled TensorFlow environment. This audits/inferences only; no fitting.

## 1. Source and label distribution shift

Masked frame prevalence differs between TRAIN and validation:

| Population | Wheeze | Rhonchi | Crackle |
|---|---:|---:|---:|
| TRAIN overall | 14.52% | 10.03% | 28.70% |
| Validation overall | 16.69% | 4.58% | 35.90% |
| TRAIN steth | 17.27% | 11.67% | 26.72% |
| Validation steth | 21.76% | 11.50% | 30.88% |
| TRAIN trunc | 10.86% | 7.88% | 31.31% |
| Validation trunc | 13.90% | 0.88% | 38.54% |

The steth window share also falls from 50.13% to 29.27%. These differences
are not justification to reshuffle validation until it looks easier. Date-group
boundaries remain frozen; new grouped development evaluation must be predeclared.

A nuisance baseline assigns each frame its device's **TRAIN-only** positive
prevalence, without using audio or fitting on validation. It is evaluated on
exactly the CNN's masked validation frames:

| Class | CNN ROC-AUC | Device-only ROC-AUC | CNN PR-AUC | Device-only PR-AUC |
|---|---:|---:|---:|---:|
| Wheeze | 0.8152 | 0.5647 | 0.5135 | 0.1904 |
| Rhonchi | 0.8252 | 0.7756 | 0.1770 | 0.1063 |
| Crackle | 0.5458 | 0.5376 | 0.3737 | 0.3776 |

Crackle's audio model does not beat the device-only baseline on PR-AUC. This
supports concern about source confounding/weak transferable acoustic learning;
it does not prove that every CNN prediction relies on device identity. No
confidence intervals or independent-patient significance claim is made.

## 2. TRAIN-to-validation generalization gap

Inference-only diagnostic subsamples use seed 42, one random window per recording,
up to 64 recordings per device: 128 TRAIN and 128 validation windows. These are
**not** full-population metrics and have differing prevalence. ROC-AUC:

| Class | TRAIN sample | Validation sample |
|---|---:|---:|
| Wheeze | 0.8991 | 0.8571 |
| Rhonchi | 0.9201 | 0.8913 |
| Crackle | 0.8368 | 0.6251 |

Together with falling TRAIN loss and rising validation loss, this supports
overfitting/distribution-shift concerns. It does not distinguish their separate
causal contributions. Earlier lower-LR, regularization and compact-model runs did
not eliminate the pattern; simply increasing patience is unsupported.

At the frozen development max-F1 thresholds [0.65, 0.80, 0.05], full validation:

| Class | Sensitivity | Specificity | Precision | F1 | TP / FP / FN / TN |
|---|---:|---:|---:|---:|---|
| Wheeze | 0.5978 | 0.8496 | 0.4432 | 0.5091 | 177423 / 222856 / 119347 / 1258499 |
| Rhonchi | 0.4857 | 0.9013 | 0.1911 | 0.2743 | 38257 / 161907 / 40514 / 1478512 |
| Crackle | 0.9700 | 0.0567 | 0.3654 | 0.5309 | 609625 / 1058539 / 18880 / 63681 |

Crackle's F1 hides extremely poor specificity: nearly every negative frame is
flagged. This is not an acceptable acoustic screening candidate.

## 3. Loss weighting and empty supervision

The loss normalizes each window by its own supervised frame/class count, but
positive weights are computed from global frame counts. These are different
weighting measures. The analytic constant-score optimum on TRAIN is
[0.56956, 0.51160, 0.48533], rather than the frame-balanced [0.5, 0.5, 0.5].
This is a confirmed objective mismatch if class balancing is intended; its
magnitude does not explain crackle's near-chance ranking by itself. An alternative
weight estimator must follow the selected reduction and be independently tested.

3,128 TRAIN windows (10.93%) and 1,609 validation windows (9.10%) have no supervised
targets after selecting these three classes. They contribute zero loss while
remaining in the batch/epoch mean. They are not negative labels. Their presence
dilutes loss averages and makes epoch counts a weak progress measure. A future
policy may exclude empty TRAIN windows, with exact cardinality and provenance;
full validation prediction/index coverage must remain intact. This audit does
not change the window population or retroactively rescale historical losses.

## 4. Confirmed numerical defect, unproven causal importance

Manual probability clipping before log loss gives zero gradients for confidently
wrong extreme examples. Synthetic logits [30, -30] with targets [0, 1] and
positive weight six yield gradients [0, 0]. Public Keras stable BCE and a logits
reference both yield [1, -6]. The moderate-logit gradient agrees between methods.
Three focused tests pass, including mask semantics and reduction/weight mismatch.

However, the saved best checkpoint has **zero wrong saturated validation frames**
for all three labels at the existing clipping boundaries. Therefore this defect
cannot be presented as the demonstrated cause of its epoch-two optimum. Later
epoch prediction arrays were not retained, so later saturation is unknown.

Any stable-BCE change must be opt-in/versioned, preserve legacy reproducibility,
retain masks/positive weights/reduction, and be tested through the actual Dense
sigmoid model path against a logits reference before a one-factor comparison.

## 5. Checks and limitations

- All 46,308 development windows pass unchanged provenance/split preflight;
  group and source hashes do not cross TRAIN/validation. This does not prove
  patient independence or absence of all acoustic duplicates.
- Normalization clipping affects at most 0.000403% of physical feature cells per
  device/split. Within-device normalized means are similar between splits. No
  evidence of catastrophic validation clipping was found; this is not proof
  that the feature representation is optimal for crackle.
- All ten layer-weight arrays in saved `model.keras` are exactly equal to
  `best.weights.h5`. Optimizer state is deliberately not compared.
- Reloaded inference on 16 validation windows is repeatable within that process,
  but strict saved-score parity at atol/rtol 1e-4 fails: max difference 0.00012337,
  mean absolute difference 0.000000326; zero sampled threshold decisions change.
  A batch-16 comparison differs by up to 0.00096622. Kernel/runtime numerical
  variation is a hypothesis, not established cause. Exact inference parity is an
  open verification item; no tolerance was loosened to declare a pass.
- Earlier mechanical alignment checks and user listening review found no clear
  annotation issue. This does not validate every annotation. In particular,
  source crackle annotations denote intervals containing crackles, not individual
  crackle clicks; frame-localization interpretation remains limited.

## Next implementation order

1. Add a versioned stable loss with actual-model extreme-logit gradient tests;
   resolve strict reload parity and freeze numerical/runtime provenance.
2. Predeclare the training objective (window-balanced vs frame-balanced), align
   its TRAIN-only class weights, and handle empty supervision explicitly. Test
   mask invariance, gradients, reduction and cardinality. Isolate this from the
   numerical-loss comparison rather than changing everything in one run.
3. Add device-stratified and group-level diagnostics plus the frozen nuisance
   baseline to future development reports. Use TRAIN-only grouped CV for research
   selection; do not repeatedly tune on this validation or alter the sealed test.
4. Audit crackle representation/interval supervision on TRAIN examples; acquire
   additional source-diverse crackle/rhonchi data only with compatible annotations,
   patient/source exclusion and a frozen mapping protocol. Raw window quantity
   alone is not the demonstrated shortage.
5. Launch a new immutable experiment only after its policy and comparison gate
   are frozen. Require ranking/false-positive improvements over L015 and nuisance
   baselines; a later best epoch alone is not success. No launch in this audit.

No official test labels were opened, no thresholds were reselected, no optimizer
steps were taken and the audited model SHA-256 is unchanged. No model is activated.
