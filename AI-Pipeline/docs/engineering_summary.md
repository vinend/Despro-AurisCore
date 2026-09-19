# Engineering handoff — 2026-09-16

## Status

| Status | Scope |
|---|---|
| DONE | Heart PCG acquisition, immutable source verification, manifest, quality analysis, preprocessing, segmentation, features, participant splitting, SVM training, real evaluation, saved model, offline WAV screening, documentation and tests |
| PARTIALLY DONE | Overall AurisCore system: a working desktop Python reference exists; smartphone/hardware integration remains future work |
| BLOCKED | Nothing in this milestone; no manual dataset authentication/download was needed |
| NOT STARTED | CNN, INT8, TFLite, BLE firmware, Flutter, backend, WebRTC, lung and abdomen classifiers; deliberately outside this milestone |

## Current state before work

The workspace contained 30 proposal/report/documentation files and a document-generation script, with no executable PCG pipeline, dataset, tests, dependencies or root README. No `.git` directory was present; Git was unavailable on PATH. Python was only a Windows Store alias. Existing files are unchanged; see [inspection](repository_inspection.md). No commit or push was made.

## Datasets investigated and selection

- **CirCor DigiScope 1.0.3:** selected for real WAV recordings, explicit participant IDs/Additional IDs, usable murmur labels, location metadata, public original provenance and ODC-By-1.0 terms. The original license, annotations and metadata are preserved.
- **PhysioNet/CinC 2016:** investigated as a possible external-validation source, not downloaded or mixed into training. Final organizers' paper describes 764 training subjects and 3,153 recordings. Complete public participant linkage and uniform location metadata still need auditing before future use.

Sources, citations, terms, sizes, metadata and limitations are in [dataset comparison](datasets.md).

## Measured dataset statistics

- All **10,434 published source files** verified against PhysioNet SHA-256 checksums.
- **3,163 recordings**, **942 original subject IDs**, **872 linked independent participant groups**.
- All WAVs decode: mono, 4,000 Hz. No missing required annotations or exact file-hash duplicates.
- Duration: **20.0941 hours total**, mean 22.8703 s, median 21.456 s, range 5.152–64.512 s.
- Original-ID classes: 695 Absent, 179 Present, 68 Unknown.
- Recording classes: 2,391 Absent, 616 Present, 156 Unknown.
- Locations: AV 800, MV 861, PV 766, TV 732, Phc 4.
- Quality: 3,143 `ok`, 20 clipping flags; clipping-flagged recordings are retained with warnings.
- Excluded: 156 unknown-label recordings and 31 recordings from four groups with conflicting known visit labels.
- Baseline: **2,976 recordings**, **812 linked participants**, **22,819 windows**, **349 features/window**.
- Metadata, preprocessing and feature-extraction error logs have headers only: no errors in the real run.

| Partition | Independent participants | Original IDs | Recordings | Participants Absent / Present |
|---|---:|---:|---:|---:|
| Train | 568 | 601 | 2,070 | 458 / 110 |
| Validation | 122 | 132 | 448 | 98 / 24 |
| Test | 122 | 133 | 458 | 99 / 23 |

Some excluded unknown visits link to known visits in active partitions, so excluded-group counts must not be added to active counts as if disjoint. No excluded recording enters the model. Automated checks verified zero participant, group, recording or hash overlap between train, validation and test.

## Implementation completed

Original audio is never rewritten. Source TXT files supply identity and labels; quality measurements supply rate/duration/channel/RMS/clipping information. Additional IDs are linked transitively. Binary labels mean murmur absent versus present, never the separate clinical outcome.

DSP uses mono averaging, polyphase resampling to 8 kHz, DC removal, disabled-by-default conservative filtering, peak normalization and five-second windows with 50% overlap. MFCCs, deltas, log-mel, RMS, centroid, zero-crossing and temporal statistics yield 349 features. Window features are averaged per recording.

Seed 42 fixes a stratified participant split. Training uses `Pipeline(StandardScaler(), SVC(kernel='rbf', C=1, gamma='scale', class_weight='balanced'))`. No hyperparameter search or test-based model selection took place. Participant screening uses the mean recording decision margin with threshold zero. Margins are explicitly uncalibrated.

Every processed stage has manifest/configuration/code fingerprints and table hashes. Changed configuration or artifacts require regeneration. CLI stages give useful missing-data errors. Downloading is resumable and uses the official public S3 endpoint with PhysioNet fallback and checksum verification.

## Test and pipeline results

**21 pytest tests passed**, including synthetic end-to-end processing, saved-model inference, deterministic grouping/splitting, leakage failures, missing identity, corrupt/empty/nonfinite audio, silence/clipping, feature shape, resampling, checksum rejection and training-only scaling. Synthetic tests wrote only to temporary directories, with outputs explicitly marked `synthetic_smoke_only`.

The final suite emitted 14 nonfatal Matplotlib/Pyparsing deprecation warnings. `pip check` found no broken requirements. Compilation checks passed. A real-data run completed with status `real_data_evaluation`; subsequent provenance and leakage checks passed. The saved real model also successfully screened `2530_AV.wav` offline through `scripts/predict.py`.

## Actual model metrics

These are internal research screening results from local holdouts of the public release, not official hidden Challenge scores or clinical diagnostic accuracy.

| Evaluation unit | Accuracy | Precision | Sensitivity | Macro F1 |
|---|---:|---:|---:|---:|
| Validation participant (n=122) | 87.70% | 80.00% | 50.00% | 0.7711 |
| Test participant (n=122), primary | **90.16%** | **82.35%** | **60.87%** | **0.8206** |
| Test recording (n=458), secondary | 84.72% | 61.54% | 61.54% | 0.7600 |

Primary confusion matrix (rows true Absent/Present, columns predicted Absent/Present): `[[96, 3], [9, 14]]`. **Nine of 23 murmur-present test participants were missed.** The majority-Absent baseline would already achieve 99/122 = 81.15% accuracy, so accuracy alone is insufficient. The result needs clinician review and does not support deployment as a diagnostic system.

Full metrics: [baseline_metrics.json](../artifacts/metrics/baseline_metrics.json). Report: [baseline_results.md](baseline_results.md). Plot: [confusion_matrix.png](../artifacts/figures/confusion_matrix.png).

## Repository tree and files created

```text
README.md, .gitignore, requirements.txt, requirements-lock.txt, pyproject.toml
configs/
  heart_baseline.yaml
src/auriscore/
  __init__.py, config.py, io.py, acquisition.py, dataset.py, validation.py
  analysis.py, preprocessing.py, segmentation.py, features.py, splitting.py
  training.py, evaluation.py, inference.py, pipeline.py
scripts/
  _bootstrap.py, download_dataset.py, build_manifest.py, analyze_dataset.py
  preprocess_dataset.py, extract_features.py, train_baseline.py
  run_pipeline.py, predict.py
tests/
  conftest.py, test_audio.py, test_dataset.py, test_acquisition.py, test_smoke.py
data/
  external/README.md
  external/circor-heart-sound/1.0.3/  # Complete original release, ignored
  raw/.gitkeep, interim/.gitkeep
  processed/                       # Ignored arrays/features; .gitkeep tracked
    audio/*.npy, segments.csv, features.csv
    segments_provenance.json, features_provenance.json
metadata/
  dataset_manifest.csv, audio_validation.csv, metadata_errors.csv
  preprocessing_errors.csv, feature_errors.csv
artifacts/
  test_results.xml
  dataset_analysis/
    statistics.json, duplicates.csv, class_distribution.png
    duration_distribution.png, recordings_per_subject.png
    auscultation_location.png
  models/heart_svm.joblib           # Ignored; about 4.1 MB
  metrics/baseline_metrics.json, validation_predictions.csv, test_predictions.csv
  figures/confusion_matrix.png
docs/
  repository_inspection.md, datasets.md, dataset_report.md
  baseline_results.md, engineering_summary.md
.runtime/                          # Ignored local Python, packages and test scratch
```

The feature CSV is about 159 MB and is ignored by Git, as are source/processed data, runtime and model binaries. Existing `docs/ai_architecture/`, `tools/`, `terbaru/`, root DOCX/PDF files remain present.

**Files modified from the original workspace: none.** All implementation/report files above were newly created. New files were revised during implementation and testing. One abandoned partial archive created during this task was removed after the source-file download succeeded; no existing project work or original dataset file was removed.

## Commands executed

Main execution commands, run from the workspace root:

```powershell
# Inspection: rg --files, directory/extension inventory, Get-Content of existing sources.
# git status --short was attempted; Git is absent and there is no local .git directory.
# python --version was attempted; it resolved to the Windows Store alias.

# Local Python 3.12.10 embeddable archive and get-pip.py downloaded from official sources.
.runtime/python/python.exe .runtime/get-pip.py --no-warn-script-location
.runtime/python/python.exe -m pip install -r requirements.txt --no-warn-script-location --cache-dir .runtime/pip-cache
.runtime/python/python.exe -m pip freeze
.runtime/python/python.exe -m pip check
.runtime/python/python.exe scripts/run_pipeline.py --help
.runtime/python/python.exe -m compileall -q src scripts tests
.runtime/python/python.exe scripts/download_dataset.py
.runtime/python/python.exe -m pytest -q --basetemp .runtime/pytest-tmp --junitxml=artifacts/test_results.xml
.runtime/python/python.exe scripts/run_pipeline.py
.runtime/python/python.exe scripts/predict.py data/external/circor-heart-sound/1.0.3/training_data/2530_AV.wav

# Expected missing-data failure was verified separately:
.runtime/python/python.exe scripts/run_pipeline.py --root .runtime/no-data-check --config 'C:/Life/kuliah/Semester 6/DESPOR/configs/heart_baseline.yaml'
```

The full pipeline command executed all six processing/training stages. Additional read-only Python checks verified source hashes, source metadata counts, stage provenance and leakage. Initial archive downloading was stopped because it was slow; the official public S3 downloader resumed file acquisition successfully. A pre-evaluation pipeline run was restarted to correct excluded-group reporting; no model was selected using test performance.

## Known limitations, human action and next task

The data are from another device and predominantly young Brazilian screening participants. Participant labels weakly supervise individual locations/windows. No external validation, confidence calibration, learned signal-quality gate, heart-cycle segmentation or clinical validation exists. Exact hashes do not detect perceptual duplicates. A 4 kHz source resampled to 8 kHz gains no new signal content above 2 kHz. The phone/hardware path is documented but not integrated.

**Human action required to run this milestone: none in this workspace.** Use the available `.runtime/python/python.exe`; another computer needs Python and the documented dependency/dataset setup. The original license and attribution must accompany future dataset reuse. No Git initialization, commit or push was performed.

**Next recommended task:** review validation-set errors and the quality flags with the capstone/clinical supervisor, then design validation-only improvements or the CNN comparison. Preserve the recorded baseline and use a fresh or external evaluation plan for future model selection; do not optimize against these now-reported test outcomes.
