# SPRSound source-addition pilot — EXP-L012

Completion update: L012 fitting and development analysis completed successfully.
Best checkpoint is epoch two; early stopping occurred at epoch ten. It remains
research-only. The [completed review](lung_l012_review.md) documents the mixed
class effects, phase regression and common-weight loss comparison. Launch notes
below are historical; they do not describe an actively fitting L012 run.

Date: 2026-11-10. PRD section 7; research-only acoustic screening.

The user authorized acquisition, audit and prompt GPU fitting. EXP-L012 adds
SPRSound 2022 TRAIN to the existing HF fitting set while retaining every original
HF validation window, its order, groups and targets. Heart/Abdomen and application
result contracts remain unchanged. No model is activated automatically.

## Acquisition and label boundary

- Source: [official SPRSound repository](https://github.com/SJTU-YONGFU-RESEARCH-GRP/SPRSound),
  pinned revision `bca1e51422a42a042441010081519610ef3845d0`.
- License: pinned CC BY 4.0 text retained with original authors' attribution.
- Official TRAIN: 1,949 recordings / 251 patient identifiers. Official test
  filenames identify 203 patients. Only filename/blob metadata was inspected;
  no official-test audio or annotation contents were downloaded.
- Excluding all test-patient identities leaves 629 TRAIN recordings / 89 patients.
  Exact Git blob identity is also checked against the official test inventory;
  one content conflict is already covered by patient exclusion.
- All 1,261 selected files (629 WAV, 629 JSON, license and two READMEs) were
  checked against pinned Git blob SHA-1, bytes and saved SHA-256 receipts.
- Forty-four Poor Quality records were excluded. The resulting cache includes
  585 added recordings / 85 patient groups and 2,181 additional supervised windows.

Acoustic mapping v1 converts milliseconds to seconds. Coarse/fine crackles map
to crackle-containing intervals; Wheeze+Crackle maps to both targets. All original
labels remain in source manifests. The taxonomy is treated as exhaustive only
inside explicitly categorized events; full-frame containment establishes
negative coverage. Positive overlap remains positive. Outside annotated events
labels are unknown, and I/E targets are always masked. Normal record labels are
not stretched across unannotated audio. No phase boundaries or disease labels
are invented. This is an explicit source-supervision assumption, not independent
verification of annotation completeness or acoustic correctness.

New data are checked for clipping, silence, rate/duration, finite samples and
event bounds. Exact hashes and resampled gain/DC-normalized PCM fingerprints
are compared against known HF and accepted source recordings. Official SPR test
deduplication uses patient/blob inventory, not decoded test audio. These checks
are not exhaustive perceptual deduplication or proof of cross-source identity
independence. A supplementary scan found no selected recording with a trailing
zero run exceeding 16 ms (maximum 0.25 ms).

## Important class-support limitation

| Added event target | Annotated events | Supporting added patient groups |
| --- | ---: | ---: |
| Crackle | 130 | 20 |
| Wheeze | 88 | 12 |
| Rhonchi | 13 | 3 |
| Stridor | 1 | 1 |

These counts include combined event mapping and are not independent observations.
The added data are predominantly normal. This pilot studies source diversity
and false positives; it does not solve rare-class coverage, especially stridor.
The preserved HF validation set also cannot establish pediatric/source-wide
generalization. Further appropriately labeled rare-class data remain necessary.

## Frozen experiment

- ID: `EXP-L012-hf-sprsound-context`; comparator: L006, on identical HF validation.
- Fitting: 30,801 windows / 179 groups; validation: 17,688 windows / 24 HF groups.
- Same six-output temporal CNN, dilation 16, dropout 0.2, initial LR 0.001,
  Adam with zero weight decay, batch eight and seed 42. No additional augmentation.
- Maximum 50 epochs; val_loss early stopping, patience eight, restore best weights.
- Thresholds: existing per-class maximum-F1 development grid, 0.05..0.95 in
  37 points, lowest tie. Official test remains sealed.
- Post-fit: saved-score diagnostics, unsmoothed v2 one-to-one localization at
  0.1-s onset/offset tolerance, and matching-population per-class comparison to
  L006 including accuracy/balanced accuracy, sensitivity/specificity, precision,
  F1, ROC/PR-AUC, confusion counts, thresholds and class support.

The same source cache is not overwritten. Original HF payloads are hard-linked
into a separate immutable Linux cache; generated SPR payloads, metadata and
source receipts remain outside Git. The builder source, policy/config and cache
identities are frozen in the run's protocol. An earlier preparation-only cache
is retained; fitting uses `mixed-v2` with corrected combined manifest counts.

## Launch checkpoint

Launched 2026-11-10 approximately 10:01 WIB, WSL PID **3621**. Startup confirms
TensorFlow GPU:0 / RTX 5060 with a **3,072 MiB** logical-device memory cap and
successful 48,489-window preflight. The initial run status is training, at TRAIN
statistics preparation. The prior L007–L011 queue is preserved. Resource sharing
is explicitly recorded; concurrent wall-time is not a latency benchmark.
The worker waits for adequate free VRAM before starting and refuses CPU fallback.
Active agent polling stops after the startup check.

Runtime: `/home/vinend/.venvs/auriscore-lung`.
Code snapshot: `/home/vinend/auriscore-lung-runs/EXP-L012-20261110`.
Data: `/home/vinend/auriscore-sprsound2022/mixed-v2`.
Results: `AI-Pipeline/results/EXP-L012-hf-sprsound-context/`.
Protocol/status/log/analysis: `AI-Pipeline/artifacts/lung-launch/EXP-L012-20261110/`.
Source receipts/audit/tests: `AI-Pipeline/artifacts/lung-launch/SPRSound-20261110/`.

Verification: 116 Lung/source engineering tests passed, no skips, 173 dependency
deprecation warnings (7.58 s, CPU tests under the WSL TensorFlow environment).
No completed L012 metrics exist at launch. The run is not deployment eligible;
additional fitting does not establish clinical reliability.
