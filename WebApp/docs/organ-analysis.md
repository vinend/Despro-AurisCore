# Heart and Abdomen app integration — phase 5

The existing Next.js app now uses actual recorded audio in its main recording
controls and WAV upload flow. Select **Heart** or **Abdomen** before starting.
Capture freezes that selection, collects validated mono PCM packets, encodes WAV
and calls the same service as uploaded files. No fake classification or processing
delay is used by the main recording flow. Simulator audio remains visibly labeled
as simulator audio even though it runs through real analysis code.

The existing device protocol remains unchanged: its four organMode values are
Heart auscultation positions. The new organ selector chooses the analysis backend;
it does not invent an Abdomen firmware command or change physical BLE behavior.
Users must supply audio from the selected organ. Physical BLE still needs its
confirmed packet/UUID/control contract. Heart-only device readouts and training
metrics are hidden when selecting Abdomen.

## Run locally

Install the WebApp dependencies and the mock-device dependencies if testing its
simulator. Generate Prisma's existing client; no database migration is needed.

```powershell
npm ci
npm run db:generate
cd mini-services/mock-device
npm ci
cd ../..
```

Configure `.env.local` from `.env.example` with absolute local Python/pipeline
paths. The Python environment needs the pipeline CNN requirements for model-backed
analysis. Both package settings are optional: without them, Heart DSP runs with
Murmur unavailable and Abdomen returns unavailable. A bad configured package
fails explicitly; no research model or demo result substitutes for it.

```powershell
npm run dev
# Optional simulator, in a second terminal:
cd mini-services/mock-device
npm run start
```

In this workspace, a local ignored `.env.local` points at the existing
`auriscore-audit` Python environment and pipeline checkout. No model package has
been promoted/configured. Dependencies and generated Prisma files remain ignored.

From the repository root in PowerShell, `WebApp/scripts/run-local.ps1` starts the
app using Node on PATH, `AURISCORE_NODE`, or the existing bundled Codex Node runtime.
This workspace's dependencies are already installed. For an engineering simulator,
run the same script with `-MockDevice` in a second terminal; it is optional.

## Transport and retained worker

- `POST /api/analysis`: multipart `audio` WAV and `mode: heart|abdomen`;
  returns `organ-analysis-v1`.
- `POST /api/abdomen/analyze`: fixed Abdomen mode, same envelope.
- `POST /api/heart/analyze`: fixed Heart mode, preserves the existing
  `heart-analysis-v1` response for legacy clients.

The shared server handler validates upload size/type/mode and dispatches to one
retained `scripts/analyze_recording.py --serve` worker per Node process. The worker
is shared through `globalThis` across route modules and development reloads.
Requests are serialized, carry generated correlation IDs, and have a 90-second
total deadline including queue wait. At most eight requests are retained. Response
lines are bounded to 4 MiB; WAV uploads to 16 MiB. The worker shuts down after five
idle minutes and is recreated on the next request, configuration change, crash or
timeout. Models load once per worker lifetime. Windows cleanup kills the spawned
Python process tree, including a virtual-environment launcher child.

HTTP statuses: 200 completed/partial, 422 invalid audio, 503 model unavailable.
Transport/configuration failures use a safe `{error}` response; tracebacks and
paths are not exposed. The client parses structured unavailable/quality envelopes
even on non-200 responses. Request cancellation stops active inference; queued
requests remain isolated and are never assigned another recording's response.

The older `analyze_heart_wav.py` CLI is preserved for one-shot tools; active app
routes use the retained shared worker. Server execution requires local Python and
external model packages even for a standalone Next build. This integration does
not establish browser-only or native-mobile offline inference. Core mobile
offline deployment remains a separate PRD gap; the Python library itself needs no
cloud service.

## Results and recording lifecycle

Heart renders its existing rhythm, cardiac events and Murmur branches. A Murmur
score marked uncalibrated is shown as a score, not a disease probability. Abdomen
shows window times, scores and labels, active-window count/fraction, analyzed
duration, discarded tail, threshold and model version. Activity windows overlap;
the fraction is not event rate or time active. Bowel event rate, variability and
pattern categories remain explicitly unavailable.

Invalid/unavailable states never generate labels or numerical summaries. Mode
changes clear old results; switching is disabled during capture/upload/inference.
Packet gaps, disconnects, changed device positions and malformed packets prevent
capture analysis. Repeated stop clicks cannot submit duplicate recordings. Reset
or unmount aborts processing and discards late results. Audio playback uses bounded
in-memory WAV blobs with object URLs revoked on replacement/unmount. History
retains at most 50 analysis records in memory, distinguishes simulator/device
sources and records unavailable/partial status; it does not persist audio/patients.

## Verification (2026-10-10)

29 WebApp tests passed with no skips. They cover typed schemas, endpoint dispatch,
missing-model/quality states, real PCM capture, cancellation, rendering and
persistent Python-worker lifecycle. Affected-file linting also passed.
Integration tests run real stored Heart/A005 Keras models with explicitly fictional
temporary selection/evaluation fixtures; those fixtures are never deployed and
do not establish model accuracy. Existing Heart tests continue to pass.

TypeScript checking and the production Next build pass. Browser verification
confirmed WAV upload → shared API → Python → 75 BPM synthetic Heart result;
Abdomen unavailable and silent-audio states; and the main mock-stream recording
flow with actual DSP and session history. No training, new threshold selection,
sealed evaluation, model promotion or external deployment was performed.

## Final verification handoff

Phase 6 adds repeatable production HTTP acceptance checks (`npm run verify:integration`)
and the [readiness report](phase6-readiness.md). The final WebApp suite has 30
passing tests with no skips, including cancellation/idle worker recovery.

## Lung extension

Select Lung for WAV upload or 30-second network capture. Existing PCM transport
and retained worker are reused. Without AURISCORE_LUNG_PACKAGE pointing to an
approved package, real Lung analysis returns unavailable. Eligible results show
sound events, respiratory phase timelines and nullable respiratory measurements.
Rates/I:E require three complete unambiguous cycles. Heart controls such as BPM
and auscultation site are hidden in Lung mode. No model is active yet.
