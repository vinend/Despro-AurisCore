# AGENTS.md

## Purpose

This file defines mandatory behavior for AI coding agents and human contributors working inside the AurisCore repository.

It exists to prevent agents from:

- forgetting product requirements while optimizing one subsystem;
- treating the Heart murmur CNN as the entire Heart product;
- inventing architecture or clinical functionality not approved by the team;
- silently changing medical assumptions or product claims;
- mixing research experiments with production integration code;
- optimizing superficial metrics while ignoring class imbalance and screening sensitivity;
- leaking validation/test information into training decisions;
- breaking contracts between ESP32, mobile, DSP/AI, backend, and tele-auscultation;
- committing datasets, generated models, caches, credentials, or machine-specific GPU tooling.

# 0. MANDATORY STARTUP SEQUENCE

Before a non-trivial change, the agent **must establish product context before editing code**.

Read, in this order:

1. `PRD.md`
2. `DECISIONS.md`
3. `ARCHITECTURE.md`
4. `INTEGRATION.md`
5. relevant subsystem docs:
   - AI work -> `AI_PIPELINE.md` + `TESTING.md`
   - implementation planning -> `IMPLEMENTATION.md` + `ROADMAP.md`
   - repository overview -> `README.md`

For a small local task, later reads may be limited to relevant sections, but **`PRD.md` must never be skipped for product, AI, or integration work**.

Before editing, identify:

- which PRD requirement the task serves;
- which subsystem is changing;
- upstream input;
- downstream consumer;
- research-only vs production/integration scope;
- whether an interface/schema changes;
- whether data-split, medical, or product assumptions change.

If the requested task conflicts with `PRD.md`, do not silently follow the conflicting implementation. Treat the mismatch as a product/architecture decision requiring explicit resolution.

# 1. DOCUMENT AUTHORITY

## Product scope

`PRD.md` is the source of truth for required product behavior and scope.

## Architecture decisions

`DECISIONS.md` records accepted architectural decisions.

An ADR may choose **how** to satisfy the PRD, but must not silently delete or redefine a product requirement. If product behavior intentionally changes, update `PRD.md` in the same change.

## Technical contracts

- `ARCHITECTURE.md` defines structure and boundaries.
- `INTEGRATION.md` defines interfaces and schemas.
- `AI_PIPELINE.md` defines AI research/training/deployment discipline.
- `TESTING.md` defines verification expectations.
- `IMPLEMENTATION.md` and `ROADMAP.md` define execution order.

## Code is implementation state, not product truth

Working code may be incomplete relative to the PRD.

If code implements only one branch of a required feature, do not redefine the product around existing code. Record the missing work as an implementation gap.

# 2. PROJECT CONTEXT

AurisCore is an offline-capable digital stethoscope / auscultation-support system with three product domains:

1. Heart
2. Lung
3. Abdomen

Selected software flow:

```text
ESP32-S3
   |
   | BLE audio / metadata
   v
Mobile Application
   |
   +--> signal quality / preprocessing
   +--> DSP / organ analysis
   +--> local AI inference where required
   +--> Clinical Decision Support UI
   +--> local/session storage
   +--> optional backend sync
   +--> optional WebRTC tele-auscultation
```

The system is an **assistive screening / decision-support prototype**, not a final autonomous diagnostic system.

Never generate UI copy, API behavior, documentation, or tests that turn unsupported model output into a definitive disease diagnosis.

# 3. CRITICAL HEART INVARIANT

## Heart is NOT one CNN

Every agent must preserve this product model:

```text
                         HEART AUDIO
                              |
                   preprocessing / quality
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
       RHYTHM DSP       CARDIAC EVENT DSP   MURMUR AI
              |               |               |
          BPM / beat       S1 / S2        probability
          intervals        systole /       + Present/
              |            diastole          Absent
              v               |
       rhythm category      S3 / S4
              |               |
              +---------------+---------------+
                              |
                              v
                    UNIFIED HEART RESULT
```

This is a hard product invariant unless `PRD.md` is intentionally revised.

### Branch A — Rhythm DSP

Required eventual outputs:

- BPM;
- beat/interval information;
- Normal / Tachycardia / Bradycardia / irregular-rhythm indicator.

### Branch B — Cardiac Event DSP

Required eventual outputs:

- S1/S2 event timing;
- systole/diastole timing;
- S3/S4 candidate timing;
- visualization annotations.

### Branch C — Murmur AI

Current trained AI target:

```text
Murmur Absent  = 0
Murmur Present = 1
Unknown        = excluded
```

Required output:

- murmur probability;
- threshold;
- Present/Absent screening result.

The Murmur model must not be silently converted into disease classification.

**An agent may spend an entire task improving Branch C, but it must not describe Heart as complete merely because Branch C works.**

# 4. CURRENT DEVELOPMENT DIRECTION

Current priority remains **Heart first**.

The current research-heavy branch is the Murmur AI/CNN. H021 is the strongest TRAIN-only development result; H022 is prepared but has not started. Neither is a deployment-ready final model.

Prototype Rhythm DSP, Cardiac Event DSP, and `heart-analysis-v1` aggregation are implemented and covered by synthetic engineering tests. Labeled-recording validation, robustness evaluation, visualization/annotation completion, physical hardware integration, offline mobile integration, and deployable Murmur inference remain required.

Lung and Abdomen remain required product domains but are later milestones unless the team explicitly parallelizes them.

Do not let temporary experiment priority become permanent product scope.

# 5. MEDICAL-SAFETY AND CLAIM RULES

Model/DSP output must be framed as assistive screening or acoustic findings.

Preferred language:

- `Murmur suspected`
- `No murmur detected`
- `Possible abnormal acoustic pattern`
- `Candidate S3 event`
- `Assistive screening result`

Avoid unsupported claims such as:

- confirmed disease diagnosis;
- definitive pathology;
- treatment recommendations;
- disease subtype labels not part of the trained/validated target.

If the implementation detects a signal feature associated with a disease, expose the feature first. Do not automatically promote it to a disease diagnosis.

# 6. BEFORE EDITING CODE

For every non-trivial task, identify:

1. Product requirement served.
2. Subsystem being changed.
3. Upstream input.
4. Downstream consumer.
5. Research-only vs production/integration path.
6. Whether a schema/interface changes.
7. Whether data-split or clinical assumptions change.

If an interface changes, update in the same work:

- `INTEGRATION.md`;
- `ARCHITECTURE.md` when structural;
- affected tests;
- `PRD.md` only if product behavior itself changes.

Do not hard-code undefined requirements into multiple modules. Use `TBD`, configuration, or one explicit assumption boundary.

Prefer small, isolated, testable changes over broad rewrites.

# 7. RESEARCH VS PRODUCTION BOUNDARY

Keep research experiments separate from mobile/integration code.

Research code may:

- train models;
- run cross-validation;
- generate metrics and plots;
- perform audits;
- create immutable experiment artifacts.

Production/integration code should:

- use a frozen/versioned model;
- use versioned preprocessing;
- expose stable result schemas;
- fail safely on invalid input;
- not depend on research notebooks or mutable experiment directories.

Do not make the mobile application reach directly into ad-hoc experiment files.

# 8. AI DATA GOVERNANCE

## No leakage

Participant/patient/source boundaries must be preserved.

If multiple segments/recordings originate from the same participant/source, do not distribute them across training/evaluation partitions in a way that leaks source identity.

## Split discipline

Use the protocol-defined hierarchy:

- training / inner validation for fitting and early stopping;
- train-only CV / OOF for research selection when specified;
- external validation only after a predeclared gate;
- sealed test/holdout only for final locked evaluation.

Never optimize against the sealed test set.

Never repeatedly inspect external validation results to guide many small experiment choices unless the documented protocol explicitly permits it.

## Target integrity

For the current Heart Murmur AI:

- target = `murmur_label`;
- do not silently swap to an outcome/disease label;
- Unknown labels are excluded from supervised evaluation according to the active protocol.

# 9. AI EXPERIMENT RULES

Every material AI experiment must have:

- a unique experiment ID;
- a one-factor or clearly justified change;
- an immutable output directory;
- config/protocol saved before evaluation;
- reproducible data split;
- seed where applicable;
- preprocessing provenance;
- threshold-selection rule;
- metrics and predictions saved to machine-readable files;
- before/after comparison against the appropriate benchmark.

Do not overwrite H014/H015/H016 or any prior completed experiment directory.

A failed experiment is still a valid research result and must not be hidden.

Do not cherry-pick metrics across different thresholds or evaluation populations.

# 10. REQUIRED MURMUR AI EVALUATION

Do not report accuracy alone.

At minimum report:

- accuracy;
- precision;
- recall / sensitivity;
- specificity;
- F1;
- balanced accuracy when relevant;
- ROC-AUC;
- PR-AUC;
- confusion matrix;
- selected threshold;
- class distribution;
- evaluation population/unit;
- dataset/split provenance.

For current screening-oriented optimization, false positives are a major practical weakness, but precision must not be improved by destroying sensitivity.

Current internal engineering direction:

```text
Sensitivity >= 0.90
Specificity >= 0.85
Precision   >= 0.65
F1          >= 0.75
ROC-AUC     >= 0.92
PR-AUC      >= 0.85
```

These are engineering goals, not clinical/regulatory standards.

# 11. THRESHOLD AND CALIBRATION DISCIPLINE

Threshold selection must follow the active experiment protocol.

For sensitivity-first screening experiments:

- enforce the declared minimum sensitivity first;
- optimize secondary metrics only among eligible thresholds;
- report precision/specificity/FP/FN consequences;
- never choose a threshold from the sealed test set.

Remember:

- F1 is threshold-dependent;
- ROC-AUC/PR-AUC describe ranking behavior;
- calibration changes probability interpretation but does not magically improve ranking;
- fold-scale mismatch and true class overlap are different failure modes.

# 12. EARLY STOPPING / LONG TRAINING

Use reproducible early-stopping rules defined before the run.

Do not switch the monitored metric mid-run because an intermediate result looks better.

For the current Murmur pipeline, validation loss is an acceptable training-stop signal while F1/precision/specificity are evaluated at a separately selected threshold after training, unless an experiment explicitly studies a different rule.

**LONG-RUNNING TRAINING MUST NOT BE MONITORED BY REPEATED AGENT POLLING.**

When long training is authorized:

1. prepare the experiment/config;
2. launch the standalone training process/queue;
3. report PID/log/result paths;
4. stop active polling;
5. inspect status later through repository status/summarization tooling.

Do not start training when the user asked only for code/documentation changes.

# 13. DSP IMPLEMENTATION RULES

Heart Rhythm/Cardiac Event DSP is product functionality, not optional visualization glue.

When implementing DSP:

- keep report-derived thresholds/timing values configurable;
- separate signal processing from UI rendering;
- produce timestamps/events in a machine-readable structure;
- test synthetic/known cases where possible;
- validate against labeled data before claiming clinical reliability;
- do not silently convert a heuristic into a disease diagnosis.

S1/S2/BPM/S3/S4/rhythm logic must be versionable independently of the Murmur CNN.

# 14. MOBILE / INTEGRATION RULES

The mobile UI must not depend on internal TensorFlow/Keras details.

Prefer service boundaries such as:

```text
AudioInputService
SignalQualityService
HeartAnalysisService
AIInferenceService
SessionRepository
DeviceRepository
```

Heart results should use a versioned schema capable of representing:

- signal quality;
- rhythm/BPM;
- cardiac events;
- murmur probability/result;
- visualization annotations;
- algorithm/model versions.

Do not keep an old minimal `prediction.label/probability` schema if it prevents the PRD-required Heart branches from being represented. Version the contract instead of silently overloading fields.

# 15. SIGNAL QUALITY / FAIL-SAFE RULE

Do not force a confident output from unusable audio.

If signal quality is insufficient:

- return an explicit invalid/low-quality state;
- preserve a reason code where possible;
- request re-recording or show a clear UI warning;
- do not fabricate BPM/events/model confidence.

# 16. CODING CONVENTIONS

## Python

Use:

- type hints for public functions;
- docstrings for non-trivial modules;
- deterministic seeds where practical;
- configuration files for experiment parameters;
- small testable functions;
- explicit exceptions/validation errors.

Preferred libraries when appropriate: NumPy, SciPy, librosa, pandas, scikit-learn, TensorFlow/Keras.

Do not add large dependencies without clear need.

## Flutter / Dart

Use:

- feature-based structure where practical;
- typed data models;
- state separated from widgets;
- service/repository boundaries;
- no large DSP/business-logic blocks inside UI widgets.

## Backend

Use:

- explicit request/response schemas;
- versioned endpoints for breaking changes;
- environment variables for secrets;
- structured logging;
- offline-safe mobile behavior.

# 17. REPOSITORY HYGIENE

Never commit:

- `.venv/` or runtime environments;
- Python caches;
- Node/package-manager caches;
- raw/private datasets unless explicitly approved;
- generated model binaries intentionally ignored by the repository;
- local CUDA executables/symlinks such as repository-local `ptxas`;
- API keys;
- passwords;
- private certificates;
- real patient-identifying data.

Respect `.gitignore`.

If a generated/local file causes Git errors, fix the repository-local artifact or ignore rule; do not delete system CUDA/toolchain files blindly.

# 18. SECURITY / PRIVACY

Use anonymized/generated development data whenever possible.

Sensitive data must not be logged unnecessarily, committed to Git, embedded in fixtures, or sent to cloud services without an explicit approved design.

Authentication/encryption statements in the report are design targets and must not be described as achieved compliance until implemented and verified.

# 19. TEST REQUIREMENTS

A change is not complete because it “runs once”. Add/update tests for changed behavior.

### AI

Test preprocessing shape/rate behavior, invalid inputs, deterministic grouping/splits, no leakage, threshold logic, aggregation logic, finite predictions, artifact schema, and holdout protections.

### Heart DSP

Test event-detector edge cases, no-event/noisy input, BPM calculation, interval/rhythm rules, timestamp ordering, and serialization into the unified Heart result.

### Mobile/integration

Test file-simulator flow, BLE disconnect/reconnect, waveform/recording, invalid signal state, full Heart result rendering, session save, and schema-version handling.

# 20. DOCUMENTATION UPDATE RULE

Whenever implementation changes documented behavior, update the relevant document in the same change:

- product requirement -> `PRD.md`;
- architecture -> `ARCHITECTURE.md` + ADR when significant;
- result schema -> `INTEGRATION.md`;
- model/training protocol -> `AI_PIPELINE.md`;
- test/acceptance behavior -> `TESTING.md`;
- work sequencing -> `ROADMAP.md` / `IMPLEMENTATION.md`.

Do not leave documentation knowingly inconsistent with merged implementation.

# 21. DEFINITION OF DONE

A normal software task is done only when:

- code runs;
- relevant tests pass;
- the PRD requirement remains satisfied;
- interfaces remain compatible or are versioned/documented;
- no secrets/private data/local artifacts are committed;
- relevant documentation is updated;
- failure behavior is defined;
- safety wording remains appropriate.

For AI model changes also require:

- reproducible config/protocol;
- before/after metric comparison;
- saved machine-readable evaluation artifacts;
- documented threshold rule;
- no prohibited validation/test usage;
- model/version update if exported.

For Heart product completion, consult the **Heart Definition of Done in `PRD.md`**. Murmur CNN completion alone is not Heart completion.

# 22. DEFAULT PRIORITY ORDER

Unless the user/team explicitly overrides it:

1. Continue disciplined Murmur research and define a separately evaluated deployment candidate; H022 requires an explicit launch decision.
2. Validate and stabilize the implemented Heart DSP prototypes on representative labeled recordings.
3. Complete the unified Heart result and UI integration, including annotations and offline mobile execution.
4. Confirm the physical hardware contract and integrate BLE audio without changing the Heart analysis contract.
5. Complete session persistence/report flow.
6. Implement tele-auscultation.
7. Expand to Lung.
8. Expand to Abdomen.

Parallel work is allowed, but product definition does not change because a sprint focuses on one branch.

# 23. AGENT FINAL-RESPONSE EXPECTATIONS

After meaningful work, summarize:

- what requirement/task was addressed;
- files changed;
- tests run and result;
- metrics if AI changed;
- interface/doc changes;
- known remaining gaps;
- whether validation/test boundaries were touched.

Do not claim success that is not supported by artifacts/tests.
