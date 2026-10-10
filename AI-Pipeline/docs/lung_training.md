# Lung training readiness — HF_Lung_V1

Implementation date: 2026-10-10. The user authorized development training. The
first local EXP-L001 launch stopped during preparation; no epoch/checkpoint was
saved. The user subsequently completed EXP-L002 on a Linux GPU server. Its
reported development metrics show weak discrimination/degenerate phase outputs;
the candidate remains research-only. No deployment decision or mobile readiness
exists. Preserve previous experiments and use fresh output directories.

## Data and target contract

Source: [HF_Lung_V1](https://gitlab.com/techsupportHF/HF_Lung_V1), pinned revision
`2a77d37230b1673d332645e6c6afeea29900bcf9`. Cite the authors' study
[PLOS ONE](https://doi.org/10.1371/journal.pone.0254134) and retain the downloaded
CC BY 4.0 license/disclaimer. Source archives are multipart 7z, not ZIP.
Both splits are downloaded, extracted and inventoried locally outside Git.
Official test TXT contents have not been parsed or used for selection.

Released labels are `I` (inhalation), `E` (exhalation), `D` (crackle), `Wheeze`,
`Rhonchi`, `Stridor`, with HH:MM:SS.sss timestamps. Six sigmoid outputs preserve
overlap. None is a disease diagnosis. Missing labels are not healthy patients.
Negative targets are supervised only inside annotated respiratory regions;
outside those regions only explicit positive events are supervised.

The audit assigns 4,770 train, 2,948 validation, 1,951 test and 96 quarantine
recordings. There are 118 official-training date groups and no remaining
train/test date-group conflicts. Dates are shifted grouping proxies, not verified
patient identifiers. Duplicate checks cover exact files and gain/DC-normalized
quantized PCM; this is not an exhaustive acoustic near-duplicate audit.

One upstream API SHA-256 declaration for train volume 005 disagreed with its
bytes. The bytes matched the pinned Git tree's blob identity. Receipts retain
both hashes and the verification basis; other parts use matching SHA-256 values.

Features: 8 kHz mono, 5-second windows, hop aligned to FFT frames near 50% overlap,
96-bin log-mel, FFT512/hop128, 20–1900 Hz, no filter or augmentation in the initial
baseline. Upsampling does not recover frequencies above the original 2 kHz
Nyquist limit. Tails and missing supervision are masked. Normalization and
positive weights are fitted within each training fold only.

Input pipeline `lung-cache-dataset-v2` shuffles the full list of TRAIN filenames
with a fold seed and a fresh permutation each epoch, then streams cache tensors.
Validation remains in stable order. Targets/masks stay attached to each feature
window; shuffling uses filename storage rather than buffering the full tensor
cache. Dataset batch cardinality is known and asserted; the final short batch is
retained. Both development and final fitting pass `shuffle=False` to Keras because
the input dataset already handles training order. This removes the ignored-shuffle
warning and unknown-cardinality end-of-data warning without infinite repetition,
dropping samples, or suppressing runtime errors. TensorFlow informational
rendezvous cleanup messages may still occur independently.

This is an input-order correction, not evidence of improved model quality.
Normalization, labels, split assignments, cache keys, class weights, model and
threshold selection rules are unchanged. Existing audited caches can be reused.
New experiment source.json records the input-pipeline version/shuffle policy;
compare fresh development runs against EXP-L002, keeping official test sealed.

## Commands and authorization

Run from AI-Pipeline with its Python environment. Install optional acquisition
dependency using `python -m pip install -e ".[lung-data]"` if needed.

```powershell
python scripts/download_lung_dataset.py --split train
python scripts/download_lung_dataset.py --split test
python scripts/build_lung_manifest.py
python scripts/preprocess_lung_dataset.py
python scripts/train_lung_cnn.py --cache data/processed/lung/cache/<config-digest>
```

The last command is preflight only. It checks cache/source/audit identity and
split integrity without importing TensorFlow or fitting weights. Current cached
data contain 46,308 windows from 7,718 development recordings. Preprocessing is
complete; the source files were rehashed after completion and preflight passed.
The cache key is `fa2fc598295d3e8b71d8e34cee4ecc7c21866cb658f57367ca9aa5ff546cee14`.

Development fitting is now authorized. Final fitting and opening the official
test remain separate selection/authorization steps.

```powershell
python scripts/train_lung_cnn.py --cache <cache> --output results/EXP-L002-temporal-cnn --authorized-training
python scripts/evaluate_lung_development.py --experiment results/EXP-L002-temporal-cnn --output results/EXP-L002-development.json
python scripts/train_lung_cnn.py --cache <cache> --final-selection <selection.json> --output results/EXP-L003-final --authorized-training
python scripts/evaluate_lung_holdout.py --candidate results/EXP-L003-final --model-version lung-L003 --open-sealed-test
python scripts/prepare_lung_deployment.py --help
```

Selection JSON explicitly contains `role` (`train_only_oof` or
`development_validation`), exact `config`, development `index_sha256`, fixed
integer `epochs`, class-order `thresholds`, and `postprocessing` with
`minimum_s`/`merge_gap_s`. Freeze these after development review. Final fitting
uses all development groups, fixed epochs and no official-test callbacks.
Holdout evaluation writes a dataset-level exclusive opening receipt, rejects
repeat evaluation, merges overlapping frames and saves frame counts/AUC,
one-to-one event boundary/duration metrics and reference/predicted respiratory
measurements per recording/date/device. A failed opening also remains recorded;
review it rather than deleting the receipt to tune/retry against test labels.

The initial executable baseline is one temporal CNN with independent sigmoid
outputs for phases and acoustic events. `classes` can select separately versioned
phase-only or acoustic-only experiments; rebuild each configuration's cache.
The model builder also exposes a pooled research architecture, but this trainer
uses temporal outputs. CNN-GRU, augmentation, uncertainty analysis and candidate
comparisons remain development experiments after authorization, not established
performance. No automatic experiment queue or auto-resume launches training.

For a foreground PowerShell run on this prepared machine, activate the Python
environment containing TensorFlow and run from AI-Pipeline:

```powershell
$cache = (Get-Content data/processed/lung/readiness.json -Raw | ConvertFrom-Json).cache
python -u scripts/train_lung_cnn.py --cache $cache --output results/EXP-L002-temporal-cnn --authorized-training
```

Keep that PowerShell window open until completion. The run uses CPU on the current
native-Windows environment, up to 50 epochs with early stopping patience eight.
Results include status.json, fold-0/history.csv, best.weights.h5 and model.keras
when those stages finish. Existing output directories are never overwritten;
choose a fresh experiment ID after interruption. Source data/caches/models and
local launch records are excluded from Git. On a new machine acquire/preprocess
the dataset before using readiness.json.

## Activation and limits

A final package needs exact hashes for weights, normalization, configuration,
locked-test evidence and an explicit engineering decision specifying per-class
eligibility gates. Research models are not automatically promoted. Use
`AURISCORE_LUNG_PACKAGE` to register a verified package in the existing worker.
Missing/ineligible packages produce structured unavailable results.

The UI accepts Lung WAV files and 30-second network recordings. Valid Lung audio
must be at least five seconds; respiratory calculations also require three
complete unambiguous cycles. Rate, phase durations and I:E remain null otherwise.
Frame scores are uncalibrated scores, not clinical probabilities.

TFLite conversion is available as an explicit helper; INT8 requires TRAIN-only
representative tensors. Conversion, parity, resource benchmarking and physical
ESP32 validation must follow actual candidate training before mobile readiness
can be claimed. No Lung package is active now.
