# Abdomen inference — phase 4

The existing Python pipeline now has a real bowel-acoustic-activity CNN backend.
`AbdomenInferenceBackend` registers on the shared `AnalysisService` and runs
recorded WAV or PCM through frozen preprocessing, complete-window segmentation,
log-mel tensors, and safe-mode Keras inference. It does not use demo signals.
`BowelWindowScorer` exposes raw scores for engineering checks without assigning
thresholds or promoting research candidates.

## Meaning of the output

The existing A005 target is window activity: background/absent=0 and bowel acoustic
activity/present=1. SB, MB, CRS and HS annotations were combined into that binary
target during training. The CNN cannot distinguish those pattern categories or
locate/count events inside a window. Its five-second windows overlap by 50%.

The `abdomen-analysis-v1` result nests inside `organ-analysis-v1`. It contains:

- `quality`, `mode`, and `schema_version`;
- `activity` with target, model/preprocessing/threshold versions, window-level
  threshold, window duration/overlap, and uncalibrated score interpretation;
- `activity.windows`: `start_s`, `end_s`, raw `score`, and `present|absent` label;
- window count, active-window count/fraction, analyzed duration and discarded tail;
- explicit null fields for bowel events, rate, variability and pattern categories;
- limitations explaining the outstanding event-analysis work.

Threshold equality means present. No recording-level present/absent conclusion
is manufactured from the window scores. The active-window fraction is a descriptive
fraction of overlapping windows; it is not percentage of time active, event rate,
or probability of disease. Incomplete trailing windows are discarded, matching
training. Short recordings are rejected rather than padded into confident output.

Model/preprocessing failures produce structured component errors with no activity
classification. Shared input checks reject stereo, malformed WAV, nonfinite,
silent/DC-only, short, clipped and oversized audio before model loading. A retained
backend caches its model and initialization failures, and serializes concurrent
calls. A separate 512-window engineering resource limit prevents pathological
overlap configurations from producing unbounded work.

## Deployment package

`abdomen-activity-deployment-v1` contains `model.keras`, `source_metadata.json`,
`evaluation.json`, `decision.json` and a SHA-256/size manifest. Original source
metadata is preserved, including any historical copied Heart text. Corrected
target/class semantics are mandatory in the manifest, decision and evaluation;
source metadata alone cannot authorize a bowel model.

The decision must identify an explicitly selected final model, version identifiers
and an `engineering_gate` containing sensitivity and specificity minima. Additional
precision/F1/AUC/accuracy minima are optional. Abdomen has no numeric PRD gate, so
this implementation requires the team's supplied gate rather than adopting Heart
targets or selecting new thresholds. The evaluation must identify:

- `mode: abdomen`, `target: bowel_sound_activity`, `class_mapping: {absent: 0, present: 1}`;
- `inference_unit: window`, `aggregation: none`, `tail_policy: discard_incomplete`;
- matching `window_seconds`, `overlap` and model/preprocessing/threshold versions;
- participant-disjoint validation threshold selection and dataset/split provenance;
- both window classes, window-level TN/FP/FN/TP matrix and consistent finite metrics;
- SHA-256 bindings to the weights and canonical sorted preprocessing configuration.

An explicit engineering eligibility guard requires at least two validation
participants. This is a conservative software guard, not a claim of sufficient
clinical validation. Supplied evidence is checked for consistency, not independently
reconstructed. The current A005 one-subject evaluation and copied Heart metrics
do not satisfy this deployment contract. No approved package is fabricated, no
candidate is automatically selected, and no training/evaluation split is opened.

```powershell
& $analysisPython scripts\prepare_abdomen_deployment.py `
  --model final-bowel.keras --metadata final-bowel.json `
  --evaluation window-validation.json --decision deployment-decision.json `
  --destination artifacts\deployment-packages\abdomen-v1
```

Packaging refuses overwrites and verifies all supplied bytes and contracts before
publishing a directory. Model weights are rechecked before the first load.

## Run through the existing service

```python
from pathlib import Path
from auriscore.analysis_service import AnalysisService, BackendDefinition, HeartDSPBackend
from auriscore.abdomen_inference import abdomen_backend_definition

service = AnalysisService(backends=[
    BackendDefinition("heart", "heart-dsp-prototype-0.1.0", HeartDSPBackend),
    abdomen_backend_definition(Path("artifacts/deployment-packages/abdomen-v1")),
])
result = service.analyze_wav(Path("recording.wav").read_bytes(), "abdomen")
```

```powershell
& $analysisPython scripts\analyze_recording.py --wav recording.wav --mode abdomen `
  --abdomen-package artifacts\deployment-packages\abdomen-v1
& $analysisPython scripts\analyze_recording.py --serve `
  --abdomen-package artifacts\deployment-packages\abdomen-v1
```

`--stdin --mode abdomen` accepts bounded WAV bytes for an application bridge.
CLI package paths can alternatively come from `AURISCORE_ABDOMEN_PACKAGE` and
`AURISCORE_HEART_PACKAGE`. Both can be registered in one retained worker. Configuring
only Abdomen retains the existing Heart DSP default. Without an eligible Abdomen
package, valid Abdomen audio returns unavailable. No separate HTTP server exists.

Phase 5 preserves the existing WebApp Heart endpoint and adds Abdomen/shared HTTP
upload, client service, result display and retained worker lifecycle. See
`../../WebApp/docs/organ-analysis.md`. PRD bowel-event DSP, rate/variability and pattern categories remain explicit
implementation gaps, separate from this binary CNN adapter.

## Verification

Tests cover frozen A005 per-frequency tensor parity/resampling, complete-window
times and tails, batch boundaries, float/int16/WAV parity, equality thresholds,
concurrent one-time loading, invalid audio and predictions, cached failures,
metadata statistics, evidence/target/version/geometry rejection, gates, hashes,
candidate refusal and independent Heart/Abdomen routing. Actual A005 inference
is smoke-tested on synthetic audio, including repeated requests in one worker.
Temporary approval and metric fixtures are fictional and are not model evaluation
evidence. No model accuracy or clinical claim is derived from these tests.

On 2026-10-10, 180 compatibility checks passed, followed by 3 WAV/worker checks
after the stdin adapter addition (182 unique passing cases across both runs).
