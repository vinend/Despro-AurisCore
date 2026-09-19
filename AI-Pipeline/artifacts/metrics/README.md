# Metrics artifact status

`baseline_metrics.json`, `validation_predictions.csv`, and `test_predictions.csv` are archived outputs from the 2026-09-16 SVM run. Its test partition was inspected and is no longer an untouched final holdout. Do not cite those files as current CNN performance or as unbiased final evaluation.

Current SVM and CNN training commands write validation-only development metrics and do not evaluate the final holdout. A new `final_holdout_metrics.json` can be created only through the sealed one-time workflow documented in `docs/evaluation_protocol.md`.
