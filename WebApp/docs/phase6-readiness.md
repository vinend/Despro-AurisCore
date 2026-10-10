# Phase 6 — integrated verification and handoff

Date: 2026-10-10. Scope: the existing Next.js backend and Python Heart/Abdomen
pipeline, connected to recorded PCM and WAV uploads. This concludes the six-phase
software integration work. It does not mark the complete PRD or either organ's
clinical validation/deployment complete.

## Current runnable state

| Capability | Current state |
| --- | --- |
| Heart recording/upload → quality → rhythm/event DSP → UI | Runnable with the configured local Python runtime |
| Murmur model adapter and unified three-branch Heart schema | Implemented; activation requires an approved final package |
| Abdomen window-activity model adapter and UI | Implemented; activation requires an approved final package |
| Default missing-model behavior | Heart keeps DSP and reports Murmur unavailable; Abdomen returns unavailable |
| Low-quality/corrupt/oversized input | Rejected with explicit reasons; no fabricated findings |
| Worker lifecycle | Bounded serialized queue, deadlines, correlation, cached initialization, cancellation and idle restart |
| Playback and history | Recorded WAV playback and bounded in-memory history; no durable patient/session persistence |
| Physical ESP32 BLE and smartphone offline analysis | Not validated/complete in this server-backed implementation |
| Abdomen event count/rate/variability/pattern categories | Not inferred by the binary window classifier; remain unavailable |

## Verification evidence

The user story is: select Heart/Abdomen → record validated PCM or upload mono WAV
→ shared same-origin API → retained Python analysis → typed organ result →
screening-safe display, playback and status history.

| Boundary/check | Evidence |
| --- | --- |
| Python DSP, inference, package guards and shared transport | 182 tests passed; 14 dependency deprecation warnings |
| WebApp contracts, recording, client, rendering and worker | 30 tests passed, no skips; includes recovery after active cancellation and idle shutdown |
| Production HTTP → real Python → validated response | Nine acceptance scenarios passed; report at `WebApp/artifacts/phase6-http.json` |
| Concurrent recordings | Independent 75 BPM / 90 BPM synthetic signals and Abdomen request retained distinct correlation IDs and expected results |
| Legacy endpoint | `/api/heart/analyze` preserves valid and branchless invalid-quality `heart-analysis-v1` |
| Failures/recovery | Both-organ silence, invalid modes, missing audio, corrupt WAV and 17 MiB upload rejected; next valid request works |
| TypeScript / production build | Independent `tsc --noEmit` and `npm run build` passed; existing Next config skips build-time type checking |
| Lint | Phase 5 affected-file lint passed; phase 6 verification script lint passed |
| Browser → API → Python → UI | Phase 5 browser checks confirmed upload, invalid audio, both main capture flows, playback and history; reused evidence because phase 6 changes verification/docs only |

The HTTP runner launches its own loopback production server on a free port, uses
synthetic 8000 Hz mono WAV only, deliberately clears model-package settings in
that child process and shuts down its server/Python process tree. It does not
modify `.env.local` or contact a cloud analysis service. Generated evidence is
ignored by Git. It checks the built application, so rebuild after code changes.
The runner exits nonzero on failure, including missing runtime/build configuration.

Configured-model tests load actual saved Heart and A005 Keras weights using
explicitly fictional evaluation/selection fixtures in temporary directories.
They verify software execution, not model eligibility, accuracy or clinical
performance. No training, real threshold selection, holdout/external evaluation,
model promotion, database migration, commit, push or external deployment was done.

## Repeat the checks

Set `AURISCORE_PYTHON` in the current PowerShell session to your installed Python
executable; the environment needs the pipeline CNN requirements and pytest.
Set `AURISCORE_PIPELINE_DIR` to the absolute `AI-Pipeline` directory. Existing
WebApp `.env.local` is also read by the HTTP runner, but Node unit tests require
the Python setting in the shell to avoid skipping the older stream test.

From `AI-Pipeline`:

```powershell
& $env:AURISCORE_PYTHON -m pytest -q tests/test_abdomen_inference.py tests/test_abdomen.py tests/test_heart_inference.py tests/test_analysis_service.py tests/test_model_audit.py tests/test_heart_dsp.py tests/test_heart_bridge.py tests/test_h021_freeze_adapter.py
```

From `WebApp`, after installing dependencies and generating Prisma as described
in [organ-analysis.md](organ-analysis.md):

```powershell
npm run test:analysis
npm run typecheck
npm run build
npm run verify:integration
```

The PowerShell launcher `WebApp/scripts/run-local.ps1` remains available from the
repository root when npm/Node are absent from PATH and the bundled runtime exists.

## Model activation handoff

1. Select and evaluate a final Heart model with genuine participant-disjoint,
   recording-level evidence for the exact `mean_window_score` inference rule and
   threshold. The package must satisfy the documented Heart engineering gate.
   H021's development folds/OOF threshold cannot be reused as a deployment rule.
2. Select and evaluate a final Abdomen activity model with corrected bowel
   target/class semantics, genuine window-level validation, exact preprocessing
   and an explicit team engineering gate. A005's existing one-subject evidence
   and copied Heart metadata do not qualify.
3. Supply genuine model metadata, evaluation and selection decisions to
   `prepare_heart_deployment.py` / `prepare_abdomen_deployment.py`. These create
   immutable hash-bound packages and refuse overwrites; see
   [Heart package contract](../../AI-Pipeline/docs/heart_inference.md) and
   [Abdomen package contract](../../AI-Pipeline/docs/abdomen_inference.md).
4. Set the absolute `AURISCORE_HEART_PACKAGE` and `AURISCORE_ABDOMEN_PACKAGE` paths
   in local server configuration and restart the app. Verify representative
   recordings through upload and capture, including invalid input and
   organ-specific labels/versions. The default HTTP runner deliberately clears
   package settings; it does not certify the activated models.

Representative labeled Heart DSP validation, waveform event annotations, physical
BLE, durable session/report storage and native-mobile offline inference remain
separate product work. Software acceptance checks cannot replace those validations.
