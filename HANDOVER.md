# AurisCore AI Pipeline — Engineering Handover Document (HANDOVER.md)

**Project:** AurisCore Digital Stethoscope (Assistive Acoustic Screening System)  
**Repository:** `https://github.com/vinend/Despro-AurisCore.git`  
**Current Active Feature Branch:** `feat/abdomen-ai`  
**Status Date:** 2026-10-07  

---

## 1. Executive Summary & Medical Principles

AurisCore is a digital stethoscope research prototype with three auscultation domains:
1. **Heart (Phonocardiogram - PCG):** Primary priority.
2. **Abdomen (Bowel Sounds / Gastrointestinal):** Active development on `feat/abdomen-ai`.
3. **Lung (Respiratory Sounds):** Planned on separate branch `feat/lung-ai`.

### Medical Safety & Evaluation Mandates:
* **Assistive Screening Only:** Output must strictly use language such as `Normal / Abnormal`, `Possible abnormal acoustic pattern`, `Assistive screening result`. Never emit definitive clinical diagnoses or treatment recommendations.
* **Recall / Sensitivity First:** For clinical screening, target sensitivity is $\ge 90\%$ to minimize false negatives (missed abnormal cases).
* **Sealed Holdout:** Test sets must remain uninspected during training and hyperparameter tuning. All decisions use linked-participant validation splits.

---

## 2. Current Progress & Milestones

### A. Heart AI Status (`master`)
* **Dataset:** PhysioNet CirCor DigiScope 1.0.3 (3,163 recordings, 942 subject IDs, 8,000 Hz mono).
* **Completed Batch:** `EXP-H001` through `EXP-H007` in `AI-Pipeline/results/`.
* **Current Best Model:** `EXP-H006-cnn-per-frequency-normalization` (Sensitivity: **91.67%**, Specificity: **71.43%**, Macro F1: **0.7091**, Positive F1: **0.5946**, ROC-AUC: **0.8852**, PR-AUC: **0.7793**).

### B. Abdomen AI Status (`feat/abdomen-ai`)
* **Dataset:** Figshare Bowel Sounds 1.0 (`data/external/bowel-sounds/`, 14 files, 7 long continuous recordings, CC BY 4.0).
* **Preprocessing:** Resampled to 8,000 Hz, 4th-order Butterworth bandpass filter $100 - 1.000\text{ Hz}$, segmented into 2,174 windows (5.0 seconds, 50% overlap).
* **Window Labeling:** Active acoustic bursts (`SB`, `MB`, `CRS`, `HS`) $\to$ `Present` (1); Quiescent/silence intervals $\to$ `Absent` (0).
* **Completed Experiments (`AI-Pipeline/results/`):**
  * **`EXP-A001-abdomen-cnn-compact`:** Best Val Loss `0.0758` (Epoch 11).
  * **`EXP-A002-abdomen-cnn-per-frequency-norm`:** Best Val Loss `0.0612` (Epoch 20).
  * **`EXP-A003-abdomen-cnn-dropout-050`:** Best Val Loss `0.0604` (Epoch 12).
  * **`EXP-A004-abdomen-cnn-conservative-augmentation`:** Best Val Loss `0.0575` (Epoch 12).
  * **`EXP-A005-abdomen-cnn-residual-se` (BEST MODEL):** Best Val Loss **`0.0571`** (Epoch 10, early stop Epoch 18).
  * **`EXP-A006-abdomen-cnn-learning-rate-0003`:** Best Val Loss `0.0589` (Epoch 15).
* **Current Best Abdomen Model:** `EXP-A005-abdomen-cnn-residual-se` (Val Loss: **0.0571**, Rec Sensitivity: **100%**, Rec Specificity: **100%**, Rec F1: **1.0000**).
* **Artifacts:** Stored in `AI-Pipeline/results/EXP-A00*/` along with `experiment_comparison_abdomen.csv` and `experiment_comparison_abdomen.png`.
---

## 3. Directory & Architecture Map

```text
auriscore-prototipe/
├── ARCHITECTURE.md                  # System architecture specifications
├── AI_PIPELINE.md                   # Machine learning rules and conventions
├── INTEGRATION.md                   # Data schemas and network contracts
├── DECISIONS.md                     # Architecture Decision Records (ADRs)
├── ROADMAP.md                       # Milestone tracking
├── WebApp/                          # Next.js 16 + Tailwind CDS interface
│   ├── src/components/auriscore/    # Waveform canvas, status cards, CDS result
│   ├── src/lib/auriscore/           # Protocol parser, ring buffer (80k samples)
│   └── mini-services/mock-device/   # Bun WebSocket server (port 8081, 8 kHz PCG)
└── AI-Pipeline/                     # Python 3.12 + TensorFlow 2.21 Machine Learning Pipeline
    ├── configs/
    │   ├── abdomen_cnn.yaml         # Abdomen DSP & CNN hyperparameters
    │   ├── abdomen_baseline.yaml    # Abdomen SVM baseline config
    │   ├── abdomen_cnn_queue.json   # 6-experiment queue manifest
    │   ├── heart_cnn.yaml           # Heart CNN config
    │   └── heart_cnn_queue.json     # Heart queue manifest
    ├── src/auriscore/
    │   ├── acquisition_abdomen.py   # Figshare REST API downloader + MD5/SHA256 validator
    │   ├── dataset_abdomen.py       # .txt annotation parser & window label tagger
    │   ├── cnn.py                   # Compact and Residual SE-CNN models
    │   ├── experiment_queue.py      # Resumable sequential experiment manager
    │   ├── evaluation.py            # Sensitivity-first threshold selection
    │   ├── preprocessing.py         # Resampling, filtering, DC removal
    │   └── spectrogram.py           # Log-mel and STFT feature tensor extractors
    ├── scripts/
    │   ├── download_abdomen_dataset.py
    │   ├── build_abdomen_manifest.py
    │   ├── preprocess_abdomen_dataset.py
    │   ├── train_abdomen_cnn.py
    │   ├── run_experiment_queue.py
    │   ├── launch_training_queue.ps1
    │   └── training_status.py
    ├── data/
    │   ├── external/bowel-sounds/   # Raw WAV and TXT files (gitignored)
    │   └── processed/               # Preprocessed .npy audio and segments.csv (gitignored)
    ├── metadata/                    # dataset_manifest.csv, errors
    └── results/                     # Completed experiment directories (EXP-A*, EXP-H*)
```

---

## 4. Remote PC Setup & Operational Commands

### A. Environment Initialization
```powershell
cd D:\Musyaffa\Despro-AurisCore\AI-Pipeline
git checkout feat/abdomen-ai
git pull origin feat/abdomen-ai

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Install requirements
python -m pip install -r requirements-cnn.txt
```

### B. Dataset & Preprocessing Pipeline
```powershell
# 1. Download dataset (if not already downloaded)
python scripts/download_abdomen_dataset.py

# 2. Build manifest & split
python scripts/build_abdomen_manifest.py

# 3. Preprocess into 8 kHz filtered segments
python scripts/preprocess_abdomen_dataset.py
```

### C. Running Experiments (Interactive / Foreground Mode)
```powershell
# Run the entire remaining queue interactively on screen
python scripts/run_experiment_queue.py --plan configs/abdomen_cnn_queue.json

# OR run one specific model:
python scripts/train_abdomen_cnn.py
# (or with specific flag: python scripts/run_experiment_queue.py --plan configs/abdomen_cnn_queue.json --only abdomen-cnn-per-frequency-norm)
```

### D. Checking Status & Progress
```powershell
python scripts/training_status.py --plan configs/abdomen_cnn_queue.json
```

---

## 5. Troubleshooting & Critical Pitfalls

1. **Orphaned Background Processes:**
   * If a process prints `[Queue Notice] Waiting for existing active process: PID XXXXX`, an earlier detached training process is still holding CPU/locks.
   * **Fix:**
     ```powershell
     Stop-Process -Name python -Force -ErrorAction SilentlyContinue
     ```
2. **Path Spacing in PowerShell:**
   * Always quote paths if running from directories containing spaces (e.g. `D:\Musyaffa UI\...`).
3. **Early Stopping is Expected:**
   * Training stops automatically when `val_loss` fails to improve for 8 epochs (`patience: 8`). A model stopping at Epoch 15–25 is healthy and prevents overfitting.
4. **Git Branch Discipline:**
   * All Abdomen AI changes must stay on `feat/abdomen-ai`.
   * Never force-push or merge broken checkpoints to `master`. Only completed results, configs, and code are committed.
