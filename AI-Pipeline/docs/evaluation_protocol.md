# Final evaluation protocol

The CirCor test metrics already stored in this repository have been inspected. That partition is development history and must not be presented as a genuinely untouched test set for the SVM, CNN, or future models.

## What qualifies as the final holdout

A final holdout must come from newly collected AurisCore hardware recordings or a separately governed external cohort that has not influenced preprocessing, architecture, hyperparameters, early stopping, threshold selection, or quality rules. It must use participant identities that do not occur in training or validation. Exact source files and participant membership must be frozen before final model development.

The manifest must retain the standard provenance fields, including `subject_id`, `subject_group`, `recording_id`, `file_path`, `label`, `split`, `sha256`, and `dataset_source`. Assign the reserved records to `split=test`; do not include them in training or validation. Keep their labels inaccessible to model developers where project staffing permits.

## Lock before model development

1. Complete acquisition and manifest validation for the new cohort.
2. Verify participant, recording, and exact-file hashes do not cross partitions.
3. Set `holdout_status: locked_unseen` in the model configuration.
4. Run `python scripts/lock_holdout.py --config <config>`.
5. Commit `metadata/holdout_lock.json`. Any later membership or source-hash change makes evaluation fail.

The lock command refuses the current `legacy_exposed` and `pending_new_data` configurations. Changing the status is a governance assertion: do it only when the new cohort really has remained unseen.

## Freeze development decisions

Train using only `train`. Use `validation` for early stopping and the screening threshold. The threshold policy targets the configured participant sensitivity and then maximizes specificity among eligible thresholds. Freeze preprocessing, architecture, weights, threshold, and inference aggregation before final evaluation.

## Evaluate once

Run one of the following after the model is frozen:

```powershell
python scripts/evaluate_holdout.py --config configs/heart_baseline.yaml --model artifacts/models/heart_svm.joblib
python scripts/evaluate_holdout.py --config configs/heart_cnn.yaml --model artifacts/models/heart_cnn.keras
```

The evaluator verifies the lock, refuses altered membership, and refuses to overwrite an existing `final_holdout_metrics.json`. Report sensitivity, specificity, precision, negative predictive value, macro F1, confusion matrix, cohort composition, and uncertainty intervals in any later study report. A successful internal evaluation remains research evidence, not clinical validation.
