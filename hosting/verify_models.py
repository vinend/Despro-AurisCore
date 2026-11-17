"""Fail closed before starting the hosted engineering inference worker."""
import os
from pathlib import Path
import sys

pipeline = Path(os.environ.get('AURISCORE_PIPELINE_DIR', '/app/AI-Pipeline'))
sys.path.insert(0, str(pipeline / 'src'))
from auriscore.engineering_inference import definitions, l030_definition

if __name__ == '__main__':
    use_l030 = os.environ.get('AURISCORE_LUNG_ENGINEERING_L030') == '1'
    models = definitions(os.environ.get('AURISCORE_ENGINEERING_MODELS', '/models/manifest.json'),
                         exclude={'lung'} if use_l030 else frozenset())
    if use_l030:
        lung = l030_definition(pipeline)
        lung.factory()
        models.append(lung)
    if {item.mode for item in models} != {'heart', 'lung', 'abdomen'}:
        raise SystemExit('All three explicit engineering models are required')
    print('Engineering model hashes verified; clinical deployment eligibility unchanged.', flush=True)
