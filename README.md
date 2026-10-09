# AurisCore Software Project Framework

AurisCore is an offline-capable digital stethoscope and auscultation-support platform for Heart, Lung, and Abdomen analysis.

## Documentation authority

Read project documentation in this order for non-trivial work:

1. `PRD.md` — product scope and required behavior.
2. `DECISIONS.md` — accepted architecture decisions.
3. `ARCHITECTURE.md` — technical structure and subsystem boundaries.
4. `INTEGRATION.md` — interface and schema contracts.
5. `AI_PIPELINE.md` / `TESTING.md` — AI and verification rules.
6. `IMPLEMENTATION.md` / `ROADMAP.md` — implementation sequence and milestones.
7. Current code — implementation state, which may temporarily be incomplete relative to the PRD.

`AGENTS.md` defines mandatory behavior for AI coding agents and contributors. Agents must read `PRD.md` before substantial product, AI, or integration work.

## Current software team

- Rowen — AI / signal processing / model optimization
- Musyaffa — mobile app / UI/UX / Clinical Decision Support interface
- Alvin — software integration / backend / AI support as needed

## Current product priority

The current priority is **Heart first**.

Important: Heart is **one analysis system with three branches**, not one CNN:

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

The Murmur CNN is only the **Murmur AI branch**. Heart is not product-complete until Rhythm DSP, Cardiac Event DSP, and Murmur AI are integrated into one versioned result.

## Current Murmur AI status

The active trained target is:

```text
Murmur Absent  = 0
Murmur Present = 1
Unknown        = excluded from supervised evaluation
```

Frozen historical external-validation benchmark: **H014**.

Strongest TRAIN-only development result: **H021** (568 participant OOF predictions): sensitivity 90.0%, specificity 74.45%, precision 45.83%, F1 60.74%, FP 117, FN 11. It misses the full engineering gate and has no final deployment model or predeclared fold ensemble. External validation and sealed test remain closed.

**H022** is protocol-locked and preflight-ready in the WSL research checkout; training has not started and no results exist. See [AI_PIPELINE.md](AI_PIPELINE.md) for the research history.

The CPU Heart DSP and `heart-analysis-v1` are engineering prototypes. The WebApp can analyze WAV files and captured mock/WebSocket PCM through the same Heart service with Murmur explicitly unavailable. Physical BLE still needs a confirmed firmware contract; see [IMPLEMENTATION.md](IMPLEMENTATION.md) and [ROADMAP.md](ROADMAP.md).

## Intended software flow

```text
ESP32-S3
  -> BLE audio / metadata
  -> Mobile App
  -> signal quality + DSP / AI
  -> Clinical Decision Support
  -> local/session storage
  -> optional backend sync
  -> optional WebRTC tele-auscultation
```

Core analysis is offline-first.

## Major product capabilities

The report-aligned product includes:

- Heart: BPM/rhythm, S1/S2, systole/diastole, S3/S4 candidates, Murmur Present/Absent + probability, waveform/spectral visualization.
- Lung: respiratory-phase analysis, I:E metrics, wheeze/crackle/rhonchi analysis.
- Abdomen: bowel-event analysis, bowel rate/variability, report-defined pattern categories including HS/Harmonic Sound indicators.
- patient/session history and report generation.
- tele-auscultation through WebRTC where available.

AurisCore is an **assistive screening / decision-support prototype**, not an autonomous definitive diagnostic system.

## Documentation map

| File | Purpose |
|---|---|
| `PRD.md` | Product source of truth: required behavior, outputs, safety boundary, product DoD |
| `AGENTS.md` | Mandatory operating rules for coding agents / contributors |
| `DECISIONS.md` | Architecture Decision Records |
| `ARCHITECTURE.md` | System/component architecture and boundaries |
| `INTEGRATION.md` | ESP32/mobile/DSP-AI/backend/telehealth interfaces and result schemas |
| `AI_PIPELINE.md` | Murmur AI research, training, evaluation, model-selection, deployment rules |
| `TESTING.md` | Unit/integration/AI/DSP/E2E verification and acceptance logic |
| `IMPLEMENTATION.md` | Concrete implementation phases and deliverables |
| `ROADMAP.md` | Current milestones, exit conditions, and future work |

## Working rule

Documentation is part of the implementation. When merged behavior changes, update the relevant document in the same change.

Do not silently change product scope to match whichever subsystem happens to be implemented first.
