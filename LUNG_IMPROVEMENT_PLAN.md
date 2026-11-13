# Lung improvement and local GPU training plan

Updated: 2026-11-10 (Asia/Jakarta).

Compact execution update: following explicit authorization and a new user-confirmed
ten-recording error review, L013/L014 are launched serially under WSL PID 11139.
L013 is active at startup. Parameter count drops from about 269k to 93k with
time outputs/cache/labels unchanged; 132 tests and GPU forward/backward pass.
No improvement is claimed before evaluation. See
`AI-Pipeline/docs/lung_compact_experiments.md`; older entries below are historical.

Latest execution: the user authorized immediate source expansion and fitting.
L012 (HF + audited SPRSound 2022 TRAIN) was launched as WSL PID 3621 with a 3-GB
GPU cap; initial preflight/runtime reached TRAIN statistics. It adds 2,181 windows
from 585 recordings / 85 source patient groups, preserving all HF validation.
The other probes remain independent. All 116 Lung/source tests pass. New source
stridor support is only one event, so rarity remains a gap. No test labels opened,
package activated or completed L012 metrics claimed at launch. Details:
`AI-Pipeline/docs/lung_sprsound_training.md`. Earlier entries below record their
respective historical launch checkpoints.

Execution update: L006 completed in about 14m45s, restored epoch two and remains
ineligible for deployment. Read-only diagnostics/localization are recorded in
`AI-Pipeline/docs/lung_l006_findings.md`. The user subsequently authorized all
five separate L007–L011 probes; their fixed queue is
`AI-Pipeline/configs/lung_improvement_queue.json`. Existing snapshot/launch notes
below describe L006 at launch, not its present status. Additional dataset
assessment is in `AI-Pipeline/docs/lung_dataset_expansion.md`; no source is merged.

L007–L011 queue launch checkpoint: 2026-11-10 approximately 09:43 WIB, WSL PID
384, initial active experiment L007. All 108 Lung tests pass. Each run is an
independent control against L006; there is no automatic promotion, additional
dataset use or official-test opening. Queue protocol/status/per-run logs are
under `AI-Pipeline/artifacts/lung-launch/EXP-L007-L011-20261110/queue/`.

## Scope and current authorization

This work serves PRD section 7: respiratory phases and acoustic-event screening.
The user authorized Lung development training on this Windows computer and
explicitly requested GPU use. Prepare the existing TensorFlow pipeline under
WSL2; do not replace it with CPU training or a different framework silently.
This authorization does not open the official test or activate a deployment model.

- Subsystem: Lung research/training and local runtime setup.
- Upstream: pinned HF_Lung_V1 development audio, audited annotations, date groups,
  and the existing immutable feature cache.
- Downstream: saved development predictions, localization/error analysis, then
  a separately selected frozen package for the existing Python worker/WebApp.
- Scope: research; no production API/schema, device protocol or clinical claim changes.
- Keep split assignments, masks, label semantics and negative-supervision
  assumptions unchanged for the immediate experiment.
- Preserve pending local L006/alignment changes and all existing experiments.

## Evidence and limitations

The local cache contains 28,620 TRAIN and 17,688 validation windows. Groups are
shifted recording dates, not verified patient identities. Unknown annotation
coverage is not evidence that an acoustic finding is absent. Source label D
means a crackle-containing interval, not an individually labeled crackle click.

Linux L003/L004/L005 results are documented user-supplied results; their complete
checkpoints and prediction archives have not been verified on this computer.
L003's reported best validation loss was 0.8388. L004 restored epoch two before
LR reduction; later LR reductions did not improve its selected checkpoint.
L005's reported best loss was 0.8241, but its joint phase-positive fraction was
87.3% against about 1.1% target overlap. Lower loss alone is insufficient.
Some older documents still describe L005 as pending; the reported result must
be reconciled against original artifacts before quantitative model selection.

Reuse Heart/Abdomen's experiment discipline, not their task-specific labels,
architectures, thresholds or claimed performance. In particular, hard-coded
perfect metrics in `scripts/package_active_models.py` are not evaluation evidence.

## Phase A: runtime and annotation readiness

1. Use a new isolated environment; the copied Windows `.venv` points to a
   previous user's Python installation and is unusable as-is.
2. Native Windows preflight uses ignored `.runtime/lung-preflight/` with the
   pinned base requirements. This environment has no TensorFlow/GPU runtime.
3. Enable Windows Virtual Machine Platform as Administrator and restart when
   required. BIOS virtualization is reported enabled. Install Ubuntu under WSL2.
4. In WSL use Python 3.11 or 3.12 and a separate venv, install base requirements,
   `tensorflow[and-cuda]==2.21.0` and `psutil==7.0.0`. Keep the Windows NVIDIA driver;
   do not install a Linux display driver inside WSL.
5. Verify `nvidia-smi`, TensorFlow GPU visibility, and an actual GPU forward and
   backward convolution. Device enumeration alone does not prove kernel support
   on the RTX 5060. If kernels fail, stop and resolve compatibility before fitting.
6. Run focused Lung tests and the real cache preflight. Regenerate sampled
   development source/cache alignment evidence, then listen and inspect the
   annotated timelines. Mechanical agreement does not establish acoustic accuracy.
   Resolve mismatches before training. Do not change labels automatically.

Runtime references: [TensorFlow installation](https://www.tensorflow.org/install/pip),
[WSL installation](https://learn.microsoft.com/windows/wsl/install), and
[NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).

## Phase B: immediate controlled experiment

EXP-L006-temporal-cnn-context was launched on 2026-11-10 at approximately 07:48
WIB as WSL PID 2489. Startup reached TRAIN statistics with GPU runtime active.
It has no completed evaluation result at this checkpoint.
Use a fresh output ID if that directory already exists; never overwrite it.

| Parameter | Frozen rule |
| --- | --- |
| Comparator | L003 temporal baseline, with original artifacts when available |
| One changed factor | Existing temporal Conv1D dilation 1 -> 16 |
| Policy | `AI-Pipeline/configs/lung_training_context.json` |
| Theoretical context span | 224 ms -> 1.184 s; parameter count unchanged |
| Other model settings | Dropout 0.2; same independent six sigmoid outputs |
| Features | Mono 8 kHz, 5 s windows, 96 mel bins, FFT 512, hop 128 |
| Cache | `fa2fc598295d3e8b71d8e34cee4ecc7c21866cb658f57367ca9aa5ff546cee14` |
| Seed / optimizer | 42 / Adam, constant initial LR 0.001 |
| Batch / epochs | 8 / maximum 50 |
| Early stopping | Validation loss, patience 8, restore best weights |
| Threshold selection | Existing per-class maximum-F1 development grid; no test access |
| Localization comparison | v2 decoder, minimum duration 0, merge gap 0, onset/offset tolerance 0.1 s |
| Data boundaries | Existing TRAIN/validation groups; official test sealed |

Symmetric context consumes future frames and includes zero padding near window
edges. It is not proof of causal streaming inference or improved accuracy.
Save protocol/config/code hashes, runtime versions and GPU evidence before fitting.
The trainer already saves source.json, process.jsonl, status.json, normalization,
checkpoint/history, model and development predictions/evaluation. Save the
environment inventory and launch record outside the immutable result directory.

Launch one standalone process only after readiness checks. Record PID, full
stdout/stderr and result paths. Do not repeatedly poll long-running fitting.
Use a later status inspection or explicit user request to review completion.

If original L003 weights/predictions are unavailable or hardware/runtime changes
prevent a fair comparison, perform a separately named matched-runtime baseline
replication before attributing an improvement to dilation. Do not silently reuse
the L003 ID or treat cross-machine differences as a one-factor causal result.

## Phase C: evaluation and decision

Report all classes separately, with masks, thresholds, class support and units:

- Accuracy and balanced accuracy derived from TN/FP/FN/TP, precision, sensitivity,
  specificity, F1, ROC-AUC and PR-AUC. Accuracy is not the primary selection metric.
- Positive prediction rate, always-positive F1/PR baseline and score distributions.
- Joint inhalation/exhalation conflict and target overlap on the identical valid population.
- One-to-one event F1 and matched onset/offset/duration errors on reconstructed
  recording timelines; explicitly state tolerance and matched-event support.
- Respiratory-rate and I:E errors only for sufficient unambiguous complete cycles;
  include availability/coverage so rejecting difficult records cannot inflate quality.
- Per-device and date-group performance, rare-class support, and group-level
  uncertainty. Overlapping frames/windows are not independent participants.

Development thresholds are selected on development data and scores are optimistic
selection estimates. Confirm a selected direction with predeclared grouped CV/OOF;
fit normalization, weights and learned selection rules within the permitted folds.
Bootstrap uncertainty at group level, preserving the selected decision rule.

L006 can be considered promising only if phase conflict improves alongside
discrimination/localization; suppressing positive predictions at the expense of
sensitivity is not enough. Report tradeoffs rather than claiming a single winner
from validation loss. This plan defines no clinical eligibility threshold.
Freeze quantitative per-class engineering gates with the team before final fitting
or opening the official test; `engineering_gate: null` remains unchanged now.

## Phase D: subsequent experiments, conditional on the evidence

These are planned comparisons, not implemented features or an automatic queue.
Reserve the actual unused experiment ID immediately before each authorized run.

| Order | Experiment | Implementation and controls |
| --- | --- | --- |
| 1 | Separate phase and sound tasks | Phase-only I/E and acoustic-only W/R/S/C outputs; version class-subset caches, retain the same groups/coverage, compare each head against the matching joint-model classes. Freeze an overlap policy before any exclusive phase head. |
| 2 | Class weighting | Compare current TRAIN-derived positive weights against unweighted masked BCE; preserve the chosen architecture, masks and data. Do not introduce focal loss simultaneously. |
| 3 | Longer-context alternative | Only if L006 supports the context hypothesis, compare a compact temporal/GRU alternative with matched preprocessing and an explicit parameter/latency budget. |
| 4 | Conservative augmentation | TRAIN-only noise/gain appropriate for stethoscope recordings; align any temporal transforms with labels and masks. Use representative device noise when available. |
| 5 | Error-directed sampling | Only after score/error review; select hard examples inside fitting groups, never from outer-held-out mistakes. Document group/class sampling balance. |
| 6 | Decoder study | Separate duration/gap or phase-consistency study using development/inner folds; freeze decoder version/settings and avoid comparing only frame F1. |

Do not launch every experiment merely because it is listed. After each completed
run, compare against the correct frozen control and decide the next one-factor test.
If annotation assumptions fail review, create a separate versioned target/mask
protocol and regenerate caches before further architecture comparisons.

## Phase E: frozen candidate and integration

1. Select a reproducible candidate from grouped development evidence; freeze
   architecture, preprocessing, normalization rule, epochs, thresholds and decoder.
2. Fit the final candidate under the existing locked selection protocol without
   validation/test callbacks or mutable LR decisions.
3. Open official test only through the explicit one-shot evaluation workflow after
   separate authorization. Retain failures; do not tune and retry on the same test.
4. Package only genuine hash-bound evaluation artifacts and an explicit decision.
   Do not manufacture metrics or auto-promote research checkpoints.
5. Validate existing `lung-analysis-v1` worker/API/UI behavior, unavailable/invalid
   states and null respiratory metrics with insufficient cycles.
6. Separately verify TFLite parity/latency, physical ESP32 audio robustness and
   native-mobile offline operation. Software tests do not establish clinical readiness.

## Local checkpoint on 2026-11-10

- RTX 5060 detected, 8,151 MiB VRAM; Windows driver 621.14.
- Following user setup, Ubuntu-24.04 runs under WSL2 with the hypervisor active.
  `nvidia-smi` in Ubuntu sees the RTX 5060. Python 3.12.3 is installed.
- An isolated Linux environment at `/home/vinend/.venvs/auriscore-lung` runs
  TensorFlow 2.21.0. The actual L006-shaped model passed finite forward/backward
  execution on GPU:0 with zero optimizer steps, using synthetic input only.
  CUDA library directories and ptxas PATH are scoped to this environment via
  ignored `.runtime/lung-cuda-env.sh`; no system toolchain files were replaced.
- Development code/cache were copied to a Linux snapshot for fitting; original
  data and pending working-tree changes remain preserved.
- Base dependency installation in `.runtime/lung-preflight/` completed.
- Cache/config/provenance preflight passed for 46,308 windows with dilation 16.
- Initial Windows base tests: 19 passed, 5 skipped (TensorFlow unavailable).
  Subsequent complete Lung tests under WSL/TensorFlow: 85 passed, zero skipped,
  with 123 dependency deprecation warnings. `pip check` reports no broken requirements.
- Sampled source/cache review: six recordings / 36 windows, zero mismatches.
  Evidence is ignored at
  `AI-Pipeline/artifacts/lung-launch/alignment-gpu-20261110/report.json` and
  `review.html`. The user subsequently confirmed listening/annotation review was
  completed and appropriate. This is sampled review, not exhaustive label validation.
- Linux snapshot: `/home/vinend/auriscore-lung-runs/EXP-L006-20261110`.
- Run: `AI-Pipeline/results/EXP-L006-temporal-cnn-context/`.
- Launch/protocol/test/runtime evidence:
  `AI-Pipeline/artifacts/lung-launch/EXP-L006-20261110/`.
- Protocol SHA-256: `70aca22bcbd7f50999bca04d45a5bdfcc5aeee4c352016c53951b5b87184137f`.
- Startup preflight passed for all 46,308 windows. The background process uses
  28,620 fitting windows / 94 date groups and 17,688 validation windows / 24 groups.
- Training was launched; no completed metrics yet. No official-test labels were
  opened and no inference package was activated. Active polling stops after launch.

See `AI-Pipeline/docs/lung_training.md` for existing commands and
`LUNG_TRAINING_PLAN.md` for the original end-to-end implementation plan.
