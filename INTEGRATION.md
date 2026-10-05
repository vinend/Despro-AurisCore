# INTEGRATION.md

## 1. Purpose

Define interfaces between:
- ESP32,
- mobile,
- AI,
- backend,
- tele-auscultation.

This document should change before or together with any breaking interface change.

### Research artifact interface

Heart training now also emits immutable `AI-Pipeline/results/EXP-HNNN-name/`
directories containing `config.json`, `metrics.json`, `predictions.csv`,
applicable history and curve CSVs, PNG figures, and a copy of the trained model.
`metrics.json` includes `experiment_id`, positive-class `f1`, and a
`comparison_key` describing the validation population and method. Existing
`AI-Pipeline/artifacts/` model and inference paths remain available. The
research report interface is separate from the AI-to-mobile result schema.

Managed CNN runs add `request.json` (stable requested configuration digest),
`status.json` (`queued`, `running`, `failed`, or `completed`, current and best
epoch, best validation loss, PID), `history.csv`, `checkpoints/backup/`, and
`best_model.keras`. The queue writes completion status after metrics, models,
and plots are saved. `scripts/training_status.py` reads those small files;
`scripts/summarize_experiments.py` reads only completed validation results.
The final holdout is outside the queue interface.

---

## 2. ESP32 -> Mobile

Transport:
- BLE.

Target data concept:
- PCM / integer audio samples,
- nominal sample rate 8000 Hz,
- mono stream.

Exact packet format is `TBD` until firmware implementation is locked.

Recommended packet metadata:

```text
sequence_number
timestamp
sample_count
payload
```

The mobile app should detect:
- duplicate packet,
- missing sequence,
- buffer underrun,
- malformed packet.

---

## 3. Mobile -> AI

Stable logical input:

```text
audio samples
sample rate
mode = heart
optional session metadata
```

AI should not depend directly on BLE code.

Preferred boundary:

```text
AudioBuffer -> AIInferenceService
```

---

## 4. AI -> Mobile

Recommended result schema:

```json
{
  "schema_version": "1",
  "model_version": "heart-cnn-0.1.0",
  "mode": "heart",
  "quality": {
    "valid": true,
    "score": 0.0,
    "reason": null
  },
  "prediction": {
    "label": "normal",
    "probability": 0.0,
    "threshold": 0.0
  }
}
```

If signal quality is invalid:

```json
{
  "quality": {
    "valid": false,
    "reason": "low_signal_quality"
  },
  "prediction": null
}
```

Do not force a prediction from unusable input.

---

## 5. Mobile -> Backend

Recommended resources:

```text
POST /api/v1/sessions
GET  /api/v1/sessions/{id}
POST /api/v1/sessions/{id}/analysis
POST /api/v1/sessions/{id}/recordings
```

Exact endpoints are not yet final.

Use versioning before backend becomes shared by multiple clients.

---

## 6. Tele-auscultation

Preferred media path:

```text
Mobile -> WebRTC -> Remote Client
```

Backend may provide:
- room creation,
- signaling,
- authentication,
- session metadata.

Backend should not relay or persist the live media stream unless the team explicitly decides to use a media server.

---

## 7. Error model

Use explicit errors instead of generic failures.

Examples:

```text
BLE_DISCONNECTED
BLE_PACKET_LOSS
AUDIO_BUFFER_UNDERRUN
INVALID_SAMPLE_RATE
LOW_SIGNAL_QUALITY
MODEL_LOAD_FAILED
INFERENCE_FAILED
BACKEND_UNAVAILABLE
WEBRTC_CONNECTION_FAILED
```

Mobile UI should map technical errors into useful user actions.
