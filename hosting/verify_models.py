"""Fail closed before starting the hosted engineering inference worker."""
import os
from pathlib import Path
import sys

pipeline = Path(os.environ.get('AURISCORE_PIPELINE_DIR', '/app/AI-Pipeline'))
sys.path.insert(0, str(pipeline / 'src'))
from auriscore.engineering_inference import definitions

if __name__ == '__main__':
    models = definitions(os.environ.get('AURISCORE_ENGINEERING_MODELS', '/models/manifest.json'))
    if {item.mode for item in models} != {'heart', 'lung', 'abdomen'}:
        raise SystemExit('All three explicit engineering models are required')
    print('Engineering model hashes verified; clinical deployment eligibility unchanged.', flush=True)
