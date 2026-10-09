# AI_PIPELINE.md

## 1. Scope

This document governs **trainable AI work for the current Heart Murmur branch** and its deployment path.

It does **not** define the entire Heart product. Heart also requires Rhythm DSP and Cardiac Event DSP as defined in `PRD.md` and `ARCHITECTURE.md`.

Current trainable Heart task:

```text
Murmur Absent  = 0
Murmur Present = 1
Unknown        = excluded from supervised evaluation
```

Do not silently replace this target with a disease/outcome label.

---

## 2. Input and representation

Expected source:

- auscultation audio;
- known sampling rate;
- Heart examination mode;
- participant/source identity sufficient for leakage-safe grouping.

Nominal product acquisition rate: **8000 Hz**.

Public datasets may use other rates. Resample explicitly and record source and target rates.

Reference feature path for the current CNN family:

```text
raw audio
-> mono conversion
-> resample
-> amplitude / quality validation
-> segmentation
-> configured filtering/denoising if used
-> log-mel spectrogram
-> normalization fitted only on allowed training data
-> CNN input tensor
```

Every preprocessing parameter must be versioned/configured.

---

## 3. Dataset and leakage discipline

Every dataset item should preserve enough provenance to identify:

```json
{
  "source": "",
  "subject_id": "",
  "recording_id": "",
  "label": "",
  "murmur_label": "",
  "auscultation_location": "",
  "sample_rate": 0,
  "duration_seconds": 0,
  "split": ""
}
```

Participant/source grouping is mandatory where the dataset supports it.

Segments or multiple recordings from the same participant must not be distributed across evaluation partitions in a way that leaks participant identity.

### Split roles

- training / inner validation: fitting and early stopping;
- train-only CV / OOF: model/threshold selection when required by the experiment protocol;
- external validation: only after a predeclared eligibility gate;
- sealed test/holdout: final locked evaluation only.

Never optimize on the sealed holdout.

---

## 4. Current label semantics

For the CirCor murmur work, the current supervised target is participant-level murmur status.

Source location annotations may identify declared murmur locations, but an omitted location is not automatically a confirmed negative unless the source semantics explicitly justify that interpretation.

If a training experiment changes how declared/outside-declared recordings are supervised, document the rule in the experiment protocol before training.

---

## 5. Augmentation

Apply augmentation to training data only.

Candidate conservative augmentation may include:

- small time shifts;
- low-level additive noise;
- gain variation;
- limited time/frequency masking where physiologically reasonable;
- other transformations only when justified and reproducible.

Avoid transformations that destroy murmur timing/spectral structure.

Record augmentation probability and parameters in config.

---

## 6. Model family

Current baseline family:

- CNN using log-mel spectrogram input.

Research may evaluate alternatives such as:

- dropout / normalization changes;
- class weighting;
- focal or hard-negative-aware loss;
- learning-rate/scheduler changes;
- site-aware or participant-level aggregation/MIL;
- calibration/score alignment;
- representation changes.

Prefer one-factor experiments when possible.

Do not assume a deeper/larger CNN is automatically better.

---

## 7. Current benchmark/history snapshot

### H014 — frozen historical external-validation benchmark

Experiment:

`EXP-H014-cnn-per-frequency-augmentation-declared-positive-only`

Validation:

```text
Sensitivity   0.9167
Specificity   0.7755
Precision     0.5000
F1            0.6471
ROC-AUC       0.9056
PR-AUC        0.8108
Confusion     [[76,22],[2,22]]
```

Interpretation: high sensitivity, but false positives remain the main weakness. H014 is an integration/development benchmark, not a final diagnostic-grade claim.

### H015 — end-to-end site-aware MIL

Train-only OOF ranking was near random (ROC-AUC 0.506); the experiment failed its eligibility gate. External validation was not opened.

### H016 — fold-local acoustic pretraining + frozen site-aware MIL

Train-only OOF restored ranking (ROC-AUC 0.873, PR-AUC 0.788), but at 0.90 sensitivity it produced TN/FP/FN/TP = 190/268/11/99 and F1 0.415. External validation was not opened.

### H017 — hard-negative-aware participant training

Weighted focal training reduced OOF false positives from 268 to 207 with FN unchanged at 11: sensitivity 0.90, specificity 0.548, precision 0.324, F1 0.476. The gate failed; external validation remained closed.

### H018 — participant ranking margin

Adding a participant ranking term yielded OOF TN/FP/FN/TP = 263/195/11/99, sensitivity 0.90, specificity 0.574, precision 0.337, F1 0.490, ROC-AUC 0.891, PR-AUC 0.792. The 12-FP reduction from H017 was modest; external validation remained closed.

### H019 — uniform acoustic pooling

Replacing attention with uniform pooling yielded OOF 257/201/10/100, sensitivity 0.909, specificity 0.561, precision 0.332, F1 0.487, ROC-AUC 0.887, PR-AUC 0.789. It did not improve on H018; the gate failed and external validation remained closed.

### H020 — regularized linear participant head

With frozen acoustic embeddings, uniform mean pooling, outer-training-only StandardScaler, and nested train-only L2 logistic C selection, OOF was 279/179/11/99 at threshold 0.1623002392: sensitivity 0.90, specificity 0.609, precision 0.356, F1 0.510, ROC-AUC 0.892, PR-AUC 0.814. Simpler participant classification helped but left substantial false positives. External validation remained closed.

### H021 — fold-local hard-negative acoustic mining

The current strongest TRAIN-only result used leakage-safe, fold-local Stage-1 hard-negative weighting. Among 568 participant OOF predictions, threshold 0.19225345646277395 gave TN/FP/FN/TP = 341/117/11/99, sensitivity 0.90, specificity 0.7445, precision 0.4583, F1 0.6074, ROC-AUC 0.9028, and PR-AUC 0.8302. FP fell by 62 from H020 while FN stayed at 11. The full engineering gate still failed. Five fold-evaluation pipelines exist, but no final all-TRAIN deployment model or predeclared deployment ensemble exists. External validation and sealed test remain closed.

### H022 — prepared experiment, not started

`EXP-H022-fold-local-hard-negative-contrastive-representation` adds one fixed supervised representation-separation loss at H021's 64-dimensional Stage-1 embedding. It reuses the five audited H021 outer-training hard-negative inventories (211, 215, 215, 212, 208 selected recordings); global H021 OOF false-positive identities are not used as supervision. Protocol SHA-256: `ab7331b77e92ba8353706d60be1606434095f44915d10e10ab1294f46452b913`. Focused preflight tests and `./scripts/start_h022.sh --check` passed with TensorFlow 2.20 and GPU detection. **Training has not started; no H022 metrics exist.** External validation and sealed test remain closed.

---

## 8. Evaluation requirements

Do not report accuracy alone.

At minimum report:

```text
Dataset/split provenance
Experiment ID
Model/preprocessing version
Evaluation unit/population
Threshold-selection method
Threshold
Accuracy
Precision
Recall / Sensitivity
Specificity
F1
Balanced Accuracy when relevant
ROC-AUC
PR-AUC
Confusion Matrix
```

For imbalanced murmur screening, emphasize:

- sensitivity;
- precision;
- specificity;
- F1;
- PR-AUC;
- false-positive / false-negative counts.

### Current engineering direction

Internal development targets:

```text
Sensitivity >= 0.90
Specificity >= 0.85
Precision   >= 0.65
F1          >= 0.75
ROC-AUC     >= 0.92
PR-AUC      >= 0.85
```

These are engineering goals, not clinical/regulatory standards.

The report's historical F1 >90% statement remains an aspirational project target, not evidence that current models already meet it.

---

## 9. Threshold selection

Threshold selection must follow a predeclared experiment protocol.

For sensitivity-first screening:

1. satisfy the declared minimum sensitivity;
2. optimize the declared secondary metric only among eligible thresholds;
3. report the complete precision/specificity/FP/FN tradeoff.

Never tune threshold on the sealed test set.

Do not confuse threshold improvement with ranking improvement.

---

## 10. Early stopping

Early stopping must be defined before training.

For the current pipeline, validation loss is an acceptable training-stop signal. Threshold-dependent metrics such as F1 are evaluated after training unless the experiment explicitly studies a different predeclared stopping rule.

Do not change the stopping metric mid-run because intermediate results look favorable.

Long training follows the non-polling rule in `AGENTS.md`.

---

## 11. Experiment artifacts

Each completed experiment must use a unique immutable directory:

```text
AI-Pipeline/results/EXP-HNNN-name/
```

Store as applicable:

- `protocol.json`;
- `config.json`;
- `metrics.json`;
- predictions CSV;
- fold metrics;
- threshold tradeoff;
- training history;
- model checkpoint;
- ROC/PR plots;
- score-distribution/calibration plots;
- summary Markdown/JSON.

Do not overwrite prior completed experiment artifacts.

---

## 12. Model selection / external validation gate

A candidate may replace the current development candidate only when:

1. the comparison protocol is valid and leakage-safe;
2. the improvement is reproducible;
3. sensitivity is not traded away merely for prettier accuracy/precision;
4. inference cost remains practical for smartphone deployment;
5. the external-validation gate is explicitly satisfied before external validation is opened.

External validation should not become an iterative hyperparameter playground.

---

## 13. Deployment

Deployment target: offline smartphone-compatible inference.

```text
trained candidate
-> validated/frozen candidate
-> export
-> quantization candidate
-> mobile integration test
```

The report proposes INT8 deployment. Before accepting quantization, compare:

- sensitivity;
- precision/F1;
- model size;
- inference latency;
- any preprocessing compatibility changes.

Every exported model must include metadata such as:

```json
{
  "model_name": "auriscore-heart-murmur-cnn",
  "model_version": "",
  "preprocessing_version": "",
  "threshold_version": "",
  "threshold": null,
  "sample_rate": 8000,
  "input_shape": [],
  "classes": ["absent", "present"],
  "dataset_version": ""
}
```

Never ship a bare model artifact without metadata.

---

## 14. Boundary with Heart DSP

The unified Heart result combines an available Murmur AI output with:

- Rhythm DSP output;
- Cardiac Event DSP output.

AI research code must not fabricate BPM, S1/S2, S3/S4, or rhythm results merely to fill the unified schema. Prototype DSP modules now provide candidate outputs independently; they still require labeled validation before clinical claims.

### H021 development freeze (2026-10-09)

`EXP-H021-fold-local-hard-negative-acoustic-mining` is the strongest current
**TRAIN-only development candidate**, based on 568 participant-exclusive OOF
predictions: threshold 0.19225345646277395, TN/FP/FN/TP = 341/117/11/99,
sensitivity 0.9000, specificity 0.7445, precision 0.4583, F1 0.6074,
ROC-AUC 0.9028, PR-AUC 0.8302. Relative to H020, FP fell by 62 with FN
unchanged. These are development estimates, not clinical performance. H021
fails the predefined external-validation eligibility gate; external validation
and sealed test remain unopened. H022 preparation was authorized separately; this freeze does not authorize its training or change H021's result.

The [H021 freeze package](AI-Pipeline/analysis/HEART-DEVELOPMENT-FREEZE-H021/README.md)
records the locked protocol and SHA-256 hashes. H021 saved five outer-fold
evaluation pipelines, each with its own acoustic checkpoint, normalization,
scaler and logistic head. It did **not** save a final all-TRAIN deployment
model or predeclare an inference ensemble. The pooled OOF threshold is not a
threshold for one fold, a new ensemble, or a single recording. The Heart WAV
demo therefore keeps Murmur explicitly unavailable; it does not load H021
research fold weights. A separately specified deployment model and evaluation
decision is needed before Murmur inference can be connected.

## Research checkout detail: H018–H021 protocols

## H018 train-only research protocol (2026-10-08)

The H017 postmortem is saved at
`AI-Pipeline/analysis/EXP-H017-hard-negative-aware-murmur/postmortem/`.
Its locked 90%-sensitivity OOF threshold produced 207 FP and 11 FN among
568 training participants. The threshold was Pareto-optimal under the declared
sensitivity constraint; 131/207 FP were within +0.10 probability of it.
Cross-fold scale differences and a high-confidence negative tail were
secondary observations.

H018 tests one change: add a fixed participant positive-negative pairwise
hinge margin to H017's participant focal-loss training. It retains H016's
fold-local pretrained frozen acoustic encoders, H017's site-aware MIL
architecture, H015's exact outer folds, fit-only augmentation and
normalization, class weights, internal BCE early stopping, and train-only OOF
threshold policy. The margin and loss weight are recorded before training in
`AI-Pipeline/analysis/EXP-H018-participant-ranking-margin/protocol.json`.
The H018 worker reads only the train split and cannot use the external
validation or sealed holdout. OOF metrics are research selection evidence,
not an exported or clinical performance estimate. No product/integration
schema changes occur in H018.

## H018 postmortem and H019 research protocol (2026-10-08)

H018 remained TRAIN-only and failed its advancement gate. Its 568-participant
OOF confusion matrix was [[263,195],[11,99]], with sensitivity 0.90 and F1
0.4901. The saved postmortem is at
`AI-Pipeline/analysis/EXP-H018-participant-ranking-margin/postmortem/`.
The H017-to-H018 transitions were 22 FP corrected and 10 new FP; 185 FP
persisted. A fold-local outer-train-fit linear diagnostic probe on frozen
acoustic embeddings produced 136 FP at 0.90 sensitivity, versus 195 for
H018, but changes both pooling and classifier and is not a model candidate.
This supports testing participant aggregation before more acoustic training.
Fold-scale mismatch and genuine embedding overlap remain secondary.

H019 is a one-factor TRAIN-only OOF experiment: replace H018's learned
site-aware attention weights by equal weights across each participant's real
recordings. The 64-dimensional acoustic encoder stays frozen and fold-local;
segment-to-recording means, participant classifier, focal-plus-margin loss,
augmentation, normalization, fold roles, class weighting, and threshold rule
remain unchanged. Site IDs remain in the bag schema but do not influence
uniform weights. The locked protocol and exact hashes are stored in
`AI-Pipeline/analysis/EXP-H019-uniform-acoustic-pooling/`.
External validation and the sealed holdout stay closed. No mobile/API schema
or Heart product requirement changes.

## H019 result and H020 linear participant head (2026-10-08)

H019 remained TRAIN-only. Its 568-participant OOF confusion matrix was
`[[257,201],[10,100]]` (sensitivity 0.9091, specificity 0.5611, F1 0.4866,
ROC-AUC 0.8866, PR-AUC 0.7890). Uniform pooling corrected 17 H018 false
positives but introduced 23 new ones; it increased total false positives from
195 to 201. The focused transition audit is at
`AI-Pipeline/analysis/EXP-H019-uniform-acoustic-pooling/postmortem/`.
There was no consistent benefit across folds or recording counts.

H020 tested participant decision simplicity as one conceptual factor. It used
H019's uniform mean pooled 64-dimensional acoustic features from the same
frozen H016 fold-local encoder checkpoints; no CNN weights were updated.
For each exact H015 outer fold, a `StandardScaler` and balanced L2 logistic
regression were fitted on outer-training participants only. Regularization
`C` was chosen through five stratified inner folds among the predeclared
`[0.01, 0.1, 1.0, 10.0]`, maximizing F1 subject to sensitivity at least
0.90, then specificity and precision. The five selected values were
`[1.0, 0.01, 0.01, 0.1, 1.0]`. The balanced class-weight policy preserves
the earlier diagnostic linear probe and was not searched. The frozen encoder
had already seen inner held-out participants; inner selection is conditional
on those fixed embeddings, while outer held-out participants remained unseen
by both the encoder and logistic head.

H020's 568-person TRAIN OOF operating point used the predeclared
sensitivity-first threshold rule. Threshold `0.1623002391586189` yielded
`[[279,179],[11,99]]`, sensitivity `0.9000`, specificity `0.6092`, precision
`0.3561`, F1 `0.5103`, balanced accuracy `0.7546`, ROC-AUC `0.8924`, and
PR-AUC `0.8138`. Compared with H018, false positives fell by 16 and F1
rose by 0.0202, with 11 false negatives unchanged. Compared with H019, false
positives fell by 22 but one additional false negative was observed.

H020 met its minimum improvement rule but missed its strong-result threshold
of at most 150 false positives and did not reproduce the exploratory
fixed-C diagnostic probe's 136 false positives. It also missed the locked
external-validation eligibility gate. The final engineering targets remain
unmet. Stop participant-head tuning here; a separately authorized,
pre-registered representation-level investigation is the next research
option if project time permits. H014 remains the historical frozen validation
benchmark; H020 OOF and H014 validation values are not interchangeable.
External validation and the sealed test were not opened for H020. No Heart
product definition or mobile/API contract changed.

## H021 fold-local acoustic hard-negative mining protocol (2026-10-08)

H020 remains TRAIN-only: its 568-participant OOF threshold 0.1623002392 gave
[[279,179],[11,99]], sensitivity 0.9000, specificity 0.6092, precision
0.3561, F1 0.5103, ROC-AUC 0.8924, and PR-AUC 0.8138. H020 reduced FP
relative to H018/H019 but did not reach its strong-result or external
validation gate. The H020 representation precheck uses fold-local acoustic
embeddings and TRAIN OOF decisions only. Of 179 H020 FP, 88 had at least one
Present neighbor among five nearest fold-local training embeddings versus
23 of 279 TN; 157 FP nevertheless remained closer to the Absent centroid.
This supports a targeted test of local acoustic overlap, without claiming
that representation is the only cause of false positives.

H021 tests one conceptual change: fold-local acoustic Stage-1 gradient-fit
segments belonging to the top 20% highest cross-fitted-scoring Absent
recordings receive an exact 2.0 multiplier on the existing H016 participant-
balanced segment weights. Other eligible examples receive 1.0. The top 20%
are selected among the saved H015 `fit`-role Absent recordings, so every
selected recording can actually influence the outer Stage-1 fit. Five inner
participant folds within each outer-training partition train fresh compact
CNNs from scratch. Each inner-held participant is scored by a model that
never trained or early-stopped on that participant. Scores average segment
probabilities per recording. Outer-held participants never enter mining,
normalization, or Stage-1 fitting. Present declared-site supervision and
ambiguous-site exclusion are unchanged.

H021 then trains one outer Stage-1 encoder from scratch per original H015
fold, freezes it, and produces mean-of-segment recording embeddings and
uniform mean participant embeddings. The participant path is exactly H020's
fold-local StandardScaler and balanced L2 logistic classifier with the fixed
C grid `[0.01, 0.1, 1.0, 10.0]` and inner-CV selection policy. OOF threshold
selection remains sensitivity >=0.90 then maximum F1, specificity, and
precision. The immutable protocol and hashes are in
`AI-Pipeline/analysis/EXP-H021-fold-local-hard-negative-acoustic-mining/`.
Training is detached and resumable from epoch checkpoints. External
validation and sealed holdout are closed in H021. Eligibility for future
external validation requires all six current engineering targets, including
sensitivity >=0.90. No mobile/API contract or Heart product definition changes.

## H021 result and H022 preparation (2026-10-09)

H021 completed its genuine 568-participant TRAIN OOF evaluation with threshold
0.19225345646277395: TN 341, FP 117, FN 11, TP 99, sensitivity 0.9000,
specificity 0.7445, precision 0.4583, F1 0.6074, ROC-AUC 0.9028, and
PR-AUC 0.8302. It reduced H020 false positives by 62 without increasing false
negatives. It did **not** meet the six-metric external-validation eligibility
gate; external validation and sealed test remain closed.

H022 is prepared but **not trained**. It is a one-factor representation-level
test: retain H021's exact outer folds, declared-site supervision, recording
hard-negative identities and 2.0 weights, CNN/preprocessing, and H020 linear
participant classifier; add a fixed supervised contrastive term at the 64-D
acoustic embedding (temperature 0.10, weight 0.10). The five fold-local H021
hard-negative inventories were re-audited against inner-held scores and saved
hashes, then locked into the H022 protocol. Global H021 OOF false-positive
identities are never used to define H022 training examples. Run
`AI-Pipeline/scripts/start_h022.sh --check` for read-only launch readiness;
only an explicitly authorized later start launches training. H022 cannot
open external validation or sealed test during this development run.
