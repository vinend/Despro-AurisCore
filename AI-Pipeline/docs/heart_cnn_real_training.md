# Real Heart CNN development runs

Research screening only. The target is CirCor murmur **Absent** versus **Present**, not a disease diagnosis. All model selection in this report uses linked-participant validation results. The repository's historical CirCor test partition was already exposed during earlier SVM work, so it is not a pristine final holdout. No test inference was run for this CNN development batch; a genuinely new final holdout is still needed.

## Data and environment

- Source: local CirCor DigiScope 1.0.3 copy at `C:\Life\kuliah\Semester 6\DESPOR\data\external\circor-heart-sound\1.0.3`, copied into this project's `data/external/circor-heart-sound/1.0.3`. The repository acquisition script verified the published source hashes; no second download was needed.
- Executable: `AI-Pipeline/.runtime/python/python.exe` (Python 3.12.10, TensorFlow 2.21.0, native Windows CPU).
- Configuration: `configs/heart_cnn.yaml`, random seed 42, 8 kHz audio, five-second windows with 50% overlap, 40-bin log-mel tensors, compact CNN, participant-balanced window weights, validation-loss EarlyStopping with patience 8.
- Eligible processed cohort: 812 linked participants, 2,976 recordings, 22,819 segments. Train: 568 participants / 2,070 recordings / 15,954 segments (458 Absent, 110 Present participants; 12,862 Absent, 3,092 Present segments). Validation: 122 participants / 448 recordings / 3,335 segments (98 Absent, 24 Present participants; 2,666 Absent, 669 Present segments). Reserved internal test: 122 participants / 458 recordings / 3,530 segments; it was not evaluated for these CNN runs.
- Participant-group overlap across partitions: none, checked on the manifest and segment table before training.

## Existing compact CNN baseline

Run: [`EXP-H001-cnn-compact`](../results/EXP-H001-cnn-compact/). It trained for 23 real epochs and restored epoch 15. Approximate wall time from the run log was 9,658.64 seconds (2 hours 41 minutes). The selected validation threshold was 0.3122656103223562. The threshold policy's 0.90 sensitivity target was met, but its 0.50 minimum specificity target was not.

| Linked-participant validation metric | Baseline |
| --- | ---: |
| Accuracy | 0.4672 |
| Precision | 0.2588 |
| Recall / sensitivity | 0.9167 |
| Specificity | 0.3571 |
| Positive-class F1 | 0.4037 |
| Macro F1 | 0.4611 |
| Balanced accuracy | 0.6369 |
| ROC-AUC | 0.8282 |
| PR-AUC / average precision | 0.7125 |

The validation confusion matrix is `[[35, 63], [2, 22]]` in Absent/Present order. At the best epoch, training loss/accuracy were 0.4268/0.7968 and validation loss/accuracy were 0.5216/0.7002. By epoch 23, training loss fell to 0.3791 while validation loss rose to 1.3357; this is evidence of overfitting and unstable validation behavior. Validation accuracy at threshold 0.5 during training is distinct from the linked-participant accuracy above, which uses the selected screening threshold.

The experiment directory stores its `.keras` model, configuration, metrics, predictions, history CSV, and PNG figures. The numerical JSON/CSV files are the source of truth for these rounded values.

## Reproduction

From `AI-Pipeline`, after placing the verified CirCor 1.0.3 source tree under `data/external/circor-heart-sound/1.0.3`:

```powershell
& '.runtime/python/python.exe' scripts/build_manifest.py
& '.runtime/python/python.exe' scripts/preprocess_dataset.py --config configs/heart_cnn.yaml
& '.runtime/python/python.exe' scripts/train_cnn.py
```

The first two commands regenerate the manifest and processed segments. `train_cnn.py` allocates a new experiment ID rather than replacing an earlier run.
