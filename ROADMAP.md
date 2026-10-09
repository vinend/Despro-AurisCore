# ROADMAP.md

## Current priority

**Heart first: preserve Murmur research discipline, validate the implemented DSP prototype, complete the unified demo, and confirm physical hardware integration.**

Heart = Rhythm DSP + Cardiac Event DSP + Murmur AI.

---

## Milestone 1 — Murmur research foundation

Status: substantially established.

- [x] participant-aware dataset/split discipline
- [x] reproducible CNN experiment framework
- [x] full evaluation metrics beyond accuracy
- [x] immutable named experiments
- [x] H014 frozen validation benchmark
- [x] H015 site-aware MIL study
- [x] H016 fold-local pretrained site-aware MIL study
- [x] H017–H020 participant-training, pooling, and classifier studies
- [x] H021 train-only acoustic hard-negative mining result frozen
- [x] H022 protocol and leakage-safe preflight prepared
- [ ] H022 training and OOF evaluation (not started)

Exit condition:

- current research state can be reproduced and explained without reopening the sealed holdout.

---

## Milestone 2 — Murmur deployment candidate

- [x] audit H016–H020 operating points and failure mechanisms
- [x] preserve sensitivity-first threshold discipline in completed experiments
- [x] reduce train-only OOF FP from H020 179 to H021 117 at 0.90 sensitivity
- [x] use participant-safe train-only OOF for research selection
- [ ] separately authorize and run H022; no results exist yet
- [ ] open external validation only after the predefined gate
- [x] freeze H021 research protocol, OOF threshold, and artifact provenance
- [ ] define and evaluate a final deployment model or predeclared inference rule
- [ ] create mobile-compatible export candidate

Exit condition:

- one Murmur candidate is frozen for integration with documented limitations and reproducible metadata.

---

## Milestone 3 — Cardiac Event DSP

Progress: a CPU-only S1/S2 and interval candidate prototype now exists in
`AI-Pipeline/src/auriscore/heart_dsp.py`. The milestone remains open until
representative labeled-recording validation and integration are complete.

- [x] prototype S1 candidate detection
- [x] prototype S2 candidate detection
- [x] systolic/diastolic interval derivation
- [x] experimental S3 candidate logic
- [x] experimental S4 candidate logic
- [x] event timestamp serialization
- [x] synthetic engineering tests
- [ ] representative labeled-recording validation and robustness evaluation
- [ ] complete event visualization annotations

Exit condition:

- Heart recordings can produce inspectable event annotations through a stable API.

---

## Milestone 4 — Rhythm DSP

Progress: the same prototype provides median S1-interval BPM, configurable
rate categories, and an insufficient-data-aware irregularity flag. Clinical
performance and real-recording robustness remain unverified.

- [x] beat interval computation
- [x] BPM estimation
- [x] Normal/Tachycardia/Bradycardia prototype rule
- [x] irregularity prototype logic
- [x] invalid/insufficient-data behavior
- [x] synthetic engineering tests
- [ ] real/labeled recording validation

Exit condition:

- Heart recordings can produce reproducible BPM/rhythm output through a stable API.

---

## Milestone 5 — Unified Heart result

Progress: `AI-Pipeline/src/auriscore/heart_result.py` assembles a prototype
`heart-analysis-v1` result with an optional Murmur adapter. The WebApp service
integration exists; offline mobile integration remains open. Murmur AI completion alone does not complete Heart.
H021 development evidence is frozen, but its outer-fold pipelines are not a
defined deployment model. The optional Murmur service reports unavailable
until a separate deployment decision and evaluation are completed.

- [x] implement `heart-analysis-v1`
- [x] serialize Rhythm and Cardiac Event DSP results
- [x] represent Murmur explicitly as unavailable when no model is supplied
- [x] include branch/model/algorithm versions where available
- [x] explicit low-quality fail-safe result
- [x] integration tests for the prototype contract
- [ ] connect a separately evaluated deployment-ready Murmur model
- [ ] validate the complete three-branch product path

Exit condition:

- one analysis call returns a versioned result representing all three branches.

---

## Milestone 6 — Heart mobile demo

Progress: the WebApp has a CPU-backed Heart WAV file demo and a ten-second
WebSocket/mock PCM capture path to the same versioned result view. This is a
server-backed development slice; mobile/offline, physical BLE, waveform
markers, Murmur deployment inference, and persistence remain open.

- [ ] Flutter analysis screen
- [x] WebApp WAV file simulator
- [x] WebApp mock/WebSocket PCM capture to the same Heart service
- [ ] live/static waveform
- [ ] recording/playback
- [x] WebApp BPM/rhythm display
- [x] WebApp numeric candidate/event and interval display
- [ ] S1/S2 markers
- [ ] systole/diastole regions
- [ ] S3/S4 candidate markers
- [ ] Murmur probability/result
- [ ] local session save

Exit condition:

- complete Heart demo works without physical hardware.

---

## Milestone 7 — Hardware integration

- [ ] BLE service contract locked (UUIDs and packet layout need firmware confirmation)
- [ ] packet decoder
- [ ] buffer management
- [ ] packet-loss/duplicate detection
- [ ] reconnect behavior
- [ ] real 8 kHz device audio test

Exit condition:

- physical stethoscope stream can replace the file simulator without changing Heart analysis behavior.

---

## Milestone 8 — Session/report/backend

- [ ] patient/session metadata
- [ ] recording metadata/reference
- [ ] analysis-result persistence
- [ ] report generation
- [ ] authentication integration as implemented
- [ ] offline-safe sync behavior

Exit condition:

- session/report workflow works without turning backend availability into a local-analysis dependency.

---

## Milestone 9 — Tele-auscultation

- [ ] WebRTC signaling
- [ ] remote client/browser path
- [ ] live audio stream
- [ ] latency/jitter/packet-loss measurement
- [ ] failure recovery

Exit condition:

- stable remote listening demo with measured performance.

---

## Milestone 10 — Lung

- [ ] respiratory phase analysis
- [ ] respiratory rate / durations where supported
- [ ] I:E ratio
- [ ] wheeze analysis
- [ ] crackle analysis
- [ ] rhonchi analysis
- [ ] visualization/result schema

---

## Milestone 11 — Abdomen

- [ ] bowel event detector
- [ ] bowel rate
- [ ] bowel-rate variability / inter-event metrics
- [ ] report-defined pattern categories
- [ ] Harmonic Sound indicator handling
- [ ] visualization/result schema

---

## Product completion guardrail

Never mark **Heart complete** when only Murmur AI is complete.

Consult the Heart Definition of Done in `PRD.md`.
