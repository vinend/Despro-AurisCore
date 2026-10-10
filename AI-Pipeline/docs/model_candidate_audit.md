# Model candidate audit and packaging

Step 1 of Heart/Abdomen integration audits saved artifacts before they enter an
analysis service. It does not train, change thresholds, score research recordings,
or authorize production inference. Heart remains Rhythm DSP + Cardiac Event DSP
+ Murmur AI; a bowel activity classifier is not the full Abdomen product.

## Run from AI-Pipeline (PowerShell)

```powershell
.venv\Scripts\python.exe scripts\audit_model_candidates.py
.venv\Scripts\python.exe scripts\audit_model_candidates.py --runtime --report analysis\model-candidate-runtime-v1.json
.venv\Scripts\python.exe scripts\audit_model_candidates.py --package EXP-A005-abdomen-cnn-residual-se --runtime --destination artifacts\candidate-packages\abdomen-a005-v1
.venv\Scripts\python.exe scripts\audit_model_candidates.py --verify artifacts\candidate-packages\abdomen-a005-v1
.venv\Scripts\python.exe -m pytest -q tests\test_model_audit.py
```

Use the repository CNN requirements for `--runtime`. Structural checks need only
Python's standard library. Reports and candidate destinations refuse overwrite;
use a new version/path for a fresh audit. A failed candidate/runtime probe yields
CLI exit code 1; input/packaging errors yield 2. Runtime probes load with Keras
safe mode and exercise synthetic audio twice for shape, finite range, and
determinism. They establish loadability, not model accuracy or calibration.

On this Windows workspace TensorFlow installation under the deeply nested
repository `.venv` hits the Windows path-length limit. A shorter audit environment
is used instead:

```powershell
$auditPython = "$env:USERPROFILE\.codex\envs\auriscore-audit\Scripts\python.exe"
& $auditPython scripts\audit_model_candidates.py --runtime
& $auditPython -m pytest -q tests\test_model_audit.py
```

For a fresh setup, create that environment with `python -m venv` and install
`requirements-cnn.txt` using its Python executable. Set `AURISCORE_PYTHON` to
this executable only when a later analysis-service step is configured.

The inventory covers standalone saved CNN experiment directories with
`heart_cnn.keras`, its metadata, and metrics. H021 is represented separately by
its freeze declaration; audit does not copy or select one of its research folds.

## Checks and package contract

The audit checks Keras ZIP integrity, actual saved input/output configuration,
preprocessing-derived tensor dimensions, trained frequency normalization,
Nyquist/filter limits, metadata/evaluation threshold equality, and SHA-256 hashes.
Validation participant count and threshold selection unit are exposed.

`model-candidate-v1` packages contain `model.keras`, unchanged
`source_metadata.json`, unchanged `source_metrics.json`, and `manifest.json`.
The manifest has corrected domain/target names, preprocessing, tensor dimensions,
threshold selection semantics, runtime evidence, limitations, and file hashes.
Source experiments remain unchanged. Verification checks hashes and agreement
between the normalized preprocessing/threshold contract and source metadata.
Candidate packages always carry `deployment_eligible: false`; runtime success
cannot promote them. Local packages are ignored by Git.

## Selection result

- Abdomen A005 is a preliminary engineering candidate. Its threshold was selected
  at window-segment level and validation includes only one independent participant.
  Do not reuse this threshold for mean recording scores or infer event subtypes.
- Historical Heart CNN weights are loadability candidates; their participant-level
  thresholds do not establish a single-WAV inference procedure.
- H021 has no final all-TRAIN model or predeclared ensemble. Its OOF threshold
  cannot be transferred to one fold or a newly defined ensemble. Heart deployment
  selection remains empty until a separately specified model/rule is evaluated.
  The audit records availability/hash status for all 15 model/normalization/scaler
  fold artifacts. All 15 are absent from this Windows checkout; their hashes are
  preserved in the research freeze manifest. No inference folds are substituted.

No external validation or sealed test is opened. No H022 training is launched.

## Verified implementation result (2026-10-10)

All 13 standalone CNNs (A001–A006 and H001–H007) passed structural validation
and CPU synthetic inference using Python 3.12, TensorFlow 2.21.0 and Keras 3.15.1.
Machine-readable evidence is in `analysis/model-candidate-audit-v1.json` and
`analysis/model-candidate-runtime-v1.json`. Synthetic scores are not performance
measurements. The A005 package is local under
`artifacts/candidate-packages/abdomen-a005-v1/` and is excluded from version control.

51 focused tests passed across model audit/packaging, H021 freeze/adapter, Heart
DSP, and the Heart file bridge. Windows automatic line-ending conversion had
broken H021 byte hashes; `.gitattributes` now preserves the frozen files exactly
as committed. Original freeze hashes and contents have not been revised.

This step implements preparation tooling and identifies the outstanding Heart
deployment-model decision. It does not connect either model to the live workflow;
that belongs to the subsequent analysis-service and application steps.
