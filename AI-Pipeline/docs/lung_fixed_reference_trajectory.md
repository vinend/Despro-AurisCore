# Fixed-reference Lung features and training trajectory — 2026-11-10

## Requirement and scope

Implements the user-requested improvements after the L016–L018 deep review.
Serves PRD section 7 acoustic findings (wheeze/rhonchi/crackle). Upstream is the
audited HF development audio/manifests. Downstream is research cache/training
evidence; no model activation, WebApp response change or diagnostic claim.
Heart/Abdomen feature extraction is preserved. Lung phase/respiratory requirements
remain required beyond this temporary research head.

## Opt-in feature policy

`configs/lung_cnn_fixed_reference.yaml` adds only:

```yaml
lung_feature_policy:
  schema_version: lung-fixed-logmel-v1
  reference_power: 1.0
  floor_db: -80.0
```

`lung_preprocessing.extract_lung_features` reuses the original FFT/mel power
calculation and computes `10*log10(max(power, 1e-8)/1.0)`. The absolute floor is
fixed; there is no per-window `ref=max`, upper rescaling or relative `top_db`
floor. Parameters are declared engineering constants, not selected on validation.
The legacy `cnn_top_db` field remains for unchanged legacy/shared config behavior;
it is not used by this Lung-only policy. Absent policy selects the exact old path;
unknown/malformed explicit policies and nonfinite features fail closed.

The shared `spectrogram.extract_spectrogram_tensor` is unchanged. Existing Heart,
Abdomen and legacy Lung tensors therefore retain their original behavior. A new
config digest creates a separate Lung cache. Labels, masks, timestamps, geometry,
source split and group membership must match the old cache exactly. Frequency
mean/std must be fitted again on TRAIN features; an old checkpoint/normalization
cannot be paired with this representation.

The synthetic invariance test places loud energy outside a shared audio region.
Legacy/shared features remain bit-identical to their old implementation while
new shared-frame Lung features agree within atol 1e-5, rtol zero. Silence has a
finite -80 dB floor. Target/mask/physical-tail behavior is independently checked.
This addresses the measured representation inconsistency, not yet held-out model
accuracy or source generalization.

## Opt-in trajectory policy v7

`configs/lung_training_fixed_reference_trajectory.json` extends v6 with an explicit
per-epoch evidence policy. Its model/loss/optimizer/window settings match L017,
which retains all fitting windows. The policy freezes 16 recordings per device
and fitting partition, seed 42, one window per selected recording and diagnostic
thresholds [.5,.5,.5]. No threshold search occurs in the callback. v1–v6 remain
unchanged; v7 is research-only and rejected by final-package fitting.

`lung_trajectory.select_probes` checks source/group/split identities, disjoint
fitting/held-out groups and exclusion of official test rows. Probe selection is
independent of labels, predictions and epoch outcomes. A capped deterministic
source-balanced probe is a diagnostic sample, not the full evaluation population
or an independent-patient estimate. The source manifests remain date-group based.

Every epoch saves a fresh immutable directory under each fold:

```text
trajectory/protocol.json
trajectory/probe-index.csv
trajectory/epoch-0001/weights.weights.h5
trajectory/epoch-0001/predictions.npz
trajectory/epoch-0001/metrics.json
trajectory/epoch-0002/...
trajectory/last-epoch.json
```

Weights are captured at epoch end **before train-end best-weight restoration**.
The last-epoch pointer therefore identifies the actual last epoch snapshot;
restoring best weights cannot erase it. Existing best checkpoint/model/history
outputs remain available. Repeated writes to an existing epoch fail rather than
overwrite evidence. Snapshot files include optimizer state where Keras saves it;
the callback never applies optimizer updates or changes learning rate/stopping.

Each epoch records optimizer update count, LR and per-class metrics for fitting
and inner-validation probes, device strata and date-group strata:

- confusion counts, sensitivity, specificity, precision, F1, ROC/PR-AUC;
- accuracy/balanced accuracy, positive/negative BCE contributions;
- mean raw score, prevalence, raw Brier, entropy, confidently wrong fraction,
  positive/negative score quantiles.

Predictions retain truth/mask arrays for later reproducible analyses. Probe and
snapshot hashes bind their provenance. The callback checks that its inference
did not advance the optimizer counter and never modifies Keras callback logs.
The existing val_loss stopping signal/patience is unchanged. Raw sigmoid/Brier
values are weighted-objective diagnostics, not validated clinical probabilities.

## Cache preparation and verification

The generic cache CLI now refuses an existing output directory and reports
progress, preventing accidental overwrite of completed cache data.
The new cache is prepared from audited **development audio only** at:

```text
/home/vinend/auriscore-lung-fixed-reference-20261110/cache/
5548481b0d3e371c65f20f6790b6c958b049890cfbf528dc43e310c33967e9c7
```

The original Linux cache and all L006–L018 artifacts remain intact. Audit,
recordings and events manifests are copied byte-for-byte to the new cache's
parent manifest directory. `verify_lung_feature_cache.py` checks all windows'
non-feature arrays, source/group/split index equality, finite features and every
consecutive shared-frame overlap against the old cache. It also computes
TRAIN-only normalization and reports supervised feature clipping. This is
preparation/verification, not model fitting or test evaluation.

Full measured verification is complete:

- All **46,308 windows** retain identical non-feature arrays: labels, masks,
  timestamps and start offsets. Parsed source/group/split index rows are equal.
  Index CSV byte hashes differ because it was regenerated; parsed equality is
  tested independently and both hashes are retained in the report.
- **38,590 consecutive overlap pairs** have maximum shared-frame feature
  difference **0.0**, within the predeclared 1e-5 tolerance.
- TRAIN-only frequency statistics are finite, minimum std 10.1667. The fraction
  of supervised feature cells beyond the normalization +/-5 clip is 9.4474e-7.
- Real-cache v7 preflight passes, selecting wheeze/rhonchi/crackle.
- RTX 5060 smoke check on four real development feature windows produces
  [4,309,3] output, ten finite gradient arrays and a complete saved trajectory
  snapshot. It uses an **untrained model**, performs zero optimizer updates and
  is not a model performance result. Positive weights match L017 because targets
  and fitting population remain unchanged.

Evidence is under `artifacts/lung-launch/fixed-reference-checks-20261110/`:
cache-build log, complete cache verification, focused/full test logs and baseline
regression evidence; `cache-verification/report.json`, `gpu-smoke.json`,
`gpu-smoke-fold/trajectory/` and `new-cache-preflight.json` bind the final checks.

## Verification status and remaining limitations

40 focused tests pass, including actual trainer policy wiring without fitting,
unchanged legacy/shared tensors, grouped probe selection, two epoch snapshots,
last-state recovery with the actual Keras EarlyStopping callback, and unchanged optimizer
counter/Keras logs. GPU-capable WSL/TensorFlow is used for model tests.

The broader Lung/source/spectrogram/Heart/Abdomen check reports 297 passed and one
failure: `test_abdomen_inference.py::test_preprocessing_statistics_frozen_and_validated`.
It also fails on source exported directly from Git HEAD, before these changes:
the existing preprocessing validator does not reject a zero frequency std at
constructor time. Baseline package location and failure are saved in
`baseline-abdomen-repro.log`. This work does not alter Heart/Abdomen validators
or conceal the existing failure. New guarded checks finish in the final focused
test log; the broad result is not claimed as an all-green suite. The final
feature/trajectory subset has ten passing tests after confidence-stat additions
and actual EarlyStopping restoration verification.

No new optimizer training is started by this implementation task. No improved
accuracy, shifted best epoch or deployment eligibility can be claimed until a
new protocol-controlled run uses this cache. Source diversity, interval versus
click-level crackle supervision and independent-patient validation remain open.
Official test audio/labels are not read by preparation or telemetry.
