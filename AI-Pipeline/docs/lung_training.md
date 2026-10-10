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

### EXP-L004: validation-plateau learning-rate experiment

EXP-L003 completed on the Linux GPU server. Its best reported validation loss
was 0.8388 at epoch 2; training loss continued falling while validation loss
rose. The next one-factor experiment adds LR reduction, keeping the temporal
CNN, supervision, splits, cached features, initial LR 0.001, maximum 50 epochs
and early-stopping patience eight unchanged. This may improve optimization;
it does not guarantee more epochs or better generalization.

`configs/lung_training_plateau.json` is a training-only policy: halve LR after
two epochs without improved validation loss, with a floor of 0.000001. Reduction
runs before early stopping. Best validation weights are still restored and
checkpointed. `source.json` records the policy and file hash; `history.csv`
records `learning_rate` used in each epoch and `next_learning_rate` after any
reduction. Omit `--training-policy` to reproduce the constant-LR baseline.
The policy does not alter the immutable cache configuration or localization
provenance. No preprocessing or dataset download is needed for an existing cache.

After syncing this code to Linux, run from AI-Pipeline with the existing venv:

```bash
source .venv/bin/activate
CACHE=data/processed/lung/cache/fa2fc598295d3e8b71d8e34cee4ecc7c21866cb658f57367ca9aa5ff546cee14
python scripts/train_lung_cnn.py --cache "$CACHE" \
  --training-policy configs/lung_training_plateau.json
mkdir -p artifacts/lung-launch
set -o pipefail
python -u scripts/train_lung_cnn.py --cache "$CACHE" \
  --training-policy configs/lung_training_plateau.json \
  --output results/EXP-L004-temporal-cnn-plateau --authorized-training \
  2>&1 | tee artifacts/lung-launch/EXP-L004.log
python -m json.tool results/EXP-L004-temporal-cnn-plateau/status.json
python -m json.tool results/EXP-L004-temporal-cnn-plateau/fold-0/evaluation.json
```

The first Python command is preflight only. The second starts training; choose
a fresh experiment ID if the output directory already exists. Compare development
class-wise discrimination and localization against EXP-L003 before choosing
another change. Keep the official test sealed and candidates research-only.

Training prints timestamped UTC process events with elapsed seconds to stderr,
alongside the existing Keras/TensorFlow output. These cover preflight, visible GPU
names or CPU fallback, fold window/group counts and seed, TRAIN-only normalization
progress and positive weights, model input shape, epoch/batch progress, validation
start, losses, used/next LR, best epoch/loss, early-stop counter, best-checkpoint
saves and restored weights. GPU visibility does not prove every operation runs
on GPU. Saved-development prediction progress, threshold selection, per-class
metrics, artifact paths, completion and failures are also logged. Final fitting
logs fixed-epoch progress without introducing validation or test callbacks.

Each created experiment automatically saves structured events to `process.jsonl`;
`history.csv`, `history.json` and `status.json` retain their existing roles. Preflight
events before experiment creation and raw TensorFlow messages are console-only;
the `2>&1 | tee ...` command above captures the full console, including tracebacks.
Use `--progress-interval 10` on the training command for more frequent batch/window
updates (default 30 seconds). First/last items and all epoch boundaries always
print. Logging changes do not alter model fitting, splits or threshold selection.

If this protocol is later selected for final all-development fitting, selection
JSON must include the normalized `training_policy` from source.json and a
`learning_rates` list containing the first selected `epochs` values from the
development history's `learning_rate` column (through the selected best epoch,
not the trailing early-stopping epochs). Freeze the chosen fold/schedule along
with epochs and thresholds. Final fitting replays these fixed rates without
validation callbacks or test monitoring; a plateau selection missing the frozen
rates is rejected. Existing constant-LR selections remain supported.

### EXP-L005: stronger dropout, compared with EXP-L003

The user-reported EXP-L004 history confirms LR reductions after epochs 4/6/8/10,
early stopping at epoch 10 and restoration of epoch 2 (validation loss 0.8355).
No reduced-LR epoch improved the selected checkpoint; metric differences from
EXP-L003 cannot be attributed to the later reductions. More epochs alone are
not supported by that result.

`configs/lung_training_dropout.json` defines `lung-training-policy-v2`: explicit
model dropout 0.4 instead of the historical 0.2, and constant LR 0.001. Compare
with the fixed-LR EXP-L003 baseline so dropout is the sole changed factor.
Convolution widths/context, weighted masked loss, normalization, supervision,
split, seed, batch size, maximum epochs (50), early stopping (eight) and threshold
selection stay fixed. The preprocessed cache can be reused. V1 policies and
omitted policies preserve dropout 0.2. The policy/hash and process logs record
dropout; the serialized model retains its rate. A future final selection must
freeze the v2 policy to reproduce the selected dropout. No research candidate
is activated automatically. Increased dropout is a hypothesis, not evidence of
better quality or more useful epochs.

After syncing the updated code, run from AI-Pipeline on Linux:

```bash
source .venv/bin/activate
CACHE=data/processed/lung/cache/fa2fc598295d3e8b71d8e34cee4ecc7c21866cb658f57367ca9aa5ff546cee14
python scripts/train_lung_cnn.py --cache "$CACHE" \
  --training-policy configs/lung_training_dropout.json
mkdir -p artifacts/lung-launch
set -o pipefail
python -u scripts/train_lung_cnn.py --cache "$CACHE" \
  --training-policy configs/lung_training_dropout.json --progress-interval 10 \
  --output results/EXP-L005-temporal-cnn-dropout --authorized-training \
  2>&1 | tee artifacts/lung-launch/EXP-L005.log
```

Keep a fresh output directory and compare per-class ROC/PR AUC, F1, sensitivity,
specificity and localization metrics on development data. Do not select solely
for epoch count. Official test stays sealed. This implementation did not start
training; the second command above explicitly starts it on the Linux machine.

Temporal checkpoint outputs are available now through the research WAV and
saved-development localization commands. Existing temporal checkpoints need no
retraining to produce onset/offset candidates. See
[Lung temporal localization](lung_localization.md) for exact Linux commands,
frame-grid limitations and the versioned approved-package path.

### Development diagnostics without another training run

`scripts/diagnose_lung_development.py` audits all cached development windows,
TRAIN-only positive weights, masks/tails, phase target overlap, label durations
and device-specific prevalence. With `--experiment` it additionally reads saved
development predictions and reports positive/negative score quantiles and
histograms, phase prediction conflicts and F1 gain over an always-positive
baseline at the already selected thresholds. It does not load a model, fit
weights, select new thresholds or open official test labels. The experiment must
have development-only provenance matching the cache/config/audit. Counts include
overlapping windows, as in the development evaluator; they are not independent
patient observations. Outputs are new files outside existing experiment folders.

From AI-Pipeline on the Linux training machine:

```bash
python scripts/diagnose_lung_development.py \
  --cache data/processed/lung/cache/fa2fc598295d3e8b71d8e34cee4ecc7c21866cb658f57367ca9aa5ff546cee14 \
  --experiment results/EXP-L003-temporal-cnn \
  --output artifacts/lung-launch/EXP-L003-diagnostics.json
```

Omit `--experiment` for cache-only inspection. The Windows checkout does not
contain the Linux EXP-L003 prediction file, so its score distributions cannot
be inferred from the pasted confusion matrices. Preserve the existing cache and
experiment files while investigating.

See [the EXP-L003 inspection](lung_diagnostics_findings.md) for measured cache
support, baseline comparisons, phase overlaps and the proposed research sequence.

Interpretation limits: the [dataset paper](https://doi.org/10.1371/journal.pone.0254134)
describes D labels as periods containing crackles, not individual explosive
clicks. It also permits omitting unclear sounds. The manifest's
`annotation_coverage_verified` flag currently follows successful parsing and
the absence of manifest problems; it is not an independent completeness review.
Treat negative supervision inside annotated respiration as an explicit research
assumption pending annotation review. Do not silently relabel unannotated audio.
Independent phase sigmoids permit concurrent inhalation/exhalation predictions;
any exclusive head needs an overlap/boundary policy established first. The
baseline's three temporal 3-wide convolutions plus one 5-wide convolution see
11 feature frames (224 ms including the 64-ms FFT), not the full five-second
window. Longer temporal context is a candidate development experiment, not an
established fix or an automatic training launch.

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
