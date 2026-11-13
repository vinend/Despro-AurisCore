# L006 saved-development inspection — 2026-11-10

L006 completed ten epochs, restored epoch two and saved model/predictions.
Best validation loss: 0.8269056678. This is development selection evidence,
not clinical or independent-device validation. The original result directory
is unchanged.

Read-only diagnostics and one-to-one localization evaluation are saved under
`artifacts/lung-launch/EXP-L006-analysis-20261110/` (ignored). Predictions are
bound by SHA-256 to source config, cache index and audited development manifests.
Official test labels were not opened and no thresholds were changed.

| Finding | Observation |
| --- | --- |
| Inhalation positive fraction | 94.22% of valid inhalation frames |
| Crackle positive fraction | 97.02% of valid crackle frames |
| Simultaneous phase predictions | 1,014,662 / 1,710,259 jointly supervised frames: 59.33% |
| Reference simultaneous phases | 18,486 / 1,710,259: 1.08% |
| Inhalation F1 gain vs always-positive | 0.00220 |
| Crackle F1 gain vs always-positive | 0.00063 |
| Crackle ROC-AUC / PR-AUC | 0.52598 / 0.35709 |

The frozen unsmoothed v2 decoder (minimum duration 0, merge gap 0) produces very
fragmented events. One-to-one event F1 is below 0.01 for every class when both
onset and offset must be within 0.1 s. This is evidence that the existing frame
scores/thresholds/decoder combination does not provide usable localization;
it does not isolate the cause to timing labels or dataset size. Boundary MAE on
the few matched events must not be reported as overall boundary accuracy.

## Predeclared probes against the same L006 control

- L007: lower initial LR 0.001 -> 0.0003; all other declared factors held fixed.
- L008: Adam decoupled weight decay 0 -> 0.0001 at the original LR.
- L009: TRAIN-only frequency masking of 0–4 normalized mel bins, with timestamps,
  targets and masks preserved. This is feature augmentation, not simulated
  physical sensor noise or a change to source audio.
- L010: phase-only independent sigmoid head; preserve existing overlap labels.
- L011: four-sound head; preserve existing class coverage masks.

All use dilation 16, dropout 0.2, seed 42, batch 8, maximum 50 epochs and
validation-loss early stopping (patience 8, restore best weights). Do not extend
patience or change monitored loss mid-run. Each probe starts from a fresh model;
it does not continue an overfitted epoch-ten L006 checkpoint.

Class-subset heads share the original TRAIN normalization to isolate task removal.
Class weights are projected from the same TRAIN counts. The cache remains
immutable; targets/masks are projected only in the input adapter. Compare
matching classes and frame support, not raw losses across different heads.

Each queued run saves full metrics/predictions, existing-threshold score
diagnostics, unsmoothed localization and a same-population comparison to L006.
More epochs only count as progress when best-checkpoint discrimination and
localization improve without hiding sensitivity regressions. There is no
automatic deployment selection. Remaining uncertainty requires grouped CV/OOF
and separate frozen final evaluation. See [dataset assessment](lung_dataset_expansion.md).

Implementation verification: 108 Lung tests passed under TensorFlow/WSL, with
173 dependency deprecation warnings and no skips. Serial queue startup reports
L007 active under WSL supervisor PID 384. This is launch evidence, not a measured
improvement. Original L006 metrics/predictions and official-test boundaries remain unchanged.
