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

`EXP-H022-fold-local-hard-negative-contrastive-representation` adds one fixed supervised representation-separation loss at H021's 64-dimensional Stage-1 embedding. It reuses the five audited H021 outer-training hard-negative inventories (211, 215, 215, 212, 208 selected recordings); global H021 OOF false-positive identities are not used as supervision. Protocol SHA-256: `ab7331b77e92ba8353706d60be1606434095f44915d10e10ab1294f46452b913`. In the WSL research checkout, focused preflight tests and `./scripts/start_h022.sh --check` passed with TensorFlow 2.20 and GPU detection. **Training has not started; no H022 metrics exist.** External validation and sealed test remain closed.

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

The shared `AnalysisService` is now available for real recorded PCM/WAV input,
quality validation and Heart/Abdomen routing. Its persistent worker retains
explicitly registered backends across requests. It defaults to Heart DSP with
Murmur unavailable. Verified final packages can register Heart Murmur and Abdomen
window activity; unconfigured Abdomen remains unavailable. Deployment eligibility is not inferred
from saved candidate files. See `AI-Pipeline/docs/analysis_service.md`.

Step 1 model auditing is implemented by `scripts/audit_model_candidates.py` in
`AI-Pipeline`. It validates archives, preprocessing and threshold provenance,
optionally checks synthetic inference, and packages immutable engineering
candidates. A005 is a preliminary Abdomen candidate; no Heart deployment model
is selected. See `AI-Pipeline/docs/model_candidate_audit.md`. This does not train
models or open additional evaluation splits.

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
and sealed test remain unopened. H022 preparation was authorized separately;
this freeze does not authorize its training or change H021's result.

The [H021 freeze package](AI-Pipeline/analysis/HEART-DEVELOPMENT-FREEZE-H021/README.md)
records the locked protocol and SHA-256 hashes. H021 saved five outer-fold
evaluation pipelines, each with its own acoustic checkpoint, normalization,
scaler and logistic head. It did **not** save a final all-TRAIN deployment
model or predeclare an inference ensemble. The pooled OOF threshold is not a
threshold for one fold, a new ensemble, or a single recording. The Heart WAV
demo therefore keeps Murmur explicitly unavailable; it does not load H021
research fold weights. A separately specified deployment model and evaluation
decision is needed before Murmur inference can be connected.

## Recording-level Heart inference (step 3)

heart_inference.py implements frozen Keras scoring, recording aggregation, verified
final-model packaging, and unified Heart DSP/Murmur results. This checkout still has
no approved final package with recording-level threshold evidence. H021 research
folds and older candidate thresholds are not deployment rules. See
AI-Pipeline/docs/heart_inference.md for the contract and existing backend connection.

## Window-level Abdomen inference (phase 4)

abdomen_inference.py implements the frozen binary bowel-activity adapter and
immutable final-package verification. analyze_recording.py can retain both organ
backends and accept WAV paths, WAV bytes on stdin, or JSONL PCM/base64 recordings.
A005's window threshold is not used as a recording diagnosis or bowel event rate.
Its current single-subject evaluation does not satisfy the final-package contract.
No threshold selection, training or sealed evaluation was performed. See
AI-Pipeline/docs/abdomen_inference.md for the versioned result and evidence fields.

## App integration (phase 5)

The WebApp now sends captured PCM/recorded WAV to the retained shared worker for
Heart/Abdomen. Uploaded files, captured mock audio and device audio use real
analysis; simulator provenance remains visible. Only verified final packages
activate model-backed output. No candidate, threshold or training decision changes
in this phase. See WebApp/docs/organ-analysis.md for local setup and limitations.

## Lung implementation — training authorization pending

Pinned HF_Lung_V1 acquisition, strict labels/date-group manifests, masked temporal
log-mel caches, guarded development/final CNN commands, development/one-shot
holdout evaluation and package/inference integration are implemented. EXP-L*
experiments are separate from Heart. No Lung weights have been fitted or selected.
Test labels remain sealed; preflight never trains. Development training is now
user-authorized; EXP-L001 stopped during preparation without a saved checkpoint.
Use a fresh output directory when retrying. Uncertainty reports, model comparisons, eligibility
and TFLite/physical validation follow authorized experiments. See
AI-Pipeline/docs/lung_training.md for exact commands and limits.
