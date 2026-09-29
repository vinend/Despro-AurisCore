# Spectrogram CNN implementation

## Status and scope

The pipeline converts every WAV window into a floating-point time-frequency
tensor and trains a 2D CNN from that tensor. PNG/JPEG files are not used as
model input: rendering would add quantization, colormap, label, and resizing
artifacts. A small PNG set is available only for visual quality control.

This remains a research screening system. The new development workflow does
not make the historical test partition fresh again, and it does not establish
clinical validity.

## Signal and model flow

```text
WAV -> mono/resample/DC removal -> five-second windows
    -> training-only gain/shift/noise augmentation
    -> log-mel or log-STFT float tensor
    -> training-set frequency normalization
    -> training-only time/frequency masks and optional MixUp/CutMix
    -> residual squeeze-and-excitation CNN
    -> recording and linked-participant aggregation
    -> validation-selected screening threshold
```

The original compact CNN remains available through `configs/heart_cnn.yaml`.
The new implementation is opt-in through `configs/heart_spectrogram_cnn.yaml`.

## Configuration safety

- `feature_fmax` is rejected when it exceeds Nyquist.
- Per-frequency normalization is fitted only on the training partition and is
  saved with the model for identical inference.
- Augmentation is used only while producing training examples.
- Cached arrays include the source hash, segment boundaries, and a digest of
  every feature parameter that can alter tensor values.
- Cross-validation uses linked participant groups, never individual windows,
  as its fold unit.
- Threshold selection and all reported validation metrics operate at linked
  participant level after recording aggregation.

The supplied configuration retains the current 8 kHz acquisition contract and
a 2 kHz feature maximum. If measured hardware output is really 2 kHz, change
`sample_rate` to `2000` and `feature_fmax` to at most `1000`, then rebuild all
processed audio. Upsampling cannot recover frequencies beyond the source
Nyquist limit.

## Commands

For an interactive full training run with measured plots and exported reports:

```powershell
python -m pip install -r requirements-notebook.txt
python -m jupyter lab notebooks/spectrogram_cnn_measured_training.ipynb
```

Use **Run All**. Full preprocessing and training are enabled by default. The
notebook writes `artifacts/notebook_report/measured_report.json`,
`measured_report.md`, and figures for class balance, spectrogram examples,
learning curves, participant ROC/PR and confusion matrix, score distributions,
and the threshold sensitivity-specificity trade-off.

Build the dataset, processed windows, and a final development model:

```powershell
python scripts/run_pipeline.py --config configs/heart_spectrogram_cnn.yaml
```

If preprocessing with the exact same configuration is already complete:

```powershell
python scripts/train_cnn.py --config configs/heart_spectrogram_cnn.yaml
```

Precompute deterministic validation/inference tensors and render twelve visual
examples:

```powershell
python scripts/cache_spectrograms.py --config configs/heart_spectrogram_cnn.yaml --previews 12
```

Run five-fold participant-exclusive development cross-validation:

```powershell
python scripts/train_cnn_cv.py --config configs/heart_spectrogram_cnn.yaml
```

Cross-validation trains five models and can take approximately five times as
long as one development run. It never evaluates the final `test` partition.

## Outputs

Normal training writes:

- `artifacts/models/heart_cnn.keras`
- `artifacts/models/heart_cnn.json`
- `artifacts/metrics/cnn_metrics.json`
- `artifacts/metrics/cnn_training_history.json`
- `artifacts/metrics/cnn_validation_predictions.csv`
- `artifacts/figures/cnn_validation_confusion_matrix.png`

The cache command writes:

- `metadata/spectrogram_cache_manifest.csv`
- `metadata/spectrogram_cache.json`
- `data/processed/spectrogram_cache/`
- `artifacts/figures/spectrogram_previews/`

Cross-validation writes fold models and metrics under
`artifacts/cross_validation/`, together with `fold_assignments.csv`,
`out_of_fold_predictions.csv`, and `cross_validation_metrics.json`.

## Metrics and comparison rule

The evaluation output includes sensitivity, specificity, precision, negative
predictive value, accuracy, macro F1, ROC-AUC, PR-AUC, and Brier score for CNN
probabilities. Fold summaries include mean, standard deviation, and all fold
values.

The primary comparison is specificity while maintaining at least the configured
90% participant sensitivity. Do not choose a model from raw accuracy alone.
Only accept an architecture or augmentation change when the improvement is
consistent across grouped folds.

## Experiment sequence

1. `E0`: unchanged compact 40-mel CNN.
2. `E1`: 96-mel tensors with train-only frequency normalization.
3. `E2`: bounded waveform gain, shift, and noise.
4. `E3`: frequency and time masks.
5. `E4`: MixUp/CutMix.
6. `E5`: residual squeeze-and-excitation CNN.

Each ablation should use the same fold assignments. Disable only the relevant
configuration fields rather than creating different patient splits.

## Current limitation

The model still learns from window examples carrying a participant label, even
when a murmur may only be audible at one location or time. The scoring path
averages windows into recordings and recordings into linked participants, but
learned multi-instance attention is not part of this implementation yet. That
should be evaluated as a separate architecture after the new spectrogram
baseline is stable, because it changes both the training unit and deployment
interface.

