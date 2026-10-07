# Real Abdomen CNN Development Runs (feat/abdomen-ai)

Assistive acoustic screening prototype. The target is bowel sound acoustic burst presence (**Absent=0** vs **Present=1**), not a definitive gastrointestinal diagnosis. Output represents acoustic screening indicators to assist clinical auscultation (e.g. motility rate calculation).

---

## 1. Dataset and DSP Preprocessing

* **Source Dataset:** Figshare Bowel Sounds 1.0 (14 files, 7 continuous long recordings across 4 subject sessions, CC BY 4.0).
* **Signal Conditioning:**
  * Resampled to **8,000 Hz mono**.
  * 4th-order Butterworth bandpass filter **100 – 1,000 Hz** (attenuates low-frequency heart sounds/breathing and high-frequency friction).
  * Window segmentation: **5.0 seconds with 50% overlap** (40,000 samples per window, 20,000 hop).
  * Total segments: **2,174 windows**.
* **Annotation & Window Labeling:**
  * Active acoustic events (*Single Burst [SB], Multiple Burst [MB], Continuous Regular Sound [CRS], Harmonic Sound [HS]*) $\to$ **`Present` (1)**.
  * Quiescent / baseline intervals $\to$ **`Absent` (0)**.
* **Feature Representation:** 40-bin Log-Mel Spectrogram tensors ($40 \times 313 \times 1$).

---

## 2. Complete Experiment Queue Results (`configs/abdomen_cnn_queue.json`)

All 6 planned architectural and hyperparameter variations completed sequentially:

| Experiment ID | Architecture / Hyperparameter Variation | Best Val Loss | Best Epoch | Total Epochs | Threshold | Training Time | Rec Sensitivity | Rec Specificity | Rec F1 |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| [`EXP-A001`](../results/EXP-A001-abdomen-cnn-compact/) | Compact Baseline (MinMax normalization) | `0.0758` | 11 | 19 | 0.9662 | 4.4s | 100.0% | 100.0% | 1.0000 |
| [`EXP-A002`](../results/EXP-A002-abdomen-cnn-per-frequency-norm/) | Per-Frequency Normalization (z-score clip 5.0) | `0.0612` | 20 | 28 | 0.9727 | 151.1s | 100.0% | 100.0% | 1.0000 |
| [`EXP-A003`](../results/EXP-A003-abdomen-cnn-dropout-050/) | Compact with Dropout 0.50 | `0.0604` | 12 | 20 | 0.9716 | 108.8s | 100.0% | 100.0% | 1.0000 |
| [`EXP-A004`](../results/EXP-A004-abdomen-cnn-conservative-augmentation/) | Conservative Augmentation (gain, shift, SpecAugment) | `0.0575` | 12 | 20 | 0.9751 | 116.8s | 100.0% | 100.0% | 1.0000 |
| **[`EXP-A005`](../results/EXP-A005-abdomen-cnn-residual-se/)** | **Residual Squeeze-and-Excitation (SE-CNN)** | **`0.0571`** | **10** | **18** | **0.9813** | **236.7s** | **100.0%** | **100.0%** | **1.0000** |
| [`EXP-A006`](../results/EXP-A006-abdomen-cnn-learning-rate-0003/) | Compact with Reduced Learning Rate (0.0003) | `0.0589` | 15 | 23 | 0.9799 | 124.4s | 100.0% | 100.0% | 1.0000 |

Comparison artifacts:
* Table: `AI-Pipeline/results/experiment_comparison_abdomen.csv`
* Figure: `AI-Pipeline/results/experiment_comparison_abdomen.png`

---

## 3. Best Performing Model: `EXP-A005-abdomen-cnn-residual-se`

* **Winning Architecture:** Residual SE-CNN (`cnn_architecture: residual_se`). Employs residual skip connections with channel-wise Squeeze-and-Excitation attention gates to adaptively recalibrate feature maps.
* **Loss Convergence:** Converged to **`0.0571`** validation loss at Epoch 10 (early stopped at Epoch 18 with patience 8), achieving a **24.7% loss reduction** over the `EXP-A001` baseline.
* **Screening Metrics:**
  * Sensitivity / Recall: **100.0%** (surpasses $\ge 90\%$ clinical screening target)
  * Specificity: **100.0%**
  * Macro F1 / Positive F1: **1.0000**
  * ROC-AUC / PR-AUC: **1.0000**
* **Model Artifacts:**
  * Model Checkpoint: `AI-Pipeline/results/EXP-A005-abdomen-cnn-residual-se/best_model.keras`
  * Metrics Manifest: `AI-Pipeline/results/EXP-A005-abdomen-cnn-residual-se/metrics.json`
  * Diagnostic Plots: `training_history.png`, `confusion_matrix.png`, `roc_curve.png`, `threshold_analysis.png`.

---

## 4. Key Engineering & Pipeline Fixes on `feat/abdomen-ai`

1. **Windows Launcher Process Deadlock (`experiment_queue.py`):**
   * *Issue:* Running `.venv\Scripts\python.exe` on Windows creates a launcher stub process. The child Python worker detected its own parent launcher as an "external active trainer", causing an infinite mutual sleep loop in `wait_for_other_trainers()`.
   * *Fix:* Updated `active_training_processes()` to query process hierarchy via `psutil` and explicitly ignore self, ancestors/parents, and children.
2. **Frequency Statistics Indentation Bug (`cnn.py`):**
   * *Issue:* `raise ValueError("Cannot estimate spectrogram statistics from an empty training partition")` was accidentally indented inside the window iteration loop, causing instant crashes during per-frequency normalization.
   * *Fix:* Relocated the empty partition guard to execute post-loop, accompanied by live segment progress counters.
3. **Queue Monitoring & Heartbeat Watchdog:**
   * Added 10-second diagnostic heartbeats reporting CPU usage and process details during waits.
   * Added 60-second stall detection warnings with remediation commands.
   * Added `--skip-wait` flag to `scripts/run_experiment_queue.py` and `scripts/train_abdomen_cnn.py`.
4. **Dual-Domain Summarizer (`summarize_experiments.py` & `visualization.py`):**
   * Extended reporting to dynamically detect and format both Heart (`EXP-H*`) and Abdomen (`EXP-A*`) runs into dedicated comparison tables and figures.

---

## 5. Reproduction

```powershell
cd D:\Musyaffa\Despro-AurisCore\AI-Pipeline

# 1. Download and verify Figshare dataset
python scripts/download_abdomen_dataset.py

# 2. Build manifest and assign splits
python scripts/build_abdomen_manifest.py

# 3. Preprocess audio into 8 kHz filtered segments
python scripts/preprocess_abdomen_dataset.py

# 4. Run the 6-experiment queue (interactive / foreground)
.venv\Scripts\python.exe scripts/run_experiment_queue.py --plan configs/abdomen_cnn_queue.json

# 5. Summarize completed experiments
.venv\Scripts\python.exe scripts/summarize_experiments.py
```
