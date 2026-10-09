#!/usr/bin/env bash
# H022 launcher. --check is strictly read-only and never starts training.
set -euo pipefail

name=h022-fold-local-hard-negative-contrastive-representation
unit="auriscore-${name}.service"
expected_root=/home/rowen/projects/Despro-AurisCore/AI-Pipeline
python=/home/rowen/.venvs/auriscore-gpu-tf220/bin/python

if (( $# > 1 )) || { (( $# == 1 )) && [[ "$1" != "--check" ]]; }; then
  echo "Usage: ./scripts/start_h022.sh [--check]" >&2
  exit 2
fi
if [[ "$(pwd -P)" != "$expected_root" ||
      "$(git -C .. branch --show-current)" != "reconcile/research-master-20261009" ]]; then
  echo "Wrong research checkout or branch; refusing H022" >&2
  exit 1
fi
if [[ ! -x "$python" ]]; then
  echo "Expected H022 Python environment is unavailable" >&2
  exit 1
fi
"$python" scripts/h022_preflight.py check >/dev/null
"$python" - <<'PY'
import json, sys, tensorflow as tf
from pathlib import Path
if tf.__version__ != '2.20.0' or not tf.config.list_physical_devices('GPU'):
    sys.exit('TensorFlow 2.20.0 with CUDA GPU is required')
root = Path('analysis/EXP-H021-fold-local-hard-negative-acoustic-mining')
metrics = json.loads((root / 'metrics.json').read_text())
if metrics.get('external_validation_opened') is not False or metrics.get('sealed_test_opened') is not False:
    sys.exit('H021 development data boundary changed')
if Path('analysis/EXP-H022-fold-local-hard-negative-contrastive-representation/metrics.json').exists():
    sys.exit('H022 OOF metrics already exist; duplicate run refused')
print('TensorFlow', tf.__version__, 'GPU', [d.name for d in tf.config.list_physical_devices('GPU')])
PY
systemctl --user show-environment >/dev/null
if systemctl --user --quiet is-active "$unit"; then
  echo "H022 service already running: $unit" >&2
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  echo "H022 READY: protocol/provenance/branch/TRAIN data/Python/GPU/systemd verified; no training started"
  exit 0
fi

mkdir -p .runtime results/EXP-H022-fold-local-hard-negative-contrastive-representation
./scripts/launch_wsl_gpu_experiment.sh "$name" scripts/train_h022_contrastive.py run
echo "Service: $unit"
echo "Log: $PWD/.runtime/$name.stdout.log"
echo "Error log: $PWD/.runtime/$name.stderr.log"
echo "Result: $PWD/results/EXP-H022-fold-local-hard-negative-contrastive-representation"
