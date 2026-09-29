# AurisCore spectrogram-CNN measured report

Generated: 2026-09-26T05:44:08.998247+00:00

## Run status

- Full training executed: **True**
- Training elapsed: **7520.1 seconds**
- Epochs completed: **19**
- Best validation loss: **0.432462**
- Automated tests: **[33m[32m34 passed[0m, [33m[1m76 warnings[0m[33m in 15.20s[0m[0m**
- Leakage check: **passed**

## Participant validation metrics

| Metric | Measured value |
|---|---:|
| Sensitivity | 0.9167 |
| Specificity | 0.6735 |
| Precision | 0.4074 |
| Negative predictive value | 0.9706 |
| Accuracy | 0.7213 |
| Macro F1 | 0.6796 |
| ROC-AUC | 0.9252 |
| PR-AUC | 0.8604 |
| Brier score | 0.1264 |

Selected threshold: **0.350100**. Threshold constraints met: **True**.

Confusion matrix `[[TN, FP], [FN, TP]]`: `[[66, 32], [2, 22]]`.

## Measured implementation

- Model: `auriscore_heart_residual_se_cnn`
- Parameters: **32,159**
- Spectrogram tensor: **[96, 313]**
- Feature extraction: **2.541 ms/window** on this computer
- Saved model size: **568.5 KiB**
- Model SHA-256: `0dd29e3c28a96b4b266189036f55398e3b11eaa6792bdad273b87fea3b6cd476`

## Figures

- `figures/participant_class_distribution.png`
- `figures/spectrogram_examples.png`
- `figures/training_curves.png`
- `figures/participant_evaluation.png`
- `figures/threshold_tradeoff.png`

## Interpretation boundary

These are development-validation measurements. The final holdout was not evaluated. This system remains research-only and is not a diagnosis.
