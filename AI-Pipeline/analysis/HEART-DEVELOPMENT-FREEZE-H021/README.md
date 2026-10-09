# H021 development freeze

This package records the completed TRAIN-only, five-fold OOF H021 result. The original model files remain in the WSL-native checkout; this package contains hashes and lightweight metadata only. H021 is the current best development candidate, not a deployment-ready or clinically validated model. External validation and sealed test were not opened.

See `artifact_manifest.json`, `decision.md`, and `inference_notes.md`.
The manifest itself is locked by `artifact_manifest_sha256.txt`.

For a read-only compatibility check from WSL, run
`python scripts/audit_h021_fold_artifacts.py --source-root ~/projects/Despro-AurisCore/AI-Pipeline`
from the Windows checkout's `AI-Pipeline` directory using a Python environment
with NumPy. This only verifies fold files; it does not produce Murmur scores.
