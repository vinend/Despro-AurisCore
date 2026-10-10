# Lung temporal localization

The Lung training pipeline already uses per-frame multi-label interval targets
and a temporal CNN. Its outputs have shape `(frames, classes)`, unlike the Heart
and Abdomen binary classifiers. Existing checkpoints such as Linux EXP-L003 can
therefore produce frame scores without retraining. This implementation exposes
research WAV localization and recording-level development boundary evaluation.
It does not establish that EXP-L003 localizes reliably.

## Research localization of a WAV

Run on the Linux machine containing the completed experiment, from AI-Pipeline
with the existing TensorFlow environment active:

```bash
python scripts/localize_lung_recording.py \
  --experiment results/EXP-L003-temporal-cnn \
  --fold 0 \
  --wav /absolute/path/to/lung-recording.wav \
  --output artifacts/lung-launch/lung-recording-localization.json
```

Use a new output path for every invocation. Input uses the existing recorded-audio
quality/size rules: mono RIFF/WAVE, 5–120 seconds, finite normalized audio,
non-silent and within clipping limits. Models are loaded in inference-only safe
mode. The experiment must be completed and carry development-only metadata;
thresholds come from its saved evaluation. No thresholds are selected here.

The research JSON includes:

- frame-center times and six scores per frame, in the saved class order;
- separate `phase_intervals` and `sound_events`;
- each candidate's `label`, `start_s`, `end_s`, `duration_s`, positive-frame count,
  mean positive-frame score, maximum score and saved threshold;
- model, normalization, source and WAV hashes, localization version and rules;
- respiratory measurements only when three complete unambiguous cycles exist;
- explicit `development_only` / `deployment_eligible: false` status and limitations.

Scores are uncalibrated and are not diagnostic probabilities. Hashes identify
the files used now; older experiments did not pre-save hashes of every weight
file, so this does not independently prove original checkpoint authenticity.

## Boundary decoding

Version `lung-frame-events-v2` averages overlapping window scores by absolute
frame position before event extraction. A candidate begins/ends half a frame
hop before/after its first/last positive frame center. Adjacent positives merge
with a small floating-point tolerance; different classes may overlap. Missing
timeline frames always split candidates. Optional `--minimum-s` and
`--merge-gap-s` remove short candidates or join runs across known negative
frames, respectively. Defaults are zero. Postprocessing settings are recorded,
not automatically optimized.

For the baseline, hop spacing is 16 ms and FFT support is 64 ms. **This is grid
resolution, not a claim of 16-ms localization accuracy.** No timestamps are
extrapolated into unanalyzed recording edges or padded tails. Crackle timestamps
represent periods containing crackles under HF labels, not individual clicks.
Independent phase outputs may overlap; ambiguous respiratory results remain null.

## Evaluate existing development predictions

No WAV inference or model loading is needed for this command:

```bash
python scripts/evaluate_lung_localization.py \
  --cache data/processed/lung/cache/fa2fc598295d3e8b71d8e34cee4ecc7c21866cb658f57367ca9aa5ff546cee14 \
  --experiment results/EXP-L003-temporal-cnn \
  --fold 0 \
  --tolerance-s 0.1 \
  --output artifacts/lung-launch/EXP-L003-localization-evaluation.json
```

The command binds the experiment to cache/config/audit provenance, requires every
held-out cache window exactly once, and checks saved truth/masks against each
cache block before slicing scores. It reconstructs recording timelines using
the saved prediction index and absolute sample offsets. Official test/quarantine
recordings are rejected. Source development event annotations are used for
one-to-one matching; no official test annotation file is read.

Results include recording-level reference/predicted intervals, per-class event
TP/FP/FN/F1, onset/offset/duration MAE for matched events and aggregate event
counts/F1 plus match-weighted onset/offset MAE. Unmatched events contribute to
FP/FN, not boundary MAE; a null MAE means no matches. Default matching requires
both boundaries within 100 ms. Labels are imperfect and may omit unclear sounds,
so these are development diagnostics, not clinical performance claims. Raw
interval matching also exposes the difference between frame overlap targets
and original annotation boundaries.

Keep these outputs outside immutable experiment directories. Do not repeatedly
tune against the official test; this command is for development predictions only.

## Existing backend and UI

The existing `lung-analysis-v1` backend/UI already renders start/end intervals
on its timeline. Future approved packages can use the same v2 decoder by freezing
`"localization_version": "lung-frame-events-v2"` in the final selection JSON.
Final training preserves that selection; locked evaluation records the chosen
version, and the package verifier/inference backend honor it. The existing API
interval fields remain `label`, `start_s`, `end_s`.

Legacy selections/evidence without the field retain v1 decoding; existing frozen
rules are not silently changed. Unknown versions are rejected. No deployment
eligibility checks are bypassed. EXP-L003 remains a research candidate and is
not activated in the WebApp by these commands. Model-quality improvements,
annotation-policy review and final engineering approval remain required.
