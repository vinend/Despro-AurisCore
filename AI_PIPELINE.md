# AI_PIPELINE.md

User-authorized L019 launch (2026-11-10): `EXP-L019-fixed-reference` compares the
verified Lung fixed-reference/floor cache against L017 with the same model,
objective/LR/fitting rows and newly saved per-epoch trajectory. A frozen standalone
protocol binds control/cache/code/policy/package hashes and fixed evaluations.
WSL supervisor PID 26483 / trainer 26498; startup passes preflight and confirms
RTX 5060 GPU:0 before TRAIN statistics. No performance gain or promotion is
claimed. Official test stays sealed. See AI-Pipeline/docs/lung_l019_fixed_reference.md.

Fixed-reference Lung implementation (2026-11-10): opt-in `lung-fixed-logmel-v1`
uses absolute reference/floor while preserving the shared Heart/Abdomen and legacy
Lung path. v7 training policies save every epoch's pre-restoration weights,
fixed grouped probe predictions and class/source confidence/ranking metrics with
optimizer update counts. Stopping/threshold selection remain unchanged. A new
immutable feature cache is prepared separately; old models require their old
features/normalization. No fitting is launched by this task. See
[implementation and evidence](AI-Pipeline/docs/lung_fixed_reference_trajectory.md).
Completed verification: all 46,308 non-feature payloads/parsed split-index rows
match the original; 38,590 overlap pairs have maximum feature difference zero.
New-cache preflight and actual GPU gradients/trajectory evidence pass without
optimizer updates. No accuracy result or new training launch is claimed.

Completed L016–L018 deep review (2026-11-10): all runs complete and pass numerical
parity, but fail the research performance gate. L017 common-L016-weight loss is
0.98844 versus L016 0.98338; L018 is worse. A read-only paired feature/inference
probe establishes window-relative dB reference as a cause of same-audio overlap
prediction inconsistency; device-conditional crackle failure persists. Later
epoch ranking/calibration cannot be reconstructed from best-only checkpoints.
Six focused tests pass; no new fitting, thresholds or official-test access.
See [deep review and next protocol](AI-Pipeline/docs/lung_l016_l018_deep_review.md).

Numerical/objective Lung continuation (2026-11-10): opt-in v6 freezes stable BCE,
deterministic float32 runtime and explicit TRAIN-only weighting/empty-window
settings. L016 establishes that numerical boundary against L015; L017 changes
only the weight estimator; L018 changes only empty-window fitting inclusion.
All retain the original cache, normalization scope, split and three-label task.
Legacy policies are unchanged; v6 final-package fitting is rejected. Full suite:
148 pass; three preflights and actual GPU gradients/reload pass. See
[bounded protocol and limitations](AI-Pipeline/docs/lung_objective_experiments.md).

L015 investigation (2026-11-10): three-sound fitting completed at epoch 10,
restoring epoch 2. The early optimum persists. A read-only full-cache audit finds
device/prevalence shift, a crackle device-only PR-AUC baseline above the CNN,
empty supervised windows and a frame-weight/per-window-reduction mismatch.
Manual probability clipping loses extreme-example gradients synthetically;
its causal role is unproven at the best checkpoint. No training defaults or
weights were changed. The next protocol must isolate versioned loss/objective
changes and source-stratified diagnostics before further fitting. See
[investigation and evidence](AI-Pipeline/docs/lung_l015_pipeline_investigation.md).
Official test remains sealed; no model is activated.

Three-sound Lung update (2026-11-10): the user requests temporary training of
wheeze/rhonchi/crackle only. L015 removes stridor from the L011 head with all
other declared training/data settings fixed. The canonical three independent
sigmoid outputs use original masked cache columns 2/3/5. 135 tests and preflight
pass. GPU supervisor launched as WSL PID 14888; no metrics or promotion claimed
at launch. Official test and broader Lung product requirements are unchanged.
See AI-Pipeline/docs/lung_three_sound_experiment.md.

Compact Lung update (2026-11-10): a bounded L010/L011 error review reproduced
60 windows from ten recordings without mismatch, followed by user listening
confirmation. Opt-in v5 bottlenecks reduce phase/sound models from about 269k
to 93k parameters while preserving time outputs and all original HF supervision.
132 tests and actual GPU forward/backward pass. L013 vs L010 and L014 vs L011
are launched serially under WSL PID 11139; startup has L013 active. No new
performance claim, threshold-rule change, test opening or model activation is
made at launch. See AI-Pipeline/docs/lung_compact_experiments.md.

Completed Lung review (2026-11-10): L012 restored epoch two and stopped at ten
because of eight stale validation-loss epochs, not a ten-epoch cap. Same-population
saved-artifact analysis finds macro PR-AUC 0.39225 versus L006 0.40436 and joint
phase predictions 70.27% versus 59.33%. TRAIN class weights changed with source
addition; common-L006-weight loss reconstruction remains worse (0.84003 versus
0.82694). L007/L008 also select epoch two. This read-only review changes no
threshold, model, split or active run. See AI-Pipeline/docs/lung_l012_review.md.

Lung source-addition update (2026-11-10): user-authorized L012 adds pinned,
patient-disjoint SPRSound 2022 TRAIN acoustic windows while preserving HF
validation. 585 quality-eligible recordings / 85 source patients add 2,181
windows; source stridor support remains just one event/patient. Missing I/E and
unannotated intervals are masked; category completeness is an explicit assumption
inside annotated events only. Source acquisition, cache builder and bounded-GPU
entrypoint are implemented, with 116 passing Lung/source tests. WSL PID 3621
reached TRAIN statistics with GPU active. No final metrics, official-test opening
or package activation occurred at launch. See AI-Pipeline/docs/lung_sprsound_training.md.

Lung generalization update (2026-11-10): L006 completed and remains research-only.
Its saved prediction/boundary diagnostics motivate five independent GPU probes,
L007–L011 (lower initial LR, weight decay, frequency masking, phase-only and
sound-only heads). Versioned v4 policies preserve original feature caches,
group splits and label masks; subset outputs are research-only. The serial queue
freezes code/config/baseline provenance before fitting, retains best checkpoints
and saves per-class same-population comparisons after each completed run.
No official test is opened or package activated. See
AI-Pipeline/docs/lung_l006_findings.md and lung_dataset_expansion.md in that folder.

Lung execution update (2026-11-10): the user authorizes local development
training with GPU and confirms sampled annotation/audio review. Ubuntu WSL2 /
TensorFlow 2.21.0 passes actual model forward/backward on RTX 5060; 85 Lung tests
pass. EXP-L006-temporal-cnn-context is launched as WSL PID 2489, with startup
reaching TRAIN statistics. Its only declared model change against L003 is
temporal dilation 1 -> 16. Original L003 artifacts are absent locally, so a
cross-runtime comparison remains exploratory. No completed L006 metrics exist
at launch, official test remains sealed and no package is activated. See
LUNG_IMPROVEMENT_PLAN.md and artifacts/lung-launch/EXP-L006-20261110/ within
AI-Pipeline for protocol/runtime/test/launch evidence (the plan is at repo root).

## RD-H022-TMIL-P1

The progress_heart research run uses a fold-matched H022 trunk, Temporal MIL and a fit-only H022 precision comparator. The [destination runbook](AI-Pipeline/research/h022_temporal/README.md) defines supervision, calibration and the frozen gate.

The integration also preserves the older H020–H022 research source and H021
audit evidence from `reconcile/research-master-20261009`. The historical H022
launch lock still binds its original Linux checkout and source hashes. Merging
the source does not authorize a replay from master. H020's historical embedding
inputs are not bundled. No prior WebApp or dataset snapshot replaces the current
integration.

## 1. Scope

This document governs **trainable AI work for the current Heart Murmur branch** and its deployment path.

It does **not** define the entire Heart product. Heart also requires Rhythm DSP and Cardiac Event DSP as defined in `PRD.md` and `ARCHITECTURE.md`.

Current trainable Heart task:

```text
Murmur Absent  = 0
Murmur Present = 1
Unknown        = excluded from supervised evaluation
```

Do not silently replace this target with a disease/outcome label.

---

## 2. Input and representation

Expected source:

- auscultation audio;
- known sampling rate;
- Heart examination mode;
- participant/source identity sufficient for leakage-safe grouping.

Nominal product acquisition rate: **8000 Hz**.

Public datasets may use other rates. Resample explicitly and record source and target rates.

Reference feature path for the current CNN family:

```text
raw audio
-> mono conversion
-> resample
-> amplitude / quality validation
-> segmentation
-> configured filtering/denoising if used
-> log-mel spectrogram
-> normalization fitted only on allowed training data
-> CNN input tensor
```

Every preprocessing parameter must be versioned/configured.

---

## 3. Dataset and leakage discipline

Every dataset item should preserve enough provenance to identify:

```json
{
  "source": "",
  "subject_id": "",
  "recording_id": "",
  "label": "",
  "murmur_label": "",
  "auscultation_location": "",
  "sample_rate": 0,
  "duration_seconds": 0,
  "split": ""
}
```

Participant/source grouping is mandatory where the dataset supports it.

Segments or multiple recordings from the same participant must not be distributed across evaluation partitions in a way that leaks participant identity.

### Split roles

- training / inner validation: fitting and early stopping;
- train-only CV / OOF: model/threshold selection when required by the experiment protocol;
- external validation: only after a predeclared eligibility gate;
- sealed test/holdout: final locked evaluation only.

Never optimize on the sealed holdout.

---

## 4. Current label semantics

For the CirCor murmur work, the current supervised target is participant-level murmur status.

Source location annotations may identify declared murmur locations, but an omitted location is not automatically a confirmed negative unless the source semantics explicitly justify that interpretation.

If a training experiment changes how declared/outside-declared recordings are supervised, document the rule in the experiment protocol before training.

---

## 5. Augmentation

Apply augmentation to training data only.

Candidate conservative augmentation may include:

- small time shifts;
- low-level additive noise;
- gain variation;
- limited time/frequency masking where physiologically reasonable;
- other transformations only when justified and reproducible.

Avoid transformations that destroy murmur timing/spectral structure.

Record augmentation probability and parameters in config.

---

## 6. Model family

Current baseline family:

- CNN using log-mel spectrogram input.

Research may evaluate alternatives such as:

- dropout / normalization changes;
- class weighting;
- focal or hard-negative-aware loss;
- learning-rate/scheduler changes;
- site-aware or participant-level aggregation/MIL;
- calibration/score alignment;
- representation changes.

Prefer one-factor experiments when possible.

Do not assume a deeper/larger CNN is automatically better.

---

## 7. Current benchmark/history snapshot

### H014 — frozen historical external-validation benchmark

Experiment:

`EXP-H014-cnn-per-frequency-augmentation-declared-positive-only`

Validation:

```text
Sensitivity   0.9167
Specificity   0.7755
Precision     0.5000
F1            0.6471
ROC-AUC       0.9056
PR-AUC        0.8108
Confusion     [[76,22],[2,22]]
```

Interpretation: high sensitivity, but false positives remain the main weakness. H014 is an integration/development benchmark, not a final diagnostic-grade claim.

### H015 — end-to-end site-aware MIL

Train-only OOF ranking was near random (ROC-AUC 0.506); the experiment failed its eligibility gate. External validation was not opened.

### H016 — fold-local acoustic pretraining + frozen site-aware MIL

Train-only OOF restored ranking (ROC-AUC 0.873, PR-AUC 0.788), but at 0.90 sensitivity it produced TN/FP/FN/TP = 190/268/11/99 and F1 0.415. External validation was not opened.

### H017 — hard-negative-aware participant training

Weighted focal training reduced OOF false positives from 268 to 207 with FN unchanged at 11: sensitivity 0.90, specificity 0.548, precision 0.324, F1 0.476. The gate failed; external validation remained closed.

### H018 — participant ranking margin

Adding a participant ranking term yielded OOF TN/FP/FN/TP = 263/195/11/99, sensitivity 0.90, specificity 0.574, precision 0.337, F1 0.490, ROC-AUC 0.891, PR-AUC 0.792. The 12-FP reduction from H017 was modest; external validation remained closed.

### H019 — uniform acoustic pooling

Replacing attention with uniform pooling yielded OOF 257/201/10/100, sensitivity 0.909, specificity 0.561, precision 0.332, F1 0.487, ROC-AUC 0.887, PR-AUC 0.789. It did not improve on H018; the gate failed and external validation remained closed.

### H020 — regularized linear participant head

With frozen acoustic embeddings, uniform mean pooling, outer-training-only StandardScaler, and nested train-only L2 logistic C selection, OOF was 279/179/11/99 at threshold 0.1623002392: sensitivity 0.90, specificity 0.609, precision 0.356, F1 0.510, ROC-AUC 0.892, PR-AUC 0.814. Simpler participant classification helped but left substantial false positives. External validation remained closed.

### H021 — fold-local hard-negative acoustic mining

The current strongest TRAIN-only result used leakage-safe, fold-local Stage-1 hard-negative weighting. Among 568 participant OOF predictions, threshold 0.19225345646277395 gave TN/FP/FN/TP = 341/117/11/99, sensitivity 0.90, specificity 0.7445, precision 0.4583, F1 0.6074, ROC-AUC 0.9028, and PR-AUC 0.8302. FP fell by 62 from H020 while FN stayed at 11. The full engineering gate still failed. Five fold-evaluation pipelines exist, but no final all-TRAIN deployment model or predeclared deployment ensemble exists. External validation and sealed test remain closed.

### H022 — prepared experiment, not started

`EXP-H022-fold-local-hard-negative-contrastive-representation` adds one fixed supervised representation-separation loss at H021's 64-dimensional Stage-1 embedding. It reuses the five audited H021 outer-training hard-negative inventories (211, 215, 215, 212, 208 selected recordings); global H021 OOF false-positive identities are not used as supervision. Protocol SHA-256: `ab7331b77e92ba8353706d60be1606434095f44915d10e10ab1294f46452b913`. In the WSL research checkout, focused preflight tests and `./scripts/start_h022.sh --check` passed with TensorFlow 2.20 and GPU detection. **Training has not started; no H022 metrics exist.** External validation and sealed test remain closed.

---

## 8. Evaluation requirements

Do not report accuracy alone.

At minimum report:

```text
Dataset/split provenance
Experiment ID
Model/preprocessing version
Evaluation unit/population
Threshold-selection method
Threshold
Accuracy
Precision
Recall / Sensitivity
Specificity
F1
Balanced Accuracy when relevant
ROC-AUC
PR-AUC
Confusion Matrix
```

For imbalanced murmur screening, emphasize:

- sensitivity;
- precision;
- specificity;
- F1;
- PR-AUC;
- false-positive / false-negative counts.

### Current engineering direction

Internal development targets:

```text
Sensitivity >= 0.90
Specificity >= 0.85
Precision   >= 0.65
F1          >= 0.75
ROC-AUC     >= 0.92
PR-AUC      >= 0.85
```

These are engineering goals, not clinical/regulatory standards.

The report's historical F1 >90% statement remains an aspirational project target, not evidence that current models already meet it.

---

## 9. Threshold selection

Threshold selection must follow a predeclared experiment protocol.

For sensitivity-first screening:

1. satisfy the declared minimum sensitivity;
2. optimize the declared secondary metric only among eligible thresholds;
3. report the complete precision/specificity/FP/FN tradeoff.

Never tune threshold on the sealed test set.

Do not confuse threshold improvement with ranking improvement.

---

## 10. Early stopping

Early stopping must be defined before training.

For the current pipeline, validation loss is an acceptable training-stop signal. Threshold-dependent metrics such as F1 are evaluated after training unless the experiment explicitly studies a different predeclared stopping rule.

Do not change the stopping metric mid-run because intermediate results look favorable.

Long training follows the non-polling rule in `AGENTS.md`.

---

## 11. Experiment artifacts

Each completed experiment must use a unique immutable directory:

```text
AI-Pipeline/results/EXP-HNNN-name/
```

Store as applicable:

- `protocol.json`;
- `config.json`;
- `metrics.json`;
- predictions CSV;
- fold metrics;
- threshold tradeoff;
- training history;
- model checkpoint;
- ROC/PR plots;
- score-distribution/calibration plots;
- summary Markdown/JSON.

Do not overwrite prior completed experiment artifacts.

---

## 12. Model selection / external validation gate

A candidate may replace the current development candidate only when:

1. the comparison protocol is valid and leakage-safe;
2. the improvement is reproducible;
3. sensitivity is not traded away merely for prettier accuracy/precision;
4. inference cost remains practical for smartphone deployment;
5. the external-validation gate is explicitly satisfied before external validation is opened.

External validation should not become an iterative hyperparameter playground.

---

## 13. Deployment

Deployment target: offline smartphone-compatible inference.

```text
trained candidate
-> validated/frozen candidate
-> export
-> quantization candidate
-> mobile integration test
```

The report proposes INT8 deployment. Before accepting quantization, compare:

- sensitivity;
- precision/F1;
- model size;
- inference latency;
- any preprocessing compatibility changes.

Every exported model must include metadata such as:

```json
{
  "model_name": "auriscore-heart-murmur-cnn",
  "model_version": "",
  "preprocessing_version": "",
  "threshold_version": "",
  "threshold": null,
  "sample_rate": 8000,
  "input_shape": [],
  "classes": ["absent", "present"],
  "dataset_version": ""
}
```

Never ship a bare model artifact without metadata.

---

## 14. Boundary with Heart DSP

The shared `AnalysisService` is now available for real recorded PCM/WAV input,
quality validation and Heart/Abdomen routing. Its persistent worker retains
explicitly registered backends across requests. It defaults to Heart DSP with
Murmur unavailable. Verified final packages can register Heart Murmur and Abdomen
window activity; unconfigured Abdomen remains unavailable. Deployment eligibility is not inferred
from saved candidate files. See `AI-Pipeline/docs/analysis_service.md`.

Step 1 model auditing is implemented by `scripts/audit_model_candidates.py` in
`AI-Pipeline`. It validates archives, preprocessing and threshold provenance,
optionally checks synthetic inference, and packages immutable engineering
candidates. A005 is a preliminary Abdomen candidate; no Heart deployment model
is selected. See `AI-Pipeline/docs/model_candidate_audit.md`. This does not train
models or open additional evaluation splits.

The unified Heart result combines an available Murmur AI output with:

- Rhythm DSP output;
- Cardiac Event DSP output.

AI research code must not fabricate BPM, S1/S2, S3/S4, or rhythm results merely to fill the unified schema. Prototype DSP modules now provide candidate outputs independently; they still require labeled validation before clinical claims.

### H021 development freeze (2026-10-09)

`EXP-H021-fold-local-hard-negative-acoustic-mining` is the strongest current
**TRAIN-only development candidate**, based on 568 participant-exclusive OOF
predictions: threshold 0.19225345646277395, TN/FP/FN/TP = 341/117/11/99,
sensitivity 0.9000, specificity 0.7445, precision 0.4583, F1 0.6074,
ROC-AUC 0.9028, PR-AUC 0.8302. Relative to H020, FP fell by 62 with FN
unchanged. These are development estimates, not clinical performance. H021
fails the predefined external-validation eligibility gate; external validation
and sealed test remain unopened. H022 preparation was authorized separately;
this freeze does not authorize its training or change H021's result.

The [H021 freeze package](AI-Pipeline/analysis/HEART-DEVELOPMENT-FREEZE-H021/README.md)
records the locked protocol and SHA-256 hashes. H021 saved five outer-fold
evaluation pipelines, each with its own acoustic checkpoint, normalization,
scaler and logistic head. It did **not** save a final all-TRAIN deployment
model or predeclare an inference ensemble. The pooled OOF threshold is not a
threshold for one fold, a new ensemble, or a single recording. The Heart WAV
demo therefore keeps Murmur explicitly unavailable; it does not load H021
research fold weights. A separately specified deployment model and evaluation
decision is needed before Murmur inference can be connected.

## Recording-level Heart inference (step 3)

heart_inference.py implements frozen Keras scoring, recording aggregation, verified
final-model packaging, and unified Heart DSP/Murmur results. This checkout still has
no approved final package with recording-level threshold evidence. H021 research
folds and older candidate thresholds are not deployment rules. See
AI-Pipeline/docs/heart_inference.md for the contract and existing backend connection.

## Window-level Abdomen inference (phase 4)

abdomen_inference.py implements the frozen binary bowel-activity adapter and
immutable final-package verification. analyze_recording.py can retain both organ
backends and accept WAV paths, WAV bytes on stdin, or JSONL PCM/base64 recordings.
A005's window threshold is not used as a recording diagnosis or bowel event rate.
Its current single-subject evaluation does not satisfy the final-package contract.
No threshold selection, training or sealed evaluation was performed. See
AI-Pipeline/docs/abdomen_inference.md for the versioned result and evidence fields.

## App integration (phase 5)

The WebApp now sends captured PCM/recorded WAV to the retained shared worker for
Heart/Abdomen. Uploaded files, captured mock audio and device audio use real
analysis; simulator provenance remains visible. Only verified final packages
activate model-backed output. No candidate, threshold or training decision changes
in this phase. See WebApp/docs/organ-analysis.md for local setup and limitations.

## Lung implementation — development training authorized

Pinned HF_Lung_V1 acquisition, strict labels/date-group manifests, masked temporal
log-mel caches, guarded development/final CNN commands, development/one-shot
holdout evaluation and package/inference integration are implemented. EXP-L*
experiments are separate from Heart. The user reports completed Linux EXP-L002
development training with weak class discrimination; no model is approved.
Test labels remain sealed; preflight never trains. Development training is now
user-authorized; EXP-L001 stopped during preparation without a saved checkpoint.
Use a fresh output directory when retrying. Uncertainty reports, model comparisons, eligibility
and TFLite/physical validation follow authorized experiments. See
AI-Pipeline/docs/lung_training.md for exact commands and limits.

The corrected `lung-cache-dataset-v2` streams cached tensors after a reproducible
full filename shuffle each training epoch. Validation order is fixed. Known
batch cardinality retains every window and final partial batch; Keras fit-level
shuffling is disabled explicitly. Both development/final trainers use this path,
and source.json records the version/policy. Existing caches and split/threshold
rules are unchanged. Compare a fresh development experiment with the saved Linux
baseline; no training or official-test evaluation was launched while fixing code.

Development diagnostics now inspect complete caches and optionally hash-bound
saved development predictions without fitting models or selecting thresholds.
They report supervised class prevalence, TRAIN weights, phase overlap, tails,
per-device support and score distributions versus always-positive baselines.
HF D labels represent crackle-containing intervals. Successful parsing does not
independently establish exhaustive annotation coverage; negative supervision
inside respiratory annotations remains a research assumption requiring review.
See AI-Pipeline/docs/lung_training.md for the Linux diagnostic command and limits.

Lung temporal localization is executable for completed development checkpoints:
`localize_lung_recording.py` exports frame scores and scored onset/offset
candidates for a real WAV; `evaluate_lung_localization.py` reconstructs complete
held-out recording timelines from saved predictions and reports one-to-one event
and matched-boundary metrics. No retraining or threshold selection is performed.
Version lung-frame-events-v2 is shared with future approved inference packages,
whose final selection/evidence must explicitly freeze it. Legacy evidence keeps
v1 behavior. The existing Lung API schema is unchanged and research models remain
ineligible for live activation. See AI-Pipeline/docs/lung_localization.md.

## Lung training-only LR policy

The opt-in `AI-Pipeline/configs/lung_training_plateau.json` halves learning rate
after two validation-loss plateau epochs, down to 1e-6, before the existing
eight-epoch early stopper. It preserves initial LR, model, splits, supervision,
cache identity, and best-weight restoration. Omission preserves fixed-LR runs.
Experiment provenance records the normalized policy/hash; history records LR
used and next LR. Final selections using this policy must freeze per-epoch rates
from development; final fitting replays them without validation/test callbacks.
See `AI-Pipeline/docs/lung_training.md` for EXP-L004 Linux commands. This is an
unmeasured research experiment, not a deployment or performance claim.

Lung training additionally emits timestamped process events and persists
`process.jsonl` in each created experiment. Preparation, visible GPU/CPU runtime,
fold support, normalization progress, epoch losses/LR/checkpoint/stop decisions,
development prediction and evaluation are reported. Batch/window updates are
time-throttled (`--progress-interval`, default 30 seconds); fitting and selection
rules are unchanged. Final fitting remains free of validation/test callbacks.

The next Lung regularization experiment (EXP-L005) opts into
`configs/lung_training_dropout.json`: versioned policy v2 explicitly sets model
dropout 0.4 and constant LR. Relative to EXP-L003, only dropout changes from 0.2;
cache geometry/identity, masks, loss, splits and selection rules are unchanged.
Historical v1/default policies keep 0.2. Both development and final builders use
the policy's frozen dropout, retained in the saved Keras model and process logs.
EXP-L004 selected epoch 2 before any LR reduction; its later schedule did not
produce a better checkpoint. Stronger dropout is unmeasured pending Linux fitting.

Lung EXP-L006 freezes v3 temporal dilation 16, default dropout 0.2 and constant
LR to isolate context span against EXP-L003. The existing Conv1D weights/shapes
and parameter count are unchanged; theoretical context spans 71 frames/1.184 s
instead of 11 frames/224 ms. Frame outputs/cache/splits/loss remain fixed; saved
models preserve dilation, and final selections must retain the v3 policy.
Symmetric padding includes future samples and boundary zeros, so this does not
claim causal streaming inference. `review_lung_alignment.py` first creates sampled
source/cache checks plus listenable development timelines. Mechanical agreement
does not verify acoustic annotations; human review is required before the next
authorized Linux run. No test labels or model fitting are involved in the review.
