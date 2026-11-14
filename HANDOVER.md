# AurisCore AI Pipeline — Engineering Handover Document (HANDOVER.md)

**Project:** AurisCore Digital Stethoscope (Assistive Acoustic Screening System)  
**Repository:** `https://github.com/vinend/Despro-AurisCore.git`  
**Current Active Feature Branch:** `feat/abdomen-crnn-sed` (CRNN Frame-Level Retraining)  
**Status Date:** 2026-10-10  

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

---

## 6. CRNN Sound Event Detection (SED) Retraining Workflow (`feat/abdomen-crnn-sed`)

### A. Objective & Approach
This branch implements **Approach 2 (Pure Deep Learning Frame-Level SED)**:
* Replaces global pooling with **frequency-only pooling** + **Bidirectional GRU** + **TimeDistributed Dense**.
* Predicts acoustic burst probability $P(t) \in [0, 1]$ per **16 ms time frame** (313 frames per 5.0s window).
* Uses **Binary Focal Loss** ($\gamma=2.0$) to handle silence-vs-burst class imbalance.
* Evaluates both frame-level metrics and **Event-based F1-score with 100 ms collar tolerance** (DCASE standard).

### B. Step-by-Step Execution on Remote PC Lab

```powershell
# 1. Navigate and switch to the retraining branch
cd D:\Musyaffa\Despro-AurisCore\AI-Pipeline
git fetch origin
git checkout feat/abdomen-crnn-sed
git pull origin feat/abdomen-crnn-sed

# 2. Activate virtual environment
.venv\Scripts\Activate.ps1

# 3. Kill any lingering Python processes
Stop-Process -Name python -Force -ErrorAction SilentlyContinue

# 4. Start the interactive CRNN training
python scripts/train_abdomen_sed.py
```

### C. Expected Outputs & Artifacts
Training runs for up to 35 epochs (with EarlyStopping patience 8). Expected completion time: $\approx 25 - 40\text{ minutes}$ on CPU.

Artifacts generated under `AI-Pipeline/results/EXP-A101-abdomen-crnn-sed/`:
* `best_model.keras` — Trained CRNN Keras weights.
* `history.csv` — Epoch-by-epoch training and validation loss/metrics.
* `training_history.png` — Loss and accuracy convergence curves.
* `metrics.json` — Evaluated Event F1-score, Recall, Precision (Collar 100 ms), and event counts.

### D. Post-Training Git Commit on PC Lab
```powershell
git add results/EXP-A101-abdomen-crnn-sed/
git commit -m "feat(sed): save completed EXP-A101 abdomen CRNN SED model and evaluation"
git push origin feat/abdomen-crnn-sed
```

### E. Completed Run Results (EXP-A101)
* **Status:** Completed (2026-10-13)
* **Training Time:** 422.01s (stopped at Epoch 16, best checkpoint Epoch 8)
* **Best Val Loss:** `0.1053` (Val PR-AUC: `0.8769`, Val ROC-AUC: `0.8994`)
* **Event SED Metrics (Collar 100 ms):**
  * Detected Events: 320 (Ground Truth: 452)
  * Event Precision: **45.62%**
  * Event Recall / Sensitivity: **32.30%**
  * Event F1-Score: **37.82%**
* **Full Milestone Report:** `AI-Pipeline/docs/abdomen_crnn_sed_training.md`

### F. Post-Hoc Calibrated Operating Profile (Active Decision)
* **Screening Baseline:** `Onset: 0.55 / Offset: 0.45` with tight hysteresis (avoids false merge of adjacent bursts).
* **Calibrated Metrics:**
  * **Collar 100 ms:** Recall **56.19%** (up from 32.30%), Event F1 **45.44%**, TP = 254.
  * **Collar 200 ms:** Recall **65.49%**, Event F1 **52.95%**, TP = 296.
  * **Collar 250 ms:** Recall **67.04%**, Event F1 **54.20%**, TP = 303.
* **Balanced Profile Alternative:** `Onset: 0.60 / Offset: 0.30` -> Precision **51.29%** (100 ms) / **61.60%** (250 ms).
* **Code Implementation:** Active in `auriscore.sed_postprocessing.SED_CALIBRATED_PROFILES`. Designated as the primary focus for ongoing Abdomen AI development.

### G. Hard Negative Mining & Production Selection (EXP-A103 - Locked Decision)
* **EXP-A102 (Residual-SE CRNN):** 261k params, SeparableConv2D + Residual Skips + Squeeze-and-Excitation. Best Val Loss `0.1124`. High Precision profile reaches Precision `58.04%` / Recall `51.11%` at Collar 250ms.
* **EXP-A103 (Residual-SE + Hard Negatives):**
  * Ingested 10 physical hardware recordings (360 5.0s segments) from `D:\Despro\Prapemrosesan_Tubuh` as negative labels (`Absent = 0`).
  * 2,161 training segments (+20% data). Validation and test sets 100% clean and untouched.
  * Training completed: 27 epochs, best val loss `0.1192`.
  * **Result:** False Positives reduced from 452 down to **427** (-25 FP) at Collar 100ms; Collar 250ms Precision reached **44.43%** (Recall **66.15%**, F1 **53.16%**); High-Precision profile reached **63.04%** Precision.
* **Locked Production Candidate:** **`EXP-A103`** selected as the production model for `abdomen-analysis-v1` due to demonstrated robustness against real-world stethoscope acoustic artifacts.

---

## 7. HANDOVER: EKSEKUSI TRAINING EXP-A104 DI PC LAB (Dataset Kaggle Nowak)

### A. Konteks & Tujuan Eksperimen EXP-A104
* **Tujuan:** Melatih model fine-tuning berbasis bobot pretrained **EXP-A103** menggunakan dataset publik **Kaggle `robertnowak/bowel-sounds`** (427 pasien unik, 1.606 rekaman audio 2.0s, 6.413 kejadian bising usus) + *hard negatives* hardware AurisCore.
* **Target Metrik:** Meningkatkan Event Recall dari ~66% ke **>75%–80%** dan menekan False Positives dengan variasi 427 subjek nyata.
* **Branch Git Aktif:** `feat/abdomen-crnn-sed`

---

### B. Langkah Eksekusi di PC Lab (Step-by-Step)

#### 1. Masuk ke Repo & Tarik Update Terbaru
```powershell
cd D:\Despro\Despro-AurisCore
git fetch origin
git checkout feat/abdomen-crnn-sed
git pull origin feat/abdomen-crnn-sed
```

#### 2. Siapkan File Dataset Kaggle
Pastikan file rekaman Kaggle diletakkan di direktori berikut:
```text
AI-Pipeline/data/external/kaggle-bowel-sounds/
```
*(Berisi 1.606 file `.wav`, 1.606 file `.csv`, dan `files.csv`). Jika di PC Lab sudah ada folder `D:\Despro\archive\data`, cukup salin isinya ke `AI-Pipeline\data\external\kaggle-bowel-sounds\`.*

#### 3. Jalankan Preprocessing Dataset (Hanya ~40 Detik)
Skrip ini akan melakukan resampling ke 8 kHz, bandpass 100–1.000 Hz, ekstraksi log-mel (40, 126), frame masks, dan patient-level leak-free split:
```powershell
python AI-Pipeline/scripts/prepare_kaggle_dataset.py
```
*Output yang dihasilkan:*
* `AI-Pipeline/data/processed/kaggle/kaggle_sed_tensors.npz` (tensors cache)
* `AI-Pipeline/data/processed/segments_kaggle.csv` (manifest pembagian train/val/test)

#### 4. Jalankan Pelatihan EXP-A104

**Opsi A — Mode Interaktif (Tampil Langsung di Layar Terminal):**
```powershell
python AI-Pipeline/scripts/train_kaggle_sed.py --config configs/abdomen_sed_nowak.yaml --name EXP-A104-abdomen-crnn-nowak
```

**Opsi B — Mode Background (PowerShell Launcher):**
```powershell
powershell -ExecutionPolicy Bypass -File AI-Pipeline/scripts/launch_abdomen_nowak.ps1
```
*Untuk memantau log secara real-time jika dijalankan di background:*
```powershell
Get-Content AI-Pipeline\.runtime\EXP-A104-abdomen-crnn-nowak.stdout.log -Wait -Tail 30
```

---

### C. File Hasil & Verifikasi Pasca-Training
Hasil evaluasi lengkap tersimpan di:
* `AI-Pipeline/results/EXP-A104-abdomen-crnn-nowak/best_model.keras`
* `AI-Pipeline/results/EXP-A104-abdomen-crnn-nowak/metrics.json`
* `AI-Pipeline/results/EXP-A104-abdomen-crnn-nowak/sensitivity_comprehensive_analysis.csv`
* `AI-Pipeline/results/EXP-A104-abdomen-crnn-nowak/training_history.png`

### D. Hasil Training EXP-A104 (Completed - 2026-11-14)
* **Status:** Completed
* **Best Val Loss:** `0.0521` (Epoch 15, early stopping Epoch 23)
* **Event SED Metrics (Collar 250 ms - Max F1 Profile `0.50 / 0.40`):**
  * Event Precision: **85.97%** (naik dari 44.43% di EXP-A103)
  * Event Recall / Sensitivity: **61.15%** (576 TP dari 942 event ground truth)
  * Event F1-Score: **71.46%** (naik dari 53.16% di EXP-A103)
  * False Positives: **94** (turun drastis dari 427 di EXP-A103)
* **High-Precision Profile (`0.80 / 0.64`):** Precision **98.84%**, hanya 2 FP di seluruh set validasi.
* **Screening Profile (`0.40 / 0.32`):** Recall **64.97%**, Precision **78.26%**, Event F1 **71.00%**.




