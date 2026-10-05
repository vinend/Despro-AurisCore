# ROADMAP.md

## Current priority

**Heart AI improvement and integration readiness**

---

## Milestone 1 — Reproducible baseline

- [ ] Freeze current Heart dataset version
- [ ] Reproduce current CNN result
- [ ] Save full evaluation metrics
- [ ] Verify train/validation/test leakage risk
- [ ] Create experiment naming convention

Exit condition:
- one command or notebook reliably reproduces baseline evaluation.

---

## Milestone 2 — AI improvement

- [ ] preprocessing experiments
- [ ] log-mel tuning
- [ ] augmentation experiments
- [ ] class balancing
- [ ] CNN hyperparameter tuning
- [ ] threshold tuning on validation set
- [ ] compare experiments consistently

Exit condition:
- best candidate selected with documented reasoning.

---

## Milestone 3 — Deployment candidate

- [ ] export model
- [ ] test INT8 quantization
- [ ] create model metadata
- [ ] create inference wrapper
- [ ] benchmark smartphone-compatible inference

Exit condition:
- model accepts a known WAV / audio buffer and returns the agreed result schema.

---

## Milestone 4 — Mobile integration

- [ ] Flutter application skeleton
- [ ] file simulator
- [ ] live waveform
- [ ] recording flow
- [ ] Heart AI integration
- [ ] AI result screen
- [ ] local session storage

Exit condition:
- full Heart demo works without hardware.

---

## Milestone 5 — Hardware integration

- [ ] BLE service contract locked
- [ ] packet decoder
- [ ] buffer management
- [ ] reconnect behavior
- [ ] real ESP32 audio test

Exit condition:
- physical stethoscope stream can replace file simulator.

---

## Milestone 6 — Backend

- [ ] API skeleton
- [ ] session persistence
- [ ] result metadata
- [ ] recording metadata
- [ ] authentication integration

Exit condition:
- session can sync without breaking offline workflow.

---

## Milestone 7 — Tele-auscultation

- [ ] WebRTC signaling
- [ ] remote client
- [ ] audio stream
- [ ] latency measurement
- [ ] failure recovery

Exit condition:
- stable remote listening demo.

---

## Later

- [ ] Lung AI
- [ ] Abdomen AI
- [ ] unified multi-mode UX
- [ ] report generator
- [ ] broader validation
