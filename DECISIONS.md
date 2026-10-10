# DECISIONS.md

# Architecture Decision Records

Use this file to record accepted decisions that affect more than one module or materially affect product implementation.

Product scope is defined by `PRD.md`. An ADR may select an implementation strategy, but must not silently remove a PRD requirement.

---

## ADR-001 — Heavy analysis runs outside ESP32

**Status:** Accepted for current prototype

**Decision:** Major DSP/AI analysis runs in the smartphone/fog layer rather than making the ESP32 responsible for the full analysis stack.

**Reason:**

- reduces ESP32 memory/compute pressure;
- simplifies model iteration;
- supports richer preprocessing and visualization;
- aligns with the selected report architecture.

**Consequences:**

- mobile becomes a critical compute layer;
- result/preprocessing versions must be controlled;
- core analysis remains offline-capable.

---

## ADR-002 — Heart-first development

**Status:** Accepted

**Decision:** Complete and integrate the Heart analysis path before deep implementation of Lung and Abdomen, unless the team explicitly parallelizes work.

**Reason:**

- Heart already has an active Murmur CNN research pipeline;
- Heart is the best-defined current path for proving end-to-end acquisition -> analysis -> UI;
- spreading research effort across all organs too early increases validation and integration risk.

**Important clarification:** Heart-first does not mean Murmur-CNN-only. Heart requires three branches: Rhythm DSP, Cardiac Event DSP, and Murmur AI.

---

## ADR-003 — AI evaluation is not accuracy-only

**Status:** Accepted

**Decision:** Murmur-model comparison requires sensitivity/recall, specificity, precision, F1, confusion matrix, ROC-AUC, and PR-AUC where applicable, plus threshold and split provenance.

**Reason:**

- murmur data are imbalanced;
- accuracy can hide poor abnormal-class behavior;
- false positives and false negatives have different consequences.

---

## ADR-004 — File simulator before full hardware dependency

**Status:** Accepted

**Decision:** Mobile and analysis integration must support prerecorded audio through a file-simulator/input-adapter path.

**Reason:**

- enables software development in parallel with hardware;
- supports deterministic tests;
- reduces integration blocking.

---

## ADR-005 — Heart uses a three-branch hybrid analysis architecture

**Status:** Accepted

**Decision:** Heart analysis is composed of:

1. Rhythm DSP — BPM / beat intervals / rhythm category;
2. Cardiac Event DSP — S1/S2, systole/diastole, S3/S4 candidates;
3. Murmur AI — Murmur probability + Present/Absent screening result.

The outputs are aggregated into one versioned Heart result.

**Reason:**

- aligns with the report-defined Heart behavior;
- not every Heart output requires or benefits from CNN training;
- keeps deterministic signal-analysis outputs separate from learned murmur classification;
- allows independent validation/versioning of each branch.

**Consequences:**

- `ARCHITECTURE.md`, `INTEGRATION.md`, `TESTING.md`, `IMPLEMENTATION.md`, and mobile models must represent all three branches;
- Murmur CNN completion alone is not Heart product completion.

---

## ADR-006 — Murmur AI is not a disease classifier

**Status:** Accepted

**Decision:** The current Heart AI target remains binary murmur status: Absent vs Present. It must not output specific disease diagnoses without a future explicit product decision, suitable labels, training design, and validation.

**Reason:**

- current training data/target support murmur status rather than disease subtype diagnosis;
- prevents unsupported clinical claims;
- keeps implementation consistent with assistive screening scope.

---

## ADR-007 — Versioned unified Heart result contract

**Status:** Accepted

**Decision:** Mobile/integration code will consume a versioned Heart result capable of carrying signal quality, Rhythm DSP, Cardiac Event DSP, Murmur AI, and visualization annotations.

**Reason:**

- the old single `prediction.label/probability` result is insufficient for the report-aligned Heart product;
- a typed unified result prevents UI logic from depending on internal DSP/AI implementations.

**Consequences:**

- breaking schema changes require a version increment and integration tests;
- legacy minimal murmur-only outputs may be adapted during transition but should not become the long-term Heart contract.

---

## ADR-008 — External validation and sealed holdout are controlled resources

**Status:** Accepted

**Decision:** AI research should use train-only CV/OOF where the protocol specifies it, open external validation only after a predefined eligibility gate, and reserve sealed holdout for final locked evaluation.

**Reason:**

- reduces iterative overfitting to validation;
- preserves credible final evaluation;
- supports reproducible model-selection claims.

---

## ADR-009 — Retained local Python worker for WebApp organ analysis

**Status:** Accepted for the current engineering prototype (2026-10-10)

The existing Next.js backend shares one retained recorded-audio JSONL worker per
Node process for Heart and Abdomen. The main recording flow captures actual PCM
instead of inventing classifications. Research candidates cannot be activated
without their respective final-package contracts. The legacy Heart endpoint
preserves its schema; new clients use the shared organ envelope. This is local
WebApp integration, not completion of native-mobile offline analysis or BLE.

### ADR template

```text
## ADR-XXX — Title

Status:
Date:

Decision:

Context:

Options considered:

Reason:

Consequences:
```
