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


def test_l030_uses_complete_clip_scores(monkeypatch):
    from auriscore import lung_preprocessing
    from auriscore.engineering_inference import L030ClipBackend

    backend = L030ClipBackend.__new__(L030ClipBackend)
    backend.config = dict(sample_rate=8000, hop_length=128, n_fft=512,
                          classes=['wheeze', 'rhonchi', 'crackle'])
    backend.mean = np.zeros(1)
    backend.std = np.ones(1)
    backend.thresholds = np.array([.65, .825, .525])
    scores = np.zeros((1, 124, 3))
    scores[0, 61, 0] = .7
    scores[0, 123, 1] = 1.0
    backend.model = lambda features, training: scores
    monkeypatch.setattr(lung_preprocessing, 'windows', lambda *args: iter([
        dict(start_sample=0, features=np.zeros((124, 1))),
    ]))
    output = backend.analyze(np.zeros(9000), 8000)
    assert output.status == 'partial'
    assert output.analysis['sound_events'] == [
        dict(label='wheeze', start_s=0.0, end_s=1.04),
    ]
    assert output.analysis['class_scores'][1]['maximum_frame_score'] == 0
