# EXP-L003 development inspection — 2026-10-10

Scope: PRD section 7 phase/acoustic findings. Research-only inspection of pinned
HF development annotations and caches plus user-provided Linux EXP-L003 metrics.
No production interface, data split, label policy, threshold or model changed.
No training or official-test label opening occurred. The Linux prediction archive
is absent locally; score histograms and joint prediction states remain pending.

## What was measured

The read-only diagnostic command traversed all 46,308 cached windows: 28,620 TRAIN
and 17,688 validation. Its validation positive/negative counts match the user's
EXP-L003 confusion-matrix populations exactly. Cache index SHA-256:
`f4b18ca1d08bb8c50c87b71aa8371ff7a61c2d98d022d29767a3135bbdba9f48`.
Counts include overlapping windows and are not independent patient samples.
The local aggregate report is ignored at
`artifacts/lung-launch/diagnostics-local-cache.json`.

| Class | TRAIN positive prevalence | Validation positive prevalence | TRAIN positive weight | Validation always-positive F1 | EXP-L003 F1 |
|---|---:|---:|---:|---:|---:|
| Inhalation | 62.89% | 66.79% | 0.590 | 0.8009 | 0.8018 |
| Exhalation | 40.59% | 36.64% | 1.464 | 0.5363 | 0.5492 |
| Wheeze | 14.52% | 16.69% | 5.887 | 0.2861 | 0.4513 |
| Rhonchi | 10.03% | 4.58% | 8.969 | 0.0876 | 0.2199 |
| Stridor | 1.67% | 1.07% | 20.000 | 0.0211 | 0.0526 |
| Crackle | 28.70% | 35.90% | 2.485 | 0.5283 | 0.5361 |

Weights match `clip(TRAIN negatives / TRAIN positives, 0.25, 20)`; validation
is not used to calculate them. No incorrect ratio was found. Weighting moves
scores away from ordinary unweighted probability interpretation and warrants a
controlled comparison, not an assumption that removing it solves the problem.

No supervised padded-tail frames were found. There are 9,930 masked positive
cells across the cache; positives can legitimately be masked in incomplete
frames, so this count alone is not an error. This is a support/invariant audit,
not a proof that every annotation or preprocessing boundary is correct.

Cached targets have both phases positive on 33,913 of 2,846,564 jointly valid
TRAIN frames (1.19%) and 18,486 of 1,710,259 validation frames (1.08%). There are
no jointly valid neither-phase frames: gaps are masked by the current policy.
An independent source-interval intersection check found 1,306 overlapping I/E
annotation pairs in 896 TRAIN recordings and 662 pairs in 402 validation
recordings, totaling 25.698 and 16.134 pairwise seconds respectively. Frame
overlap is also enlarged by the any-FFT-overlap target rule. Do not turn these
targets directly into exclusive softmax labels without a declared policy.

There is device/source composition shift: steth windows are 50.13% of TRAIN but
29.27% of validation. Rhonchi prevalence is 7.88% in TRAIN/trunc versus 0.88% in
validation/trunc. Date groups are preserved; patient independence is unverified.
Per-device prediction errors cannot be established without saved predictions
and their recording identities.

## Label and architecture interpretation

The [original dataset study](https://doi.org/10.1371/journal.pone.0254134), Data
labeling section, describes D as periods containing crackles, rather than
individual explosive clicks. Locally the median D interval is 0.815 seconds;
the 5th/95th percentiles are 0.419/1.642 seconds. This is consistent with interval
labels. The current model learns crackle-containing intervals, not individual
click timing. No evidence of an I/E/D mapping reversal was found in the parser.

The study allowed unclear sounds to go unlabeled. The code's coverage flag is
derived from nonempty parsed events and no manifest errors; it does not validate
complete absence labels. Supervised negatives inside annotated breaths remain
an explicit research assumption requiring annotation review. Outside those
regions the current mask supervises only explicit positives.

The temporal CNN has three 3-frame convolutions and one 5-frame convolution,
with frequency-only pooling. Its temporal receptive field is 11 feature frames,
or approximately 224 ms including the 64-ms FFT. Five-second input windows do
not provide five seconds of context to each output. Independent sigmoid outputs
also impose no inhale/exhale exclusivity or cycle alternation.

## Recommended next sequence

1. Run the new diagnostic command on Linux EXP-L003. Inspect score distributions
   for positive versus negative frames and simultaneous phase predictions at the
   saved thresholds. No new fitting or threshold selection is needed.
2. Review representative TRAIN annotations/audio, especially unclear absences,
   phase boundary overlaps and crackle-containing intervals. Predeclare any
   mask/target-policy change and version its cache; preserve this baseline.
3. After that review, prepare one-factor TRAIN-group development comparisons:
   longer temporal context, separately trained phase/acoustic tasks, then a
   class-weight comparison as separate experiments. Avoid changing all three
   at once. Freeze phase-overlap handling before introducing exclusive labels.
4. Use per-class ranking and event/respiratory behavior alongside F1 and
   always-positive baselines. Keep the official test sealed during selection.

Engineering validation: 28 focused Lung tests passed, including three new
diagnostic tests. No model weights were fitted; no model was promoted. These
findings motivate research changes and do not demonstrate deployment readiness.
