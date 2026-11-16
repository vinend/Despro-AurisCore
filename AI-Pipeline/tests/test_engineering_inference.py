"""Engineering mode cannot implicitly activate a research model."""
import hashlib
import json

import numpy as np
import pytest

from auriscore.analysis_service import AnalysisService, BackendDefinition, BackendOutput
from auriscore.engineering_inference import definitions


def test_engineering_needs_explicit_authorization():
    calls=[]
    class Example:
        def analyze(self,audio,rate):
            calls.append(1)
            return BackendOutput(dict(mode='heart',schema_version='fixture',quality=dict(valid=True)))
    item=BackendDefinition('heart','fixture',Example,'test-only',True,False,True)
    x=np.sin(np.arange(8000)*.1)*.1
    assert AnalysisService(backends=[item]).analyze_pcm(x,1000,'heart')['errors'][0]['code']=='MODEL_NOT_AUTHORIZED'
    assert not calls
    result=AnalysisService(backends=[item],allow_engineering=True).analyze_pcm(x,1000,'heart')
    assert result['usage_scope']=='engineering_test_only' and len(calls)==1


def test_engineering_config_hash_and_scope_rejection(tmp_path):
    model=tmp_path/'model.keras'
    model.write_bytes(b'fictional')
    manifest=tmp_path/'manifest.json'
    config=dict(scope='engineering_test_only',deployment_eligible=False,models={
        'heart':dict(model=str(model),hashes={'model':hashlib.sha256(b'fictional').hexdigest()},
                     version='fictional',threshold=.5)})
    manifest.write_text(json.dumps(config))
    assert definitions(manifest)[0].deployment_eligible is False
    model.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):
        definitions(manifest)
    config['deployment_eligible']=True
    manifest.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='engineering manifest'):
        definitions(manifest)
