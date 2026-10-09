# AurisCore Software Project Framework

This folder defines the working framework for the AurisCore software team.

## Current software team
- Rowen — AI / signal processing / model optimization
- Musyaffa — mobile app / UI/UX / Clinical Decision Support interface
- Alvin — software integration / backend / AI support as needed

## Current project state

The current AI priority is the **Heart model**. H014 remains the historical
frozen external-validation Murmur benchmark. H021 is the strongest TRAIN-only
development result, with 117 false positives and 11 false negatives at 0.90
sensitivity among 568 participant OOF predictions; it is not a final deployment
model. H022 is protocol-locked and preflight-ready, but training has not
started and no H022 metrics exist. External validation and sealed test remain
closed.

The CPU Heart DSP prototype and `heart-analysis-v1` are engineering outputs
with synthetic tests; labeled-recording validation remains open. The Windows
WebApp demo supports WAV and mock/WebSocket PCM through the same Heart service,
while physical BLE details remain unconfirmed.

The intended software flow is:

`ESP32-S3 -> BLE -> Mobile App -> DSP / AI -> Clinical Decision Support -> Backend / Storage -> Tele-auscultation`

The proposal describes:
- Flutter / Dart for the mobile application.
- Offline smartphone-side AI inference.
- Python backend using Flask or a compatible lightweight API framework.
- MongoDB for persistent storage.
- Firebase for real-time telemetry where required.
- WebRTC peer-to-peer for tele-auscultation.
- Target AI evaluation focused on F1-score, not accuracy alone.

## Documentation map

| File | Purpose |
|---|---|
| `AGENTS.md` | Rules and operating context for coding agents / AI assistants |
| `IMPLEMENTATION.md` | Concrete implementation plan and milestones |
| `ARCHITECTURE.md` | System architecture and boundaries |
| `AI_PIPELINE.md` | Heart AI pipeline, training, evaluation, and deployment rules |
| `INTEGRATION.md` | Contracts between ESP32, mobile, AI, backend, and WebRTC |
| `TESTING.md` | Test strategy and acceptance criteria |
| `ROADMAP.md` | Work sequence and project checkpoints |
| `DECISIONS.md` | Architecture Decision Record log |

## Working rule

These docs are not static reports. Whenever the implementation changes, update the relevant document in the same pull request.
