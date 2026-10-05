# AI_PIPELINE.md

## Scope

This document covers the current Heart AI work.

Lung and Abdomen are future extensions and should not distract from stabilizing the Heart pipeline.

---

## 1. Input

Expected source:
- auscultation audio,
- known sampling rate,
- single examination mode.

Target acquisition rate in the proposal:
- 8000 Hz.

Do not assume all public datasets already use this sampling rate.

Resample explicitly.

---

## 2. Dataset discipline

Each dataset item should record:

```json
{
  "source": "",
  "sample_id": "",
  "patient_or_recording_group": "",
  "label": "",
  "sample_rate": 0,
  "duration_seconds": 0,
  "split": ""
}
```

Avoid leakage.

If multiple clips originate from the same patient or same original recording, they should not be randomly distributed across training and test sets without justification.

---

## 3. Preprocessing

Reference pipeline:

```text
raw audio
-> mono conversion
-> resample
-> amplitude normalization
-> optional filtering / denoising
-> segmentation
-> log-mel spectrogram
-> normalization
-> CNN input tensor
```

Every parameter must be stored in config.

Example config fields:

```yaml
sample_rate: 8000
duration_seconds: TBD
n_fft: TBD
hop_length: TBD
n_mels: TBD
fmin: TBD
fmax: TBD
normalization: TBD
```

Do not guess final values in production code until experiments determine them.

---

## 4. Augmentation

Apply augmentation to training only.

Candidate audio augmentation:
- time shift,
- low-level additive noise,
- gain variation,
- small time stretch where physiologically acceptable,
- limited frequency masking on spectrograms,
- limited time masking.

Avoid augmentation that destroys clinically relevant temporal or spectral patterns.

Record augmentation probability and parameters.

---

## 5. Model

Current family:
- CNN using log-mel spectrogram input.

Possible training improvements:
- class weights,
- focal loss,
- batch normalization,
- dropout,
- learning-rate scheduling,
- early stopping,
- balanced sampling.

Do not assume a deeper CNN is automatically better.

---

## 6. Evaluation

Minimum report:

```text
Dataset version:
Model version:
Validation threshold:
Accuracy:
Precision:
Recall / Sensitivity:
F1:
ROC-AUC:
PR-AUC:
Confusion matrix:
```

Also show per-class results.

For imbalanced data, prioritize:
- recall,
- F1,
- PR-AUC.

---

## 7. Model selection

A new model replaces the current candidate only if:

1. its evaluation uses the same locked test set,
2. there is no dataset leakage,
3. the improvement is reproducible,
4. clinically important recall is not traded away for superficial accuracy,
5. inference cost remains acceptable for smartphone deployment.

---

## 8. Deployment

Deployment target:
- offline smartphone inference.

Export pipeline:

```text
trained model
-> validated model
-> quantization candidate
-> mobile-compatible model
-> integration test
```

The proposal targets INT8 quantization.

Before accepting quantization, compare:
- F1 before / after,
- recall before / after,
- model size,
- inference latency.

---

## 9. Model metadata

Every exported model should have metadata:

```json
{
  "model_name": "auriscore-heart-cnn",
  "model_version": "0.1.0",
  "preprocessing_version": "0.1.0",
  "threshold": null,
  "sample_rate": 8000,
  "input_shape": [],
  "classes": [],
  "dataset_version": ""
}
```

Never ship a bare model file without metadata.
