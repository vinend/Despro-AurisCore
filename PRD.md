# AurisCore Product Requirements Document (PRD)

**Status:** Active product source of truth  
**Version:** 1.0  
**Last updated:** 2026-10-09  
**Current priority:** Heart analysis pipeline

## 0. Purpose and authority

This PRD defines **what AurisCore must ultimately do**. A working experiment or partial implementation does not redefine the product.

Use documentation in this order for product work:

1. `PRD.md` — product scope, required behavior, outputs, safety boundaries.
2. `DECISIONS.md` — accepted architecture decisions. An ADR must not silently remove a PRD requirement.
3. `ARCHITECTURE.md` — technical structure and boundaries.
4. `INTEGRATION.md` — interfaces and schemas.
5. `AI_PIPELINE.md` / `TESTING.md` — AI and verification rules.
6. `IMPLEMENTATION.md` / `ROADMAP.md` — sequencing and milestones.
7. Current code — implementation reality, which may temporarily be incomplete.

If code implements only part of this PRD, treat the difference as an **implementation gap**.

## 1. Product vision

AurisCore is an offline-capable digital stethoscope and auscultation-support platform for:

1. Heart / Cardio
2. Lung / Pulmonary
3. Abdomen

The system captures, cleans, records, analyzes, visualizes, stores, and optionally streams body sounds. It is an **assistive screening and clinical decision-support prototype**, not an autonomous diagnostic system.

## 2. Product goals

AurisCore should:

- acquire auscultation audio from the physical device;
- reduce environmental/acquisition noise;
- provide live waveform visualization and recording;
- run organ-specific DSP/AI locally without requiring cloud inference;
- present quantitative findings and interpretable visual annotations;
- preserve examination/session history;
- support report generation;
- support tele-auscultation when connectivity is available;
- support prerecorded-file simulation before hardware integration is complete.

## 3. Safety boundary

Do not present unsupported outputs as confirmed disease diagnosis or treatment advice.

Preferred language includes `Murmur suspected`, `No murmur detected`, `Possible abnormal acoustic pattern`, `Candidate S3 event`, and `Assistive screening result`.

A specific disease label may only be added if a future PRD revision explicitly requires it and the project has suitable labeled data, model design, and validation.

## 4. System-level flow

```text
Physical Stethoscope / ESP32-S3
            |
            | BLE audio + metadata
            v
      Mobile Application
            |
            +--> signal-quality validation
            +--> preprocessing / DSP
            +--> organ-specific analysis
            +--> Clinical Decision Support UI
            +--> local/session storage
            +--> optional backend sync
            +--> optional WebRTC tele-auscultation
```

Core examination analysis is **offline-first**.

## 5. Report-aligned technical constraints

Project constraints/targets include:

- nominal acquisition rate: **8000 Hz**;
- ADC resolution target: **12-bit**;
- signal coverage target: approximately **20–2000 Hz**;
- major DSP/AI workload in the mobile/fog layer for the selected architecture;
- offline smartphone inference;
- mobile-compatible model export, with INT8 as a proposal target;
- post-filter/ANC SNR target: **>=20 dB**;
- tele-auscultation target: **<100 ms end-to-end**;
- local analysis must remain usable without backend connectivity.

These are project targets, not proof of clinical/regulatory compliance.

# 6. HEART PRODUCT REQUIREMENTS

## 6.1 Critical invariant: Heart has three branches

**Heart must never be reduced to only the Murmur CNN.**

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
          intervals        systole /       + screening
              |            diastole           label
              v               |
      rhythm classification S3 / S4
              |               |
              +---------------+---------------+
                              |
                              v
                     HEART ANALYSIS RESULT
                              |
                waveform / PCG / spectrogram
                 markers + numeric findings
```

This three-branch structure is a **product requirement**.

### 6.2 Branch A — Rhythm DSP

Required outputs:

- heart rate (BPM);
- beat/interval timing information;
- prototype rhythm category: Normal, Tachycardia, Bradycardia, or irregular-rhythm/Arrhythmia indicator.

Report-aligned prototype logic:

- BPM derived from successive S1 intervals;
- Normal: `60 <= BPM <= 100`;
- Tachycardia: `BPM > 100`;
- Bradycardia: `BPM < 60`;
- Arrhythmia: interval-variability heuristic across consecutive cycles.

These are configurable **prototype heuristics from the report**, not universal diagnosis rules.

### 6.3 Branch B — Cardiac Event DSP

Required outputs:

- S1 event locations;
- S2 event locations;
- systolic intervals;
- diastolic intervals;
- S3 candidate locations;
- S4 candidate locations;
- event timestamps for visualization.

Report-aligned approach includes low-frequency Heart processing, Hilbert-envelope-style event extraction, systole/diastole derived from S1/S2 timing, and S3/S4 detection using time windows/signal decomposition.

Prototype timing rules documented in the report include:

- S3 candidate: approximately `0.1–0.2 s` after S2;
- S4 candidate: approximately `0.03–0.06 s` before the next S1.

Keep these configurable and validate them before making strong clinical claims.

### 6.4 Branch C — Murmur AI

Current trained AI task:

```text
Murmur Absent  = 0
Murmur Present = 1
Unknown        = excluded from supervised evaluation
```

Required output:

```json
{
  "probability": 0.0,
  "threshold": 0.0,
  "label": "present|absent"
}
```

The Murmur model is a screening classifier, not a disease classifier.

Required evaluation includes precision, sensitivity/recall, specificity, F1, ROC-AUC, PR-AUC, confusion matrix, threshold, and data/split provenance. Accuracy alone is insufficient.

Current engineering direction is to reduce false positives / improve precision and specificity while preserving high sensitivity.

Internal engineering targets currently used by the team:

```text
Sensitivity >= 0.90
Specificity >= 0.85
Precision   >= 0.65
F1          >= 0.75
ROC-AUC     >= 0.92
PR-AUC      >= 0.85
```

These are engineering goals, not regulatory or clinical standards.

### 6.5 Unified Heart result

The versioned Heart result must be capable of representing all three branches:

```json
{
  "schema_version": "heart-analysis-v1",
  "mode": "heart",
  "quality": {"valid": true, "score": null, "reason": null},
  "rhythm": {
    "heart_rate_bpm": 78,
    "label": "normal",
    "beat_intervals_ms": []
  },
  "cardiac_events": {
    "s1_times_s": [],
    "s2_times_s": [],
    "s3_candidates_s": [],
    "s4_candidates_s": [],
    "systolic_intervals": [],
    "diastolic_intervals": []
  },
  "murmur": {
    "model_version": "",
    "probability": 0.82,
    "threshold": 0.0,
    "label": "present"
  },
  "visualization": {
    "waveform_available": true,
    "spectrogram_available": true,
    "event_annotations_available": true
  }
}
```

Exact field names may evolve via a versioned integration decision, but rhythm, cardiac events, and murmur must remain representable.

### 6.6 Heart visualization

The Heart Analysis UI should support:

- waveform / PCG;
- optional spectrogram or mel-spectrogram;
- S1/S2 markers;
- systolic/diastolic regions;
- S3/S4 candidate markers;
- BPM;
- rhythm result;
- murmur probability;
- Murmur Present/Absent screening result;
- suspicious-region highlighting only when supported by the implemented analysis.

Do not call highlighted regions confirmed pathology unless localization has been explicitly validated.

# 7. LUNG PRODUCT REQUIREMENTS

Lung is a later milestone but remains in product scope.

Report-aligned outputs include:

- lung-sound band processing;
- inhale/exhale phase analysis;
- respiratory rate where supported;
- inhalation and exhalation duration;
- I:E ratio;
- wheeze detection/classification;
- crackle detection/classification;
- rhonchi detection/classification;
- waveform/spectral visualization and abnormality annotation.

Report-derived acoustic heuristics must be explicit, versioned, and validated rather than hidden in UI logic.

# 8. ABDOMEN PRODUCT REQUIREMENTS

Abdomen is a later milestone.

Report-aligned outputs include:

- bowel-sound band processing;
- frame-wise RMS/energy extraction;
- adaptive normalization/thresholding;
- bowel event detection;
- Bowel Rate (events/minute);
- Bowel Rate Variability / inter-event-interval variability;
- pattern categories: Single Burst, Multiple Burst, CRS, HS/Harmonic Sound;
- visualization and event annotation.

If harmonic-sound patterns are used as an indicator associated with stenosis, present them as a **screening indicator/suspicious pattern**, not a confirmed disease diagnosis.

# 9. MOBILE PRODUCT REQUIREMENTS

Major capabilities/screens:

1. Authentication / security
2. Clinical dashboard
3. Patient details / examination history
4. Live auscultation
5. Analysis / AI result
6. Report / share
7. Telehealth / tele-auscultation

Live auscultation must support device/BLE state, organ mode selection, waveform, recording, session duration, and implemented quantitative metrics.

Analysis must support recorded waveform/PCG playback, organ-specific numeric outputs, probability/confidence where applicable, annotated findings, screening-safe text, and report/share flow.

# 10. DATA, BACKEND, AND TELE-AUSCULTATION

Core analysis must work offline.

Session data should support longitudinal review. Backend responsibilities may include authentication, patient/session metadata, recording references, analysis metadata, report metadata, and telehealth signaling. Backend connectivity must not become a hidden requirement for local analysis.

Preferred tele-auscultation path:

```text
Mobile -> WebRTC P2P -> Remote clinician/browser client
```

Report actual measured latency rather than automatically claiming the <100 ms target.

# 11. AI / DATASET GOVERNANCE

- Preserve patient/participant/source grouping and prevent leakage.
- Use training/inner validation for fitting and early stopping.
- Use train-only CV/OOF for research selection when defined by protocol.
- Open external validation only at a predeclared gate.
- Keep sealed test/holdout for final locked evaluation only.
- Never optimize against the sealed test set.
- Store every completed experiment in a unique immutable experiment directory.
- Track dataset/provenance, splits, seed, preprocessing, normalization, augmentation, model/loss/optimizer, threshold rule, metrics, predictions, and model artifact/version.

# 12. CURRENT IMPLEMENTATION SNAPSHOT — 2026-10-09

This section is progress context, not the final product definition.

### Heart Murmur AI

- H014 remains the frozen historical external-validation benchmark for the Murmur branch only.
- H021 is the strongest TRAIN-only development result: 568 participant OOF predictions, sensitivity 0.90, specificity 0.7445, precision 0.4583, F1 0.6074, and 117 false positives. It misses the full engineering gate; no final all-TRAIN deployment model or predeclared fold ensemble exists.
- H022 is protocol-locked and preflight-ready, but training has not started and no H022 metrics exist. External validation and sealed test remain closed.

### Heart DSP and unified result

- A CPU-only engineering prototype implements quality validation, Heart preprocessing, S1/S2 candidates, BPM/rhythm screening rules, systolic/diastolic intervals, and experimental S3/S4 candidates. Synthetic tests do not establish labeled-recording or clinical validity.
- `heart-analysis-v1` combines the DSP branches and an explicitly unavailable optional Murmur branch. The WebApp supports WAV upload and captured WebSocket/mock PCM through the same Heart analysis service and result view.
- Representative labeled-recording validation, robust event visualization, offline mobile execution, and deployable Murmur inference remain open.

### Physical hardware

- The 8000 Hz mono signed-int16 WebSocket packet stream is a development mock. Physical ESP32-S3 BLE UUIDs, packet layout, and control commands are unconfirmed; physical BLE integration is not complete.

### Lung / Abdomen

Planned after Heart is sufficiently integrated unless the team explicitly parallelizes work.

# 13. DEFAULT DELIVERY ORDER

```text
1. Continue controlled Murmur research and define a deployment candidate separately
2. Validate/stabilize the implemented Cardiac Event and Rhythm DSP prototypes
3. Complete the three-branch Heart integration and annotations
4. Integrate the versioned Heart result with offline mobile UI
5. Confirm the physical firmware contract and integrate real BLE audio
6. Complete storage/report flow
7. Tele-auscultation
8. Lung analysis
9. Abdomen analysis
```

No agent should mark **Heart complete** merely because the Murmur CNN is complete.

# 14. HEART DEFINITION OF DONE

Heart is not product-complete until:

- [ ] usable Heart audio can be ingested from file simulator and/or BLE;
- [ ] signal-quality validation exists;
- [ ] S1/S2 events can be produced and visualized;
- [ ] systole/diastole regions can be derived;
- [ ] BPM can be computed;
- [ ] rhythm output can be produced;
- [ ] S3/S4 candidate output can be produced;
- [ ] murmur probability and Present/Absent output can be produced;
- [ ] all three Heart branches are combined into one versioned result schema;
- [ ] waveform/spectrogram and supported annotations can be displayed;
- [ ] invalid/low-quality audio does not receive a confident clinical-looking result;
- [ ] tests cover changed behavior;
- [ ] AI evaluation artifacts are reproducible;
- [ ] safety wording remains assistive/screening-oriented.

# 15. CHANGE CONTROL

A change to supported organs, required Heart branches, required outputs, claim level, offline requirement, major user flow, patient/session/report capability, or tele-auscultation requirement requires PRD review/update.

A coding agent may propose such a change but must not silently implement it as already approved.
