# AurisCore AI Pipeline

AurisCore is a university capstone cyber-physical stethoscope research prototype. The intended acquisition path is body sound → MEMS microphone/analog front-end → ESP32-S3 (mono ADC near 8 kHz) → BLE → smartphone → offline signal processing and AI → clinical decision support. Heavy AI processing belongs on the phone for the current design. Optional backend/tele-auscultation comes later.

This folder contains the executable **heart-sound/PCG dataset pipeline, SVM baseline, and optional spectrogram CNNs in Python**. It covers dataset acquisition, validation, preprocessing, feature extraction, model training, participant-exclusive cross-validation, validation-only threshold selection, saved-model inference, and a sealed final-holdout workflow. Heart-only model scope allows provenance, signal processing and participant separation to be verified before adding other modalities. Lung and abdomen classifiers, embedded firmware, live-stream inference, and production mobile integration are not implemented here.

Current Heart status (2026-10-09): the CPU-only Rhythm/Cardiac Event DSP prototype emits `heart-analysis-v1` and has synthetic engineering tests; labeled-recording validation remains open. H014 is the historical frozen external-validation Murmur benchmark. H021 is the strongest TRAIN-only Murmur OOF result (117 FP, 11 FN at sensitivity 0.90), but no final deployment model exists. H022 is protocol-locked and preflight-ready; training has not started. External validation and sealed test remain closed. See [AI_PIPELINE.md](../AI_PIPELINE.md) for experiment history. The Windows WebApp demo consumes WAV and mock/WebSocket PCM through the same Heart service; physical BLE is unverified.

Historical SVM run (2026-09-16): **21 tests passed**; the real CirCor pipeline completed with 22,819 windows and 349 features. Participant test sensitivity was **60.87%** (9 of 23 positive participants missed), despite 90.16% accuracy. That test result has already been inspected and is now treated as development history, not an untouched holdout. See the [engineering handoff](docs/engineering_summary.md) and [historical baseline results](docs/baseline_results.md).

The first real-data compact CNN development run completed on 2026-10-03 using the restored local CirCor source audio. Its linked-participant validation recall was **91.67%**, positive-class F1 was **40.37%**, and specificity was **35.71%** at the validation-selected threshold. These are screening research results, not final-holdout or clinical results. See the [real CNN training report](docs/heart_cnn_real_training.md) and its saved JSON/CSV/PNG artifacts. The earlier 2026-09-19 software verification had 25 passing tests but no real CNN run at that time.

Research screening only. Outputs are not confirmed diagnoses. Neither a murmur-absent screening result nor a decision margin rules out disease. Every screening result requires clinician review; no clinical validity is claimed.

## Existing work and structure

Earlier proposals and the architecture document generator are preserved. Some historical documents discuss Wi-Fi/TinyML alternatives; the architecture above governs this milestone. See [initial inspection](docs/repository_inspection.md).

```text
configs/heart_baseline.yaml       SVM baseline and 8 kHz signal contract
configs/heart_cnn.yaml            Log-mel CNN training settings
configs/heart_spectrogram_cnn.yaml Residual spectrogram CNN and augmentation settings
src/auriscore/                    Acquisition, DSP, splits, SVM/CNN, thresholds, holdout, inference
scripts/                          Stages, model training, holdout locking/evaluation and WAV screening
tests/                           Unit, leakage and synthetic end-to-end tests
data/external/                    Unchanged original release and license (ignored)
data/raw/                        Reserved for future device captures (ignored)
data/interim/                    Reserved for intermediate data (ignored)
data/processed/                  Arrays, window index and feature table (ignored)
metadata/                       Manifest, quality checks and error logs
artifacts/dataset_analysis/      Measured statistics, duplicates and plots
artifacts/models/               Saved sklearn pipeline (ignored)
artifacts/metrics/              Metrics and held-out predictions
artifacts/figures/              Participant confusion matrix
docs/                          Reports, dataset research and existing architecture documents
tools/, terbaru/, *.pdf, *.docx  Preserved previous work
```

## Environment

Use Python 3.12 (tested); 3.11–3.13 are allowed by package metadata.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

For CNN training, install the optional TensorFlow environment instead:

```powershell
python -m pip install -r requirements-cnn.txt
```

To run the measured training notebook, install the notebook environment and
launch JupyterLab:

```powershell
python -m pip install -r requirements-notebook.txt
python -m jupyter lab notebooks/spectrogram_cnn_measured_training.ipynb
```

The notebook runs complete real-data preprocessing and training by default,
then exports plots plus JSON and Markdown reports under
`artifacts/notebook_report/`. Five-fold grouped cross-validation is available
through a separate notebook flag and is off by default because it trains five
additional models.

On Linux/macOS activate with `source .venv/bin/activate`. Source-tree scripts work without package installation; `python -m pip install -e .` is optional. Direct dependencies are pinned in `requirements.txt`; `requirements-lock.txt` records the complete tested environment. To reproduce transitive versions, install with `python -m pip install -r requirements-lock.txt`.

On this Windows workspace, an ignored local Python runtime is also available: replace `python` with `.runtime\python\python.exe`. This avoids requiring a system-wide installation. It is a local convenience, not a tracked dependency.

### WSL2 NVIDIA GPU environment

The WSL2 GPU environment uses Python 3.13 and TensorFlow **2.20.0**. Install
its dependencies with `uv pip` from the `AI-Pipeline` directory:

```bash
~/.local/bin/uv pip install --python ~/.venvs/auriscore-gpu-tf220/bin/python -r requirements-gpu-wsl.txt
~/.local/bin/uv pip install --python ~/.venvs/auriscore-gpu-tf220/bin/python --no-deps -e .
~/.venvs/auriscore-gpu-tf220/bin/python -c 'import tensorflow as tf; print(tf.__version__, tf.config.list_physical_devices("GPU"))'
```

`requirements-gpu-wsl.txt` pins `tensorflow[and-cuda]==2.20.0` alongside the
Heart pipeline dependencies. The older `requirements-cnn.txt` and `cnn` /
`notebook` extras still pin TensorFlow 2.21.0 for the historical Windows setup;
do not install them into this WSL environment. `scripts/launch_training_queue.ps1`
is a Windows launcher. WSL commands should use the virtual environment's
Python directly and a distinct experiment name for any new GPU control run so
H001–H007 remain intact.

The isolated H006 GPU migration control has a read-only preflight:

```bash
~/.venvs/auriscore-gpu-tf220/bin/python scripts/train_h006_gpu_control.py
```

It compares the saved H006 configuration, development rows and participant
membership, saved per-frequency statistics, model and compile configuration,
and validation threshold policy. The control forces legacy non-JIT compilation
and the original `EarlyStopping(val_loss, patience=8,
restore_best_weights=True)` path. It does not change the managed experiment
queue or read the sealed holdout. When explicitly authorized, launch it with
`bash scripts/launch_h006_gpu_control.sh`; the launcher prints a PID and writes
`.runtime/h006-gpu-control.stdout.log` and `.stderr.log`. Like original H006,
this control is not resumable after interruption; use a new name for a retry.

The H009 WSL GPU experiment uses the normal resumable managed callbacks. Its
one-factor specification is `configs/heart_h009_gpu.json`: it copies H008's
saved per-frequency normalization and changes only the architecture to the
Residual-SE model used by H005. Audit without training, then launch when
authorized:

```bash
~/.venvs/auriscore-gpu-tf220/bin/python scripts/train_h009_gpu_experiment.py
bash scripts/launch_wsl_gpu_experiment.sh cnn-per-frequency-residual-se scripts/train_h009_gpu_experiment.py --run
```

The reusable WSL launcher uses a user `systemd` service so training survives
the terminal session. It prints the service MainPID and writes
`.runtime/cnn-per-frequency-residual-se.stdout.log` and `.stderr.log`.
H009 forces non-JIT compilation to match H008's GPU control while retaining
the managed `CSVLogger`, `ModelCheckpoint`, and `BackupAndRestore` callbacks.
The H009 trainer reads only development rows for fitting and visualization.

H010 tests one change against H008: compact-CNN dropout 0.30 to 0.50, as in
H002. Its specification is `configs/heart_h010_gpu.json`. The default command
audits H002, H008, the completed H009 prerequisite, development split, saved
normalization statistics, model compilation, and GPU without training:

```bash
~/.venvs/auriscore-gpu-tf220/bin/python scripts/train_h010_gpu_experiment.py
bash scripts/launch_wsl_gpu_experiment.sh cnn-per-frequency-dropout-050 scripts/train_h010_gpu_experiment.py --run
```

The launcher writes `.runtime/cnn-per-frequency-dropout-050.stdout.log` and
`.stderr.log`. H010 uses the managed checkpoint path and can resume an
interrupted incomplete run in its existing experiment directory.

H011 applies the exact H003 conservative augmentation policy to H008's
per-frequency configuration. Its specification is `configs/heart_h011_gpu.json`.
Waveform gain/shift/noise and spectrogram masks run only for training windows;
validation preprocessing remains unaugmented. Audit or launch it with:

```bash
~/.venvs/auriscore-gpu-tf220/bin/python scripts/train_h011_gpu_experiment.py
bash scripts/launch_wsl_gpu_experiment.sh cnn-per-frequency-conservative-augmentation scripts/train_h011_gpu_experiment.py --run
```

The managed run writes `.runtime/cnn-per-frequency-conservative-augmentation.stdout.log`
and `.stderr.log`, plus its own resumable `results/EXP-H011-*` directory.

## Dataset and target

The sole primary dataset is [CirCor DigiScope 1.0.3 on PhysioNet](https://physionet.org/content/circor-heart-sound/1.0.3/), licensed under **Open Data Commons Attribution 1.0**. Cite Oliveira et al. (2022), DOI `10.13026/tshs-mw03`, and the source article DOI `10.1109/JBHI.2021.3137048`. Keep the original license and attribution with derived data. See [dataset comparison, terms and citations](docs/datasets.md).

The public release contains 3,163 recordings and 942 original subject IDs. The pipeline measures independent participant groups using Additional ID links; these counts must not be confused with the full research cohort. PhysioNet 2016 was investigated but is not combined with CirCor.

Target: **murmur Absent (0) versus Present (1)**. Unknown labels are retained in the manifest and excluded from training/evaluation. Clinical outcome is a separate preserved field, never a feature or target. Positive participant labels can include recordings at sites without audible murmur; this baseline explicitly uses weak recording-level supervision.

```powershell
python scripts/download_dataset.py
python scripts/run_pipeline.py
# Or acquire and run together:
python scripts/run_pipeline.py --download
```

The default complete run trains the SVM. To build the same 8 kHz processed windows and train the CNN:

```powershell
python scripts/run_pipeline.py --config configs/heart_cnn.yaml
# Or, after preprocessing with that same configuration:
python scripts/train_cnn.py
```

### Independent Heart CNN experiment queue

The canonical real-data CNN path is `configs/heart_cnn_queue.json` with one
named experiment per directory. From `AI-Pipeline` on Windows, start it without
keeping a Codex session open:

```powershell
.\scripts\launch_training_queue.ps1
```

The launcher prints the PID and writes `.runtime/training-queue.stdout.log`
and `.runtime/training-queue.stderr.log`. It starts one queue process; the queue
runs experiments sequentially and waits for pre-existing CNN trainers to exit.
Launching the same queue again while it is active returns the existing PID.
These commands inspect artifacts without starting training:

```powershell
.runtime\python\python.exe scripts\training_status.py
.runtime\python\python.exe scripts\summarize_experiments.py
.runtime\python\python.exe scripts\run_experiment_queue.py --dry-run
```

To run one queued experiment in the foreground when explicitly desired, use
`.runtime\python\python.exe scripts\run_experiment_queue.py --only cnn-dropout-050`.
The queue skips completed runs and resumes a managed interrupted run in its
existing directory. Each managed experiment writes `status.json`, `history.csv`,
`checkpoints/backup/`, per-epoch best checkpoints, `best_model.keras`, metrics,
predictions and PNG reports. Keras `BackupAndRestore` saves model and optimizer
state at each completed epoch; `CSVLogger` and `ModelCheckpoint` preserve the
history and best validation-loss model. A killed epoch can be repeated, while
completed epochs are retained. Resume preserves optimizer state but may replay
a different shuffle/augmentation sequence after restart. Runs started before
this checkpoint feature cannot recover their training state if interrupted.
Use a new experiment name after changing configuration or prepared data.

`scripts/run_experiment_queue.py --migrate-only` adds `status.json` and
`best_model.keras` for already completed legacy runs without training. The
compact status command does not parse Keras logs. The summary command prints
completed validation metrics and regenerates `results/experiment_comparison.png`
and `.csv` for runs with identical evaluation conditions. Neither command
evaluates the sealed final holdout.

For the improved float-spectrogram pipeline, residual CNN, training-only
augmentation, cache/QC previews, and grouped development cross-validation:

```powershell
python scripts/run_pipeline.py --config configs/heart_spectrogram_cnn.yaml
python scripts/cache_spectrograms.py --config configs/heart_spectrogram_cnn.yaml --previews 12
python scripts/train_cnn_cv.py --config configs/heart_spectrogram_cnn.yaml
```

See the [spectrogram CNN implementation and experiment protocol](docs/spectrogram_cnn.md).

Download uses PhysioNet's officially advertised public S3 endpoint, bounded concurrent connections, retries and published SHA-256 verification. Roughly 559 MB of source data is downloaded; allow several GB for runtime, processed audio and features. Interrupted downloads can be resumed by rerunning. Existing source files are never replaced; changed originals cause a clear failure. Manual download instructions are in [data/external/README.md](data/external/README.md). Missing data produces an actionable message and exit code 2; it does not generate invented metrics.

## Stages and manifest

```powershell
python scripts/build_manifest.py
python scripts/analyze_dataset.py
python scripts/preprocess_dataset.py
python scripts/extract_features.py
python scripts/train_baseline.py
```

All commands accept `--config configs/heart_baseline.yaml` and `--root <repository>`. Paths in configuration and manifests are relative to the repository root. The manifest records:

| Fields | Meaning |
|---|---|
| dataset_source, subject_id, recording_id, file_path | Original provenance and repository-relative audio path |
| label, murmur_label, outcome_label | Explicit murmur target, original murmur label and separate outcome |
| auscultation_location, original_sampling_rate, duration_sec | Source site and measured audio properties |
| split, license, notes | Assigned partition, usage attribution and exclusions/errors |
| additional_id, subject_group | Original repeat-visit link and canonical transitive participant group |
| sha256, quality_flag | Original file digest and engineering quality warnings |

Missing metadata stays blank. Missing identities are flagged; splitting fails rather than assuming independence. Decoding failures, empty audio, NaN/Inf, channels, duration, sampling rate, RMS and clipping ratio are logged per file. Duplicate hashes are reported. Invalid/silent files and unknown labels are excluded; other quality flags remain available for review. The clipping threshold is absolute amplitude ≥0.999, flagged when more than 1% of samples reach it; silence RMS <1e-7. These are engineering defaults.

## Signal processing and leakage prevention

Audio is converted to mono, polyphase-resampled to 8 kHz, DC-centered, optionally filtered, peak-normalized and segmented into 5-second windows with 50% overlap. Filtering is **off** by default; the optional 20–2000 Hz second-order Butterworth band follows the PDS signal range but remains an engineering choice, not a medically validated constant. A recording shorter than five seconds gets one zero-padded window with its valid sample count retained. Incomplete tails of longer recordings are discarded.

Features include 13 MFCCs, 13 delta MFCCs, 40 log-mel bands, RMS, spectral centroid and zero-crossing rate, summarized by mean/std/median/min/max, plus four amplitude/temporal statistics: **349 features** per window. Mel features stop at 2 kHz because upsampling the 4 kHz source cannot create higher-frequency information. Windows are averaged into one feature vector per recording before training.

Before segmentation, subject IDs and Additional IDs are linked transitively. Seed 42 creates stratified 70/15/15 train/validation/test participant splits. All recordings from a linked participant stay together; inconsistent linked-visit binary labels are excluded. Automated checks fail on overlap of subjects, linked groups, recording IDs or exact file hashes across splits. Feature provenance binds each stage to the manifest and configuration; rerun upstream stages if either changes.

The SVM remains an sklearn `Pipeline(StandardScaler, SVC)` comparison baseline. The legacy CNN consumes normalized log-mel windows and uses three compact convolution blocks. The opt-in spectrogram CNN supports log-mel or log-STFT tensors, train-only normalization, bounded audio and spectrogram augmentation, MixUp/CutMix, a residual squeeze-and-excitation architecture, participant-balanced window weights, and validation-loss early stopping. Both models aggregate recording scores into one linked-participant score. Their screening threshold is selected only on validation participants, targeting the configured sensitivity before maximizing specificity. Training and cross-validation never evaluate the final holdout.

The historical CirCor test split is marked `legacy_exposed` and cannot be relabelled as untouched by the locking command. A genuine final evaluation requires newly collected AurisCore device data or a separately governed external cohort. After its membership and source hashes are fixed, set `holdout_status: locked_unseen`, run `python scripts/lock_holdout.py --config <config>`, freeze the model and threshold, and run `python scripts/evaluate_holdout.py --config <config> --model <model>` once. The evaluator refuses changed membership and refuses to overwrite an existing final result. See the [final evaluation protocol](docs/evaluation_protocol.md).

## Outputs and offline screening

- [Dataset report](docs/dataset_report.md): measured counts, distributions, quality, missing values, duplicates and split statistics.
- [Baseline results](docs/baseline_results.md): real evaluation status, model settings, metrics and limitations.
- [Real Heart CNN training](docs/heart_cnn_real_training.md): restored data provenance, Python/TensorFlow environment, participant-exclusive splits, real validation metrics, and reproducible commands.
- `metadata/dataset_manifest.csv`, `metadata/audio_validation.csv`, `metadata/*_errors.csv`.
- `data/processed/audio/*.npy`, `segments.csv`, `features.csv`, stage provenance JSON.
- `artifacts/dataset_analysis/`: distribution PNGs, statistics JSON and duplicates CSV.
- `artifacts/models/heart_svm.joblib` or `heart_cnn.keras` plus `heart_cnn.json` metadata.
- Validation metrics/predictions and validation confusion matrices. Final holdout files appear only after the explicit one-time evaluation command.
- `results/EXP-HNNN-name/`: immutable per-run `config.json`, `metrics.json`,
  `predictions.csv`, the saved model, and report PNGs. CNN runs additionally
  include `history.csv`, `training_history.png`, actual tensor examples in
  `sample_tensors.npz`, spectrogram and waveform PNGs. The training plots show
  train/validation class counts; sealed test counts are deferred until the
  one-time final evaluation. SVM decision margins are uncalibrated, so their
  precision-recall plot uses margins and no ROC PNG is rendered. CNN ROC/PR
  plots use sigmoid scores when both validation classes exist.
- `results/experiment_comparison.png` and `.csv` appear after at least two runs
  have matching validation participants, labels, threshold policy and method.
  Cross-validation folds each receive a run directory; out-of-fold evaluation
  also receives its own directory and is compared only with matching fold
  assignments.
- To select an improved candidate for slides, run
  `python scripts/summarize_experiments.py --baseline EXP-H001-cnn-compact --best EXP-H00N-cnn-variant`.
  This writes `results/summary/` only when positive-class F1 improved under
  the same validation methodology. It copies available best-candidate plots
  and writes `baseline_vs_best.png` plus its numerical CSV. A new selection
  cannot replace an existing summary silently.
- The one-time locked holdout writes count/normalized confusion matrices,
  eligible score curves and full split class counts to
  `results/final-holdout-<digest>/`, alongside JSON/CSV results.

```powershell
python scripts/predict.py path/to/recording.wav
python scripts/predict.py path/to/recording.wav --model artifacts/models/heart_cnn.keras
```

Inference returns a murmur screening result, quality flags and the validation-locked threshold. SVM margins and CNN sigmoid scores are **not calibrated clinical probabilities**. Invalid/silent audio yields “unable to screen.” Only load trusted locally generated model artifacts.

## Tests and limitations

`python -m pytest -q` covers audio loading, mono conversion, resampling, segmentation, feature shape, deterministic splitting, leakage, repeat identities, unknown exclusion, corrupt/empty/nonfinite audio, manifest validation and a synthetic end-to-end smoke run. Synthetic test artifacts stay in temporary directories, are explicitly labeled, and provide no evidence of screening performance.

CirCor's cohort/device/environment may differ substantially from future AurisCore recordings. Participant labels are not precise window labels. No heart-cycle segmentation, learned quality gate, calibrated confidence, external validation, prospective evaluation or clinical validation is implemented. File hashes detect exact byte duplicates, not acoustically similar recordings. The internal held-out test is not the official Challenge hidden test. Longer windows do not increase independent participant count. This milestone provides a desktop Python reference, not a deployed smartphone model.

## Roadmap

1. Heart PCG dataset pipeline.
2. SVM baseline.
3. Train and compare the implemented CNN baseline on the complete development cohort.
4. Acquire and lock a genuinely new AurisCore/external holdout.
5. CNN INT8 quantization and TensorFlow Lite smartphone inference.
6. ESP32-S3 BLE integration.
7. Flutter application integration.
8. Lung mode.
9. Abdomen mode.

Before reporting CNN performance, review validation errors and quality exclusions with the project team. Do not inspect the future final holdout until architecture, preprocessing and threshold policy are frozen.
