# DECISIONS.md

# Architecture Decision Records

Use this file to record decisions that affect more than one module.

---

## ADR-001 — AI inference location

**Status:** Accepted for current prototype

**Decision:** Heavy AI inference runs on the smartphone rather than ESP32.

**Reason:**
- reduces ESP32 memory pressure,
- easier model iteration,
- supports more complex preprocessing,
- consistent with the selected proposal architecture.

**Consequences:**
- mobile app becomes a critical computation layer,
- inference API between app and model must be stable.

---

## ADR-002 — Heart-first AI development

**Status:** Accepted

**Decision:** Stabilize Heart classification before Lung and Abdomen.

**Reason:**
- the team already has an active Heart CNN baseline,
- spreading work across three models now would slow validation.

---

## ADR-003 — AI evaluation is not accuracy-only

**Status:** Accepted

**Decision:** Model comparison requires precision, recall, F1, confusion matrix, and AUC metrics where applicable.

**Reason:**
- medical audio datasets may be imbalanced,
- accuracy can hide poor abnormal-class detection.

---

## ADR-004 — File simulator before full hardware dependency

**Status:** Proposed

**Decision:** Mobile and AI integration should support prerecorded audio as an input adapter.

**Reason:**
- allows software development in parallel with hardware,
- simplifies deterministic testing.

---

## ADR template

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
