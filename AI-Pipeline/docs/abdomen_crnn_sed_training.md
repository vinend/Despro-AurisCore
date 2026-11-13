# Abdomen CRNN Sound Event Detection (SED) Training Report (EXP-A101)

**Branch:** `feat/abdomen-crnn-sed`  
**Experiment ID:** `EXP-A101-abdomen-crnn-sed`  
**Date:** 2026-10-13  
**Status:** Completed  
**Domain:** Abdomen Auscultation (Bowel Sounds / Acoustic Bursts Localization)  

---

## 1. Executive Summary & Clinical Intent

AurisCore Abdomen AI is an **assistive acoustic screening prototype**. The clinical goal is the accurate quantification of gastrointestinal motility (burst rate per minute and motility regularity) by localizing active bowel sound bursts (*Single Burst [SB], Multiple Burst [MB], Continuous Regular Sound [CRS], Harmonic Sound [HS]*).

Prior development on `feat/abdomen-ai` (`EXP-A001` through `EXP-A006`) established window-level classification (5.0-second presence detection). This experiment (`EXP-A101`) establishes **Approach 2: Pure Deep Learning Frame-Level Sound Event Detection (SED)**, predicting acoustic burst activity at **16.0 ms frame resolution** with millisecond onset/offset extraction.

---

## 2. Model Architecture & Training Configuration

### A. CRNN Architecture Specifications
* **Input Tensor:** $(40 \times 313 \times 1)$ — 40 Mel frequency bins ($100 - 1.000\text{ Hz}$), 313 time frames for 5.0-second audio windows ($f_s = 8.000\text{ Hz}$, $hop = 128$ samples $\approx 16.0\text{ ms}$).
* **Frequency-Only Convolutional Feature Extractor:**
  * 3 $\times$ `Conv2D` (Filters: 32, 64, 64; kernel $3 \times 3$; BatchNormalization + ReLU).
  * `MaxPooling2D(pool_size=(2, 1))` after each convolution block: shrinks frequency dimension ($40 \to 20 \to 10 \to 5$ bins) while **preserving all 313 time frames**.
* **Temporal Sequence Modeling:**
  * Permute & Reshape to sequence tensor: `(batch, 313, 320)`.
  * `Bidirectional(GRU(units=64, return_sequences=True))` $\to$ `(batch, 313, 128)`.
* **Classification Head:**
  * `Dropout(0.30)`.
  * `TimeDistributed(Dense(1, activation="sigmoid"))` $\to$ Frame burst probability $P(t) \in [0, 1]$ per 16 ms.
* **Total Parameters:** **204,577** (Trainable: 204,257 | Non-trainable: 320).

### B. Hyperparameters & Loss
* **Loss Function:** `BinaryFocalCrossentropy(gamma=2.0)` to mitigate heavy class imbalance (quiescent intervals outnumber burst intervals).
* **Optimizer:** Adam ($\text{learning rate} = 0.001$).
* **Batch Size:** 16.
* **Normalization:** Per-frequency z-score standardization (computed over all 1,801 training segments).
* **Early Stopping:** Monitored `val_loss` with patience of 8 epochs.

---

## 3. Training & Convergence Results

* **Execution Runtime:** **422.01 seconds (~7.03 minutes)** on native CPU.
* **Epochs:** 16 total epochs; stopped at Epoch 16 via early stopping.
* **Optimal Weights:** Epoch 7 (Restored best weights).
* **Best Validation Loss:** **`0.1053`** (Training loss: `0.0453`).

### Convergence Progression Table

| Epoch | Train Loss | Train Acc | Train PR-AUC | Train Sensitivity | Val Loss | Val Acc | Val PR-AUC | Val Precision | Val Sensitivity |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 0.0680 | 91.73% | 0.7475 | 66.21% | 0.4470 | 58.31% | 0.6639 | 0.00% | 0.00% |
| 3 | 0.0436 | 93.92% | 0.8506 | 72.76% | 0.3980 | 58.33% | 0.7625 | 100.0% | 0.04% |
| 5 | 0.0399 | 94.43% | 0.8732 | 75.60% | 0.2168 | 65.16% | 0.8424 | 98.41% | 16.69% |
| 7 | 0.0379 | 94.56% | 0.8814 | 76.12% | 0.1111 | 80.83% | 0.8755 | 90.54% | 60.33% |
| **8 (Best)** | **0.0453** | **93.04%** | **0.9226** | **73.17%** | **`0.1053`** | **81.95%** | **`0.8769`** | **88.38%** | **65.29%** |
| 10 | 0.0447 | 93.93% | 0.9266 | 90.41% | 0.1159 | 78.61% | 0.8439 | 74.64% | 73.74% |
| 12 | 0.0302 | 95.88% | 0.9555 | 85.52% | 0.1405 | 73.22% | 0.8272 | 63.75% | 82.91% |
| 16 (Stop)| 0.0466 | 92.51% | 0.9118 | 63.39% | 0.1275 | 77.15% | 0.8247 | 74.69% | 68.37% |

*Best checkpoint at Epoch 8 (index 7) achieved **Val PR-AUC 0.8769**, **Val ROC-AUC 0.8994**, and **Val Precision 88.38%**.*

---

## 4. DCASE Event-Based Sound Event Detection (SED) Evaluation

Discrete event extraction applied hysteresis dual-threshold tracking to continuous frame predictions:
* **Smoothing:** Median filter (kernel size 3).
* **Thresholding:** Onset threshold $P(t) \ge 0.50$; offset threshold $P(t) < 0.25$.
* **Morphological Merging:** Gap tolerance $\le 60.0\text{ ms}$.
* **Event Filtering:** Minimum burst duration $\ge 25.0\text{ ms}$.

### Event-Level Metrics (Collar Tolerance = 100 ms)

| Metric | Measured Value | Clinical Interpretation |
|---|:---:|---|
| **True Positives (TP)** | **146** | Validated burst onsets matching ground-truth within $\pm 100\text{ ms}$ |
| **False Positives (FP)** | **174** | Predicted events without matching ground-truth annotation within collar |
| **False Negatives (FN)** | **306** | Ground-truth burst intervals missed by model thresholding |
| **Event Precision** | **`45.62%`** | Proportion of predicted acoustic bursts that correspond to true bowel sounds |
| **Event Recall (Sensitivity)** | **`32.30%`** | Proportion of ground-truth acoustic bursts successfully localized |
| **Event F1-Score** | **`37.82%`** | Harmonic mean of collar-100ms event detection |
| **Detected Events Count** | 320 | Total discrete bursts identified across validation windows |
| **Ground Truth Events Count**| 452 | Total active annotated bursts across validation windows |

---

## 5. Architectural Comparison: Window-Level CNN vs. Frame-Level CRNN

| Feature | Window CNN (`EXP-A005`) | Frame-Level CRNN SED (`EXP-A101`) |
|---|:---:|:---:|
| **Temporal Granularity** | Window-level (1 prediction per 5.0s) | Frame-level (313 predictions per 5.0s, ~16 ms) |
| **Onset / Offset Output**| None (binary presence only) | Millisecond start & end timestamps |
| **Pooling Dimension** | 2D Global Average Pooling (Freq + Time) | Frequency-only pooling (`(2, 1)`), time preserved |
| **Sequence Model** | None | Bidirectional GRU (64 units) |
| **Loss Function** | Binary Crossentropy | Binary Focal Crossentropy ($\gamma = 2.0$) |
| **Evaluation Standard** | Window AUC / F1 | DCASE Event Collar Evaluation (100 ms) |
| **Clinical Utility** | Coarse burst presence gating | Accurate motility interval & rate quantification |

---

## 6. Artifact Inventory

All training artifacts are archived under `AI-Pipeline/results/EXP-A101-abdomen-crnn-sed/`:

* `best_model.keras` (2.55 MB) — Trained Keras weights with best validation loss.
* `history.csv` (3.79 KB) — Full training log across 16 epochs.
* `training_history.png` (125.8 KB) — Dual-panel convergence plot (Loss and Accuracy).
* `metrics.json` (518 B) — Machine-readable summary metrics.
* `status.json` (131 B) — Experiment status manifest.
* `config.json` (3.00 KB) — Frozen hyperparameter configuration.

---

## 7. Validated Threshold & Collar Sensitivity Analysis (Completed)

Comprehensive post-hoc sensitivity evaluation was conducted on the frozen `EXP-A101` model across 240 combinations of onset thresholds (0.35–0.80), offset hysteresis policies, merge gaps (20–60 ms), and collar tolerances (100–250 ms) on the 185 validation windows (452 ground-truth events).

### Key Empirical Findings:
1. **Loose Hysteresis Trap:** Lowering onset threshold to 0.20–0.30 with loose offset (e.g. 0.10) caused adjacent bursts to merge into a single extended event, reducing detected event count from 320 to 200 and causing Recall to drop to 6.42%.
2. **Tight Hysteresis Breakthrough:** Using a narrow hysteresis band (`Onset 0.55 / Offset 0.45` or `Onset 0.50 / Offset 0.40`) allowed the model to sharply separate consecutive bursts, nearly doubling validated True Positives.

### Comparative Operating Points Table

| Configuration / Profile | Onset / Offset Th. | Gap (ms) | Collar (ms) | Detected | TP | FP | Precision | Recall (Sensitivity) | Event F1-Score |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Initial Benchmark (Loose)** | `0.50 / 0.25` | 60 | 100 | 320 | 146 | 174 | 45.62% | **32.30%** | **37.82%** |
| **Calibrated Screening (DCASE)** | `0.55 / 0.45` | 60 | **100** | 666 | **254** | 412 | 38.14% | **56.19%** *(+23.9%)* | **45.44%** |
| **Balanced Precision (DCASE)** | `0.60 / 0.30` | 60 | **100** | 349 | **179** | 170 | **51.29%** | **39.60%** | **44.69%** |
| **Calibrated Screening (Physio 200ms)** | `0.55 / 0.45` | 60 | **200** | 666 | **296** | 370 | 44.44% | **65.49%** *(+33.2%)* | **52.95%** |
| **Calibrated Screening (Physio 250ms)** | `0.55 / 0.45` | 60 | **250** | 666 | **303** | 363 | 45.50% | **67.04%** *(+34.7%)* | **54.20%** |
| **High Precision (Physio 250ms)** | `0.60 / 0.30` | 60 | **250** | 349 | **215** | 134 | **61.60%** | **47.57%** | **53.68%** |

Full machine-readable results are archived in:
* `AI-Pipeline/results/EXP-A101-abdomen-crnn-sed/sensitivity_comprehensive_analysis.csv`
* `AI-Pipeline/results/EXP-A101-abdomen-crnn-sed/sensitivity_comprehensive_analysis.json`

---

## 8. Designated Direction Moving Forward (Decision History)

By user instruction (2026-11-12), future Abdomen AI development focused on the **Calibrated Tight-Hysteresis CRNN SED architecture**:
1. **Primary Screening Preset (`screening_recall`):** Set as the default operating profile in `auriscore.sed_postprocessing.extract_events_from_curve`:
   - `onset_threshold = 0.55`, `offset_threshold = 0.45`, `merge_gap_ms = 60.0`
   - Achieves 56.19% Recall (Collar 100 ms) and 67.04% Recall (Collar 250 ms).
2. **Hybrid Localization Integration:** Combine the CRNN probability curve $P(t)$ from this model with the Hilbert envelope detector $E(t)$ (`feat/abdomen-dsp-localization`) as a spectral gating filter.
3. **Motility Metrics Serialization:** Pipe the extracted discrete event timestamps into the unified `abdomen-analysis-v1` schema to produce true clinical Bowel Rate (events/min) and Bowel Rate Variability (BRV).

---

## 9. Experiment EXP-A102: Residual-SE CRNN Architecture

* **Experiment ID:** `EXP-A102-abdomen-crnn-residual-se`
* **Architecture:** `crnn_architecture: residual_se`
  * Replaced standard convolutions with Depthwise Separable Convolutions + Residual identity shortcuts.
  * Added frequency-wise Squeeze-and-Excitation (SE) channel recalibration before frequency pooling.
  * Parameter count: **261,313** parameters (~1.1 MB).
* **Training Convergence:**
  * Stopped at Epoch 18 (Best Val Loss: `0.1124` at Epoch 9).
  * Training time: ~49.5 minutes.
* **Evaluation Findings:**
  * High-Precision Profile (`Onset 0.60 / Offset 0.30`, Collar 250ms): Precision **58.04%**, Recall **51.11%**, Event F1 **54.35%**.
  * Screening Profile (`Onset 0.55 / Offset 0.45`, Collar 250ms): Recall **67.26%**, Precision **43.49%**, Event F1 **52.82%**.
  * Weakness: Still sensitive to out-of-domain acoustic transients (heart sounds and sensor friction) leading to 452 False Positives at Collar 100ms.

---

## 10. Experiment EXP-A103: Hard Negative Mining from Hardware Stethoscope Audio

* **Experiment ID:** `EXP-A103-abdomen-crnn-hard-negatives`
* **Motivation:**
  Stethoscope microphones placed on the abdomen capture acoustic bleed-through from heart valves (S1/S2 transmission to the epigastrium), breathing, and sensor movement. Models trained solely on Figshare bowel sound files trigger false alarms on these transients.
* **Hard Negative Ingestion (`prepare_hard_negatives.py`):**
  * 10 native 16 kHz heart and ambient recordings from `D:\Despro\Prapemrosesan_Tubuh` recorded on the physical AurisCore stethoscope hardware.
  * Resampled to 8,000 Hz, bandpass filtered (100–1,000 Hz), sliced into 360 non-overlapping 5.0-second segments labeled strictly as `Absent = 0` across all 313 frames.
  * Appended to training set: `segments_train_hn.csv` expanded to **2,161 segments** (+20.0% volume).
  * **Strict Data Governance:** Validation (185) and Test (188) sets remained 100% sterile and untouched.
* **Training Convergence:**
  * Stopped at Epoch 27 (Best Val Loss: `0.1192`).
  * Training time: ~79.4 minutes.
* **Evaluation Results:**
  * **False Positive Reduction:** At Collar 100ms, false positives dropped from 452 (EXP-A102) to **427** (-25 false alarms). Total detected false triggers dropped from 699 to 673.
  * **Precision Gain:** Collar 100ms Precision rose to **36.55%** (F1 `43.73%`).
  * **Collar 250ms Screening Profile:** Recall **66.15%**, Precision **44.43%**, Event F1 **53.16%** (TP = 299).
  * **Collar 250ms High-Precision Profile (`Onset 0.70 / Offset 0.35`):** Precision **63.04%**, Recall **44.91%**, Event F1 **52.45%** (FP reduced to only 143).

---

## 11. Final Model Candidate Selection (EXP-A103 Locked for Production)

By architectural and user decision (2026-11-13), **`EXP-A103-abdomen-crnn-hard-negatives` is designated as the primary production candidate model**:
1. **Clinical Justification:** It is the only trained model inoculated against hardware stethoscope bleed-through and environmental artifacts.
2. **Post-Processing Configuration:** Operating with dual presets (`screening_recall` for ileus rule-out, and `balanced_precision` / `high_precision` for motility rate counting).
3. **Downstream Integration:** Model weights `AI-Pipeline/results/EXP-A103-abdomen-crnn-hard-negatives/best_model.keras` are wired into `auriscore.abdomen_inference` and the `abdomen-analysis-v1` service schema for the WebApp CDS interface.

