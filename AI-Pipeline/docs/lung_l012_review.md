# Why L012 stopped at epoch ten — completed development review

Date: 2026-11-10. Read-only review of saved completed L006, L007, L008 and L012
development artifacts. No fitting, threshold reselection, official-test access
or inference activation occurred. This supports PRD section 7 research decisions;
it does not establish clinical performance.

## The stopping mechanism is working as configured

L012 allows 50 epochs. Its frozen EarlyStopping callback monitors val_loss in
min mode with patience eight and restores best weights. Validation loss reached
its minimum at epoch two, then failed to beat that minimum for epochs 3–10.
Thus best epoch 2 + eight stale epochs = stop at epoch 10. History CSV uses
zero-based indices 0–9; console/process events use epochs 1–10.

| Epoch | TRAIN loss | Validation loss |
| --- | ---: | ---: |
| 1 | 0.74539 | 0.88113 |
| 2, restored checkpoint | 0.61797 | 0.87615 |
| 3 | 0.56669 | 0.92520 |
| 10, stopping point | 0.43366 | 1.21198 |

The run and its post-fit analysis both completed successfully. There is no
evidence here of a ten-epoch hard limit, GPU failure or interrupted fitting.
The divergence is consistent with overfitting/increasingly poor held-out score
behavior. These histories alone cannot distinguish overconfidence, noisy labels,
domain shift and architecture/task interference. Only best-checkpoint predictions
were saved; later-epoch F1/ranking cannot be reconstructed from loss alone.

## Raw validation losses have different class weights

SPRSound addition changed the TRAIN-derived positive weights for acoustic classes:

| Class | L006 weight | L012 weight |
| --- | ---: | ---: |
| Inhalation | 0.59015 | 0.59015 |
| Exhalation | 1.46376 | 1.46376 |
| Wheeze | 5.887 | 6.52451 |
| Rhonchi | 8.969 | 10.07526 |
| Stridor | 20, clipped | 20, clipped |
| Crackle | 2.485 | 2.81157 |

Therefore 0.87615 versus 0.82691 is not a direct identical-objective comparison.
Using saved frame scores, masks and the actual per-window loss denominator, the
review reconstructed each best-checkpoint objective and evaluated all checkpoints
under the same L006 positive weights. Reconstruction differs from Keras' reported
best loss by less than 0.00004, consistent with numerical/execution differences.
This is analysis-only reweighting, not a new training or threshold decision.

| Run | Epochs / best | Recorded best val_loss | Best-checkpoint loss under L006 weights | Macro F1 | Macro PR-AUC |
| --- | --- | ---: | ---: | ---: | ---: |
| L006 control | 10 / 2 | 0.82691 | 0.82694 | 0.45751 | 0.40436 |
| L007 initial LR 0.0003 | 10 / 2 | 0.81478 | 0.81478 | 0.45756 | 0.40858 |
| L008 weight decay 0.0001 | 10 / 2 | 0.81142 | 0.81143 | 0.45255 | 0.40383 |
| L012 HF + SPRSound | 10 / 2 | 0.87615 | 0.84003 | 0.45668 | 0.39225 |

L012 remains worse on the common-weight checkpoint loss and macro PR-AUC.
Lower LR and weight decay at the tested values did not shift the best epoch.
L007 has a small macro PR-AUC improvement, while L008's lower loss does not
translate into better macro F1/PR-AUC. These single-seed development differences
have no independent-group confidence interval and are not significance claims.

## Same validation population, mixed per-class effects

Saved truth arrays, validity masks, class order and held-out date groups are
hash-identical across these four runs. All comparisons use 17,688 overlapping
HF validation windows from 24 date groups, not independent patients. Thresholds
are the original per-class maximum-F1 development selections; none were changed.

| Class | L006 F1 | L012 F1 | L006 sensitivity | L012 sensitivity | L012 specificity | L006 PR-AUC | L012 PR-AUC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Inhalation | 0.8031 | 0.8012 | 0.9680 | 0.9986 | 0.0062 | 0.8278 | 0.8123 |
| Exhalation | 0.5969 | 0.5876 | 0.8325 | 0.8625 | 0.3794 | 0.5524 | 0.5025 |
| Wheeze | 0.4891 | 0.4958 | 0.5563 | 0.5744 | 0.8513 | 0.4837 | 0.4868 |
| Rhonchi | 0.2656 | 0.2435 | 0.4666 | 0.5473 | 0.8584 | 0.1770 | 0.1522 |
| Stridor | 0.0615 | 0.0814 | 0.3449 | 0.2160 | 0.9558 | 0.0283 | 0.0361 |
| Crackle | 0.5290 | 0.5306 | 0.9792 | 0.9809 | 0.0388 | 0.3571 | 0.3636 |

Stridor's F1 improvement accompanies a sensitivity fall from 34.5% to 21.6%;
the selected threshold moved from 0.625 to 0.85. Rhonchi sensitivity rises but
precision falls from 0.1856 to 0.1566 and false positives rise from 161,238 to
232,246 on the same support. These are tradeoffs, not broad screening gains.

Full accuracy, balanced accuracy, precision, sensitivity, specificity, F1,
ROC/PR-AUC, confusion counts, thresholds and class support are in the CSV/JSON
linked below. No metric is borrowed from another threshold or population.

## High phase/crackle F1 hides weak decisions

- L012 labels inhalation positive on 99.70% of its supervised frames. Its F1
  is only 0.00030 above the always-positive F1 baseline.
- Crackle is positive on 96.83% of supervised frames; F1 gain over always-positive
  is only 0.00228. Crackle ROC-AUC is 0.53350, indicating weak ranking.
- Joint I/E prediction increases from 59.33% in L006 to 70.27% in L012, versus
  only 1.08% reference overlap on the same jointly valid frames.
- With the frozen unsmoothed v2 decoder and 0.1-s onset/offset matching tolerance,
  event F1 remains below 0.01 for every class. L012 inhalation event F1 is 0.000136.
- Neither L006 nor L012 provides an available respiratory-rate result on any of
  the 2,948 evaluated recordings under the existing complete-cycle rules.

The frame hop of 16 ms is not validated boundary accuracy. Low MAE on the few
matched events must not be presented as accuracy on all events. Fragmentation,
phase conflict, threshold selection and label granularity all require attention.

## Source addition did not resolve the bottleneck

SPRSound contributed 2,181 fitting windows, a 7.62% increase, predominantly normal
sounds. Added abnormal support was 130 crackle, 88 wheeze, 13 rhonchi and one
stridor annotation; stridor comes from one patient. New I/E labels were correctly
masked, so phase supervision was not expanded. Shared normalization and acoustic
features can still change phase behavior. This run does not isolate which
source/normalization/task mechanism caused the phase regression.

Per-device analysis at the saved global thresholds shows considerable source
heterogeneity. For example, L012 wheeze PR-AUC is 0.6996 for steth versus 0.3289
for trunc; rhonchi is 0.3006 versus 0.0089. Different class prevalences contribute
to PR-AUC differences, so this alone is not causal proof of equipment effects.

## Recommended decision

1. Keep L012 research-only; do not promote it as an overall improvement or change
   the ongoing stopping rules to obtain more epochs.
2. Finish the already authorized frequency-mask and separate phase/sound probes.
   Their results will test whether regularization or task separation improves
   discrimination and phase consistency; neither is yet a proven solution.
3. Inspect representative phase and crackle errors, coverage/negative-label
   assumptions and per-device support. Any supervision change needs a fresh,
   versioned cache and a separate experiment.
4. Predeclare Lung-specific threshold/decoder comparisons using proper inner
   selection or grouped OOF. Maximum frame F1 alone permits nearly always-positive
   phases; do not tune repeatedly on the final test or copy Heart gates blindly.
5. Prioritize additional genuinely independent rare-class annotations over more
   normal windows or duplicate segments. Preserve test-patient exclusions.

No new training was launched by this review. The pre-existing queue was active
on L009 at the initial status check; it is not modified or actively polled here.

## Reproducible artifacts

- [Machine-readable analysis](../artifacts/lung-launch/L012-review-20261110/analysis.json)
- [Complete per-class metrics CSV](../artifacts/lung-launch/L012-review-20261110/metrics.csv)
- [Four-panel plot](../artifacts/lung-launch/L012-review-20261110/analysis.png)
- Command: `python scripts/analyze_lung_overfit.py --root . --output <fresh-directory>`
  from AI-Pipeline, using a runtime with the base requirements.
- Two analysis tests pass: early-stopping arithmetic and exact per-window masked
  loss reconstruction/common-weight comparison, including invalid-input guards.
