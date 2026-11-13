# L016–L018 completed-result review — 2026-11-10

## Scope, authority and boundaries

Read-only research evaluation requested after all three runs completed. Serves
PRD section 7 acoustic findings (wheeze/rhonchi/crackle). Inputs are immutable
development predictions, histories, source manifests, cached features and frozen
checkpoints. Outputs are research reports/tests; no deployed interface changes,
source relabeling, preprocessing changes, split changes or new training. Lung
phase/respiratory requirements and Heart/Abdomen remain unchanged.

**Conclusion:** the numerical/objective corrections do not resolve generalization.
The evidence now identifies a concrete window-reference inconsistency in the
feature representation, alongside strong device-conditional failure and weak
temporal supervision/localization. These are actionable mechanisms and plausible
contributors, not proof of a single cause for every post-epoch-two loss increase.

## Comparable evaluation

All runs have identical saved truth, masks, prediction order, classes and held-out
groups (SHA-256 equality checked). Population: 17,688 overlapping validation
windows, 2,948 recordings, 24 shifted-date groups. Patient independence remains
unverified. TRAIN has 28,620 windows from 4,770 distinct normalized-PCM recordings
and 94 date groups; window count is not independent subject count.

| Run | Best / completed epoch | Best own loss | Loss using common L016 weights | Macro PR-AUC |
|---|---|---:|---:|---:|
| L016 | 2 / 10 | 0.983376 | 0.983376 | 0.354297 |
| L017 | 2 / 10 | 0.938403 | 0.988444 | 0.358749 |
| L018 | 1 / 9 | 1.003130 | 1.079615 | 0.341720 |

L017's smaller own loss is not evidence of improved common-objective fit: once
the same weights are applied it is slightly worse than L016. L018 is worse on
the common objective and all three PR-AUC values relative to L017. L017 is the
highest macro PR-AUC within this bounded trio, but its gain over L015 is only
about .0040, below the predeclared .01 review criterion. All three fail the
declared research gate, including crackle ROC-AUC >=.60 and specificity >=.10.
There is no approved candidate or new deployment claim.

| Run | Wheeze PR-AUC | Rhonchi PR-AUC | Crackle PR-AUC | Crackle specificity |
|---|---:|---:|---:|---:|
| L016 | 0.510974 | 0.178224 | 0.373694 | 0.067484 |
| L017 | 0.504606 | 0.190349 | 0.381291 | 0.056016 |
| L018 | 0.496292 | 0.169070 | 0.359798 | 0.098256 |

All full confusion counts, sensitivity, precision, F1, accuracy/balanced accuracy,
ROC/PR-AUC, support and frozen per-class thresholds are in `analysis/metrics.csv`.
Those thresholds retain each run's predeclared maximum-F1 rule; none were tuned
during this review. Raw loss reconstructs the saved best loss within 0.0000015,
which supports correct objective/count reporting. L016 combines numerical-runtime
and BCE changes, so its comparison to L015 is not a pure BCE ablation.

## New finding: shared audio has different window-relative features

The current shared spectrogram extractor calls
`librosa.power_to_db(power, ref=np.max, top_db=80)` separately for each window.
Consequently a loud sound elsewhere in a five-second window changes the dB
reference of every shared frame. The same absolute FFT/mel frame appearing in
two overlapping windows can receive different numeric features. The later
TRAIN-frequency normalization does not remove this window-dependent offset.

Fixed seed42 source-balanced sampling of 128 recording pairs (32 per
TRAIN/validation x device) gives:

| Sample | Median absolute dB offset | Maximum | Fraction >1 dB |
|---|---:|---:|---:|
| TRAIN steth | 1.486 | 19.868 | 59.4% |
| TRAIN trunc | 1.209 | 21.476 | 56.3% |
| Validation steth | 1.418 | 11.611 | 53.1% |
| Validation trunc | 0.505 | 12.563 | 37.5% |

After subtracting the median scalar offset, median residual feature differences
are only roughly 0.000001–0.000010 dB in these groups. A synthetic test reproduces
the effect by adding loud energy outside the shared audio. Thus this is not just
a between-recording or label-distribution correlation.

A frozen L017 GPU inference probe selects the first eight pairs per source/split
from that sample, independently of labels, scores or offset magnitude: 32 pairs.
It compares only frames whose entire +/-35-frame receptive field lies inside
**both** windows. It then adds the measured scalar offset to the second feature
window in memory, keeping model weights, audio, thresholds and normalization fixed.

- Validation steth: mean absolute score disagreement drops by 99.0% for wheeze,
  99.5% for rhonchi and 99.8% for crackle.
- Validation trunc: disagreement drops by 61.7%, 55.9% and 73.4% respectively.
- TRAIN reductions range from 72.8% to 95.3%.

This paired intervention supports a causal contribution of the window-reference
offset to **overlap prediction inconsistency**. It does not prove that changing
preprocessing improves held-out ranking or eliminates later overfitting.
Remaining differences can include clipped spectral floors and residual feature
differences; their relative causes were not isolated.

Full-validation overlap analysis also finds same-frame score ranges averaging
about .040–.052 across labels in L017, and .017–.019 even when both contexts are
fully interior. At frozen thresholds, 4.49% of repeated supervised wheeze frames
cross the decision boundary between windows (1.60% for fully interior contexts).
Boundary padding therefore contributes additional instability, but cannot
explain all of it. The temporal convolution has a sparse 71-frame receptive
span; receptive-field span alone is not continuous coverage or validated timing.

**Recommended representation fix:** use a new Lung-only feature version with a
fixed explicit dB reference and fixed floor. Merely changing `ref` while retaining
per-window `top_db` clipping still leaves a window-dependent floor. Fit frequency
normalization on TRAIN only. Preserve original targets/splits and create a new
immutable cache. Do not globally change the shared Heart/Abdomen extractor or
retroactively alter an existing experiment's preprocessing provenance.

## Device-conditional failure survives the corrections

Crackle ROC-AUC:

| Run | steth | trunc | Pooled |
|---|---:|---:|---:|
| L016 | 0.7050 | 0.4674 | 0.5372 |
| L017 | 0.7260 | 0.4854 | 0.5554 |
| L018 | 0.6922 | 0.4813 | 0.5365 |

This is a poor generalization result within `trunc`, not simply a bad selected
threshold: ROC-AUC is threshold-independent. It cannot be repaired by calibration
alone. On `trunc`, L017 rhonchi ROC-AUC is only .5455 and PR-AUC .00917, close to
its .00885 frame prevalence, despite pooled rhonchi ROC-AUC .8269.

The earlier measured prevalence/source shift remains: rhonchi TRAIN-trunc 7.88%
versus validation-trunc .88%; TRAIN steth window share 50.13% versus validation
29.27%. Device-only TRAIN priors already explain much of pooled rhonchi ranking
and remain competitive with pooled crackle. Do not infer a device calibration
rule or delete difficult records to improve the headline metric.

## Weak temporal signal, not only overlapping-window metric inflation

Merging identical absolute frames reduces validation to 2,753,431 physical frames
before per-class annotation masks. PR-AUC remains similar (L017: wheeze .50905,
rhonchi .19532, crackle .38266); overlap removal does not rescue the model. The full
overlapping and merged populations must not be mixed in a metric comparison.

Within-record ROC-AUC is evaluated only when a recording has both known positive
and known negative frames. For L017 crackle, pair-weighted AUC is .6565 in steth
(219 mixed-label records) and .5747 in trunc (460 records). The improvement over
trunc's pooled .4854 suggests that between-record/source ordering also hurts;
within-record temporal separation is still modest. These selected mixed-label
record metrics are diagnostic, not replacement whole-population performance.

Replacing every frame's score with its recording's mean **predicted audio score**
(no target fitting) improves rhonchi PR-AUC on the same deduplicated population:
L016 .18269 -> .21757; L017 .19532 -> .21569. Some pooled ranking is therefore
record-level rather than accurate localization. This is an ablation, not a
recommended detector or evidence that temporal learning is absent for all labels.

At the frozen unsmoothed decoder, event F1 is only .001–.006 across these runs,
with many fragmented false events. Source crackle annotations have median
durations .735–.875 seconds across device/split groups and designate intervals
containing crackles. They are not individual-click timestamps. Mechanical/audio
review found no obvious misalignment, but that does not make these labels strong
click-level supervision. Do not silently relabel the dataset or claim acoustic
click localization from the frame F1.

## Why epoch two, and what cannot be reconstructed

The histories confirm decreasing TRAIN loss and rising held-out loss:

- L016: best .98338 at epoch two -> final 1.34806, while TRAIN .69294 -> .47458.
- L017: best .93840 at epoch two -> final 1.35254, while TRAIN .64913 -> .45297.
- L018: best 1.00313 at epoch one -> final 1.24698, while TRAIN .88445 -> .52911.

Two epochs already contain 7,156 optimizer updates for L016/L017. L018 peaks
after 3,187 updates, showing that the trigger is not literally a universal
epoch-two code path. Reducing empty windows changes shuffle composition and
updates/epoch; it does not independently add acoustic diversity or domain
invariance. The best-checkpoint TRAIN/validation diagnostic subsamples also show
a large crackle gap, supporting generalization concerns.

The most plausible combined account is rapid fitting to the current correlated,
device-dependent representation, followed by further optimization that does not
transfer to the held-out population. The feature-reference intervention supplies
a concrete mechanism; domain-conditional metrics establish where the weakness
is. Neither measurement proves the complete training-trajectory causal chain.

**Critical observability limit:** only best-checkpoint predictions/weights and
aggregate epoch losses were retained. `model.keras` has restored best weights;
it is not the last epoch model. We cannot reconstruct per-class ROC/PR-AUC,
calibration, confidence growth or gradient behavior for epochs 3–10. Therefore
we cannot assert that ranking degraded every epoch, that loss growth is solely
overconfidence, or that a particular class alone caused the late rise.
L016–L018 also share LR .001, so this trio alone does not rule out LR effects.

Analytic inverse-positive-weight correction reduces some Brier errors, especially
for rhonchi, but is not fitted/validated calibration and preserves each class's
ranking. Raw sigmoid scores optimize weighted BCE and must not be interpreted
as unweighted disease probabilities. The correction was descriptive only; no
threshold, checkpoint or reported classification output changed.

## Next work, before another fitting run

1. Implement/test an opt-in Lung fixed-reference/fixed-floor representation.
   Require shared-frame feature consistency, including window interiors and
   physical-tail masking; preserve legacy Heart/Abdomen behavior and all splits.
2. Add predeclared trajectory evidence: saved early/best/last checkpoints and
   predictions or reproducible probes; class-wise loss, PR/ROC-AUC, reliability,
   FP/FN and device/group metrics on fixed TRAIN/inner-validation samples, indexed
   by optimizer updates as well as epoch. Do not switch stopping metrics mid-run.
3. Use TRAIN-only grouped development comparisons for representation/LR choices.
   Retain device strata, overlap/recording baselines and sensitivity consequences;
   predeclare a bounded evaluation on the existing held-out development population.
4. Audit acquisition/source differences and acquire compatible source-diverse
   crackle/rhonchi recordings if warranted. Independent subjects, both devices and
   compatible interval labels matter more than multiplying overlapping windows.
5. Do not launch another larger-epoch or patience-only experiment from this review.
   No new training was requested or started here; official test stays sealed.

## Reproducibility and verification

Scripts: `scripts/review_lung_objective_results.py` and
`scripts/probe_lung_window_reference.py`; helpers/tests:
`src/auriscore/lung_deep_review.py`, `tests/test_lung_deep_review.py`.
Six focused review tests pass (including two existing loss/stopping tests).
The GPU probe performs inference only on the frozen model; model SHA-256 is
unchanged, optimizer steps zero, no new thresholds selected.

Evidence directory: `artifacts/lung-launch/L016-L018-deep-review-20261110/`.
`analysis/report.json`, `metrics.csv`, `within-record.csv`, `feature-overlaps.csv`,
`feature-pairs.json`, visually checked `review.png`, and
`reference-probe/report.json` / `pairs.csv` preserve numerical findings.
The main report binds source/model/prediction/cache hashes; prior run directories
and caches remain intact. No production schema or model version is activated.
