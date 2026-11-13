# RD-LTMIL-01-v1-B1 — final experiment result (2026-10-29)

**Technical completion: SUCCESS. Performance: PERFORMANCE_GATE_FAILED. Deployment: NOT APPROVED.** No additional training or threshold adjustment was performed during this evaluation.

## Participant-level TRAIN development results

Five disjoint outer folds cover 568 participants: 458 Absent and 110 Present. Each participant's decision uses its own fold's previously frozen early-stop threshold. Recomputed thresholds match the saved early-stop selections exactly. No pooled threshold was selected.

| Metric | Result |
|---|---:|
| TN / FP / FN / TP | 223 / 235 / 12 / 98 |
| Accuracy | 56.51% |
| Sensitivity | 89.09% |
| Specificity | 48.69% |
| Precision | 29.43% |
| F1 | 0.4424 |
| Balanced accuracy | 68.89% |
| ROC-AUC | 0.8724 |
| PR-AUC (average precision) | 0.7658 |

**Both gates fail:** sensitivity <90% and FP >120. The <85% aggregate hard-failure condition is not reached, but fold 1 sensitivity is below85%. Cross-fold operating points are unstable. Pooled AUCs use raw probabilities from different folds and should be interpreted with their fold-scale limitation; per-fold ranking metrics are below. Historical R1 FP128 used a different threshold protocol, so these results do not establish a matched comparison or a causal explanation for differences.

| Fold | Epochs / best epoch | TN | FP | FN | TP | Sensitivity | Specificity | ROC-AUC | PR-AUC | Locked threshold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 50 / 48 | 60 | 32 | 6 | 16 | 72.73% | 65.22% | 0.8132 | 0.6917 | 0.20940093 |
| 2 | 50 / 47 | 34 | 58 | 1 | 21 | 95.45% | 36.96% | 0.8760 | 0.7567 | 0.17194905 |
| 3 | 29 / 21 | 24 | 68 | 0 | 22 | 100.00% | 26.09% | 0.9471 | 0.8542 | 0.15147623 |
| 4 | 50 / 50 | 59 | 32 | 3 | 19 | 86.36% | 64.84% | 0.9016 | 0.8449 | 0.32925009 |
| 5 | 19 / 11 | 46 | 45 | 2 | 20 | 90.91% | 50.55% | 0.8696 | 0.7735 | 0.21628894 |

## Cardiac phase and temporal output

Official TSV reference evaluation on the exported common16ms grid uses geometry coverage, unknown masks and the frozen64ms phase-boundary guard. Coverage after all masks is **10.90%**, with 324,817 valid grid frames; 105 recordings have unavailable/invalid phase references and remain in presence evaluation. This is grid-level phase evaluation, not independent murmur interval validation.

Phase macro-F1 is **0.3671**. Recall: S1 20.20%, systole 15.29%, S2 0.35%, diastole 98.76%. S2 and systole performance are particularly weak; this does not support a reliable cardiac-phase output claim. Coverage limits are material and no official label is declared incorrect.

Descriptive transition-type matching gives matched-boundary MAE 1.671s across 15,797 matches, with 150,406 unmatched reference and 58,115 unmatched predicted events. No tolerance was optimized; this conditional error is not boundary detection sensitivity or murmur localization accuracy.

18,641 exploratory murmur candidate regions were exported using a fixed display cutoff0.5 on temporal scores. That display cutoff is uncalibrated and separate from participant classification thresholds. Candidates are explicitly marked `exploratory_not_validated_murmur_interval`; there is no murmur onset/offset accuracy claim.

## Integrity, replay and runtime

All five folds completed. Original run manifest verified **160,639 files**, including checkpoints, optimizer states, histories, cache entries and saved predictions. Two fresh deterministic processes per fold replayed **every outer recording**. Maximum recording/participant/temporal probability difference was **0**; participant and phase decisions were identical. All five normalization snapshots are copied with their original frozen hashes into the evaluation directory. The evaluation itself has a sealed manifest.

Watchdog exit code 0, timeout False; measured process-tree wall runtime **8795.717s (2h26m35.717s)**, below43,200s. This includes GPU-enabled training, validation, loading and export; exclusive GPU-kernel active time was not profiled and is not invented. Hardware was RTX4060LaptopGPU. A postprocessing filename-parser error initially included optimizer metadata as checkpoint selection markers; the corrected parser uses only `best-epoch-NN.json`. Its failure log is retained; no training/fold retry occurred.

Authoritative machine-readable evidence is in `/home/rowen/research-runs/RD-LTMIL-01-v1-B1-20261028-evaluation/`: `final_report.json`, ten replay reports, `integrity.json`, `exploratory_candidates.json`, invalid-phase references, normalization snapshots and `manifest.json`. The untouched training run is the sibling directory without `-evaluation`.

This run is closed as technically completed, reproducible, and performance-gate failed. No external validation/sealed test, human review, relabeling, website/demo changes, commit/push, model promotion or automatic retraining occurred. Preserve these artifacts; stop after this report.
