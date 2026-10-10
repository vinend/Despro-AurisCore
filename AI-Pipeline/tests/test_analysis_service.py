"""Routing, quality, backend lifecycle, and persistent transport contract checks."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import base64
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

from auriscore.analysis_service import (
    AnalysisService, AudioPolicy, BackendDefinition, BackendOutput, candidate_backend,
)
from auriscore.model_audit import package_candidate

ROOT = Path(__file__).resolve().parents[1]


def audio(seconds=5, sr=8000):
    t = np.arange(round(seconds * sr)) / sr
    return 0.2 * np.sin(2 * np.pi * 180 * t)


def wav(samples, sr=8000):
    stream = BytesIO()
    sf.write(stream, samples, sr, format='WAV', subtype='FLOAT')
    return stream.getvalue()


class StubBackend:
    def __init__(self, mode='abdomen'):
        self.mode = mode

    def analyze(self, samples, sr):
        assert not samples.flags.writeable
        return BackendOutput({'schema_version': f'{self.mode}-analysis-v1', 'mode': self.mode,
                              'sample_count': len(samples), 'sample_rate': sr})


def test_default_heart_has_real_dsp_and_explicit_missing_murmur():
    result = AnalysisService().analyze_pcm(audio(), 8000, 'heart', request_id='recording-1')
    assert result['schema_version'] == 'organ-analysis-v1'
    assert result['status'] == 'partial'
    assert result['request_id'] == 'recording-1'
    assert result['quality']['valid']
    assert result['analysis']['schema_version'] == 'heart-analysis-v1'
    assert result['analysis']['murmur']['status'] == 'unavailable'
    assert result['errors'][0]['component'] == 'murmur'
    assert result['model_version'] is None
    json.dumps(result, allow_nan=False)


def test_real_heart_pulses_produce_expected_bpm():
    t = np.arange(8000 * 8) / 8000
    signal = np.zeros_like(t)
    for s1 in np.arange(.4, 7.2, .8):
        for center, amplitude in ((s1, .5), (s1 + .3, .35)):
            signal += amplitude * np.sin(2 * np.pi * 65 * (t - center)) * np.exp(-.5 * ((t - center) / .016) ** 2)
    result = AnalysisService().analyze_pcm(signal, 8000, 'heart')
    assert result['analysis']['rhythm']['heart_rate_bpm'] == 75


def test_abdomen_is_explicitly_unavailable_until_registered():
    result = AnalysisService().analyze_pcm(audio(), 8000, 'abdomen')
    assert result['status'] == 'unavailable'
    assert result['analysis'] is None
    assert result['quality']['valid']
    assert result['errors'][0]['code'] == 'MODEL_UNAVAILABLE'


@pytest.mark.parametrize('samples,sr,encoding,code', [
    ([], 8000, 'float', 'INVALID_AUDIO'),
    ([float('nan')], 8000, 'float', 'INVALID_AUDIO'),
    ([float('inf')], 8000, 'float', 'INVALID_AUDIO'),
    ([[0.2, 0.3]], 8000, 'float', 'INVALID_AUDIO'),
    (['0.1'], 8000, 'float', 'INVALID_AUDIO'),
    ([True], 8000, 'float', 'INVALID_AUDIO'),
    ([2.0], 8000, 'float', 'INVALID_AUDIO'),
    ([1.5], 8000, 'int16', 'INVALID_AUDIO'),
    ([32768], 8000, 'int16', 'INVALID_AUDIO'),
    ([0], 8000, 'unsigned', 'INVALID_AUDIO'),
    ([0], True, 'float', 'INVALID_SAMPLE_RATE'),
    ([0], 8000.5, 'float', 'INVALID_SAMPLE_RATE'),
    ([0], 0, 'float', 'INVALID_SAMPLE_RATE'),
    ([0], 999, 'float', 'INVALID_SAMPLE_RATE'),
])
def test_invalid_pcm_never_calls_backend(samples, sr, encoding, code):
    def forbidden():
        pytest.fail('Invalid audio must not load a model')
    service = AnalysisService(backends=[BackendDefinition('heart', 'test-v1', forbidden)])
    result = service.analyze_pcm(samples, sr, 'heart', encoding=encoding)
    assert result['analysis'] is None
    assert result['errors'][0]['code'] == code


@pytest.mark.parametrize('samples,reason', [
    (np.zeros(40000), 'silent_signal'),
    (np.full(40000, 0.2), 'silent_signal'),
    (np.tile([-1.0, 1.0], 20000), 'clipped_signal'),
    (audio(2), 'signal_too_short'),
])
def test_quality_failure_is_actionable(samples, reason):
    result = AnalysisService().analyze_pcm(samples, 8000, 'heart')
    assert not result['quality']['valid']
    assert result['quality']['reason'] == reason
    assert result['errors'][0]['code'] == 'LOW_SIGNAL_QUALITY'
    assert result['analysis'] is None


def test_int16_conversion_matches_float_input():
    samples = (audio() * 32768).astype(np.int16)
    service = AnalysisService()
    integer = service.analyze_pcm(samples, 8000, 'heart', encoding='int16')
    floating = service.analyze_pcm(samples.astype(float) / 32768, 8000, 'heart')
    assert integer['analysis'] == floating['analysis']
    assert integer['quality'] == floating['quality']


def test_wav_and_pcm_produce_the_same_heart_result():
    samples = audio().astype(np.float32)
    service = AnalysisService()
    file_result = service.analyze_wav(wav(samples), 'heart')
    pcm_result = service.analyze_pcm(samples, 8000, 'heart')
    assert file_result['source'] == 'wav'
    assert file_result['analysis'] == pcm_result['analysis']


@pytest.mark.parametrize('data', [b'', b'not a WAV', wav(np.zeros((40000, 2)))], ids=['empty', 'malformed', 'stereo'])
def test_invalid_wav_returns_structured_error(data):
    result = AnalysisService().analyze_wav(data, 'heart')
    assert result['errors'][0]['code'] == 'INVALID_AUDIO'
    assert result['analysis'] is None


def test_audio_limits_are_configurable_and_checked_before_inference():
    service = AnalysisService(policy=AudioPolicy(max_samples=1000))
    assert service.analyze_pcm(audio(), 8000, 'heart')['errors'][0]['code'] == 'AUDIO_TOO_LARGE'
    assert service.analyze_wav(wav(audio()), 'heart')['errors'][0]['code'] == 'AUDIO_TOO_LARGE'


def test_mode_and_request_id_validation():
    service = AnalysisService()
    for mode in ('lung', None, ['heart']):
        assert service.analyze_pcm(audio(), 8000, mode)['errors'][0]['code'] == 'UNSUPPORTED_MODE'
    assert service.analyze_pcm(audio(), 8000, 'heart', request_id=42)['errors'][0]['code'] == 'INVALID_REQUEST'


def test_backend_loads_once_even_with_concurrent_requests():
    loads = []
    def factory():
        loads.append(True)
        return StubBackend()
    definition = BackendDefinition('abdomen', 'test-v1', factory,
                                   model_version='fixture-model-v1', requires_model=True,
                                   deployment_eligible=True)
    service = AnalysisService(backends=[definition])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.analyze_pcm(audio(), 8000, 'abdomen'), range(8)))
    assert len(loads) == 1
    assert all(result['status'] == 'completed' for result in results)
    assert all(result['model_version'] == 'fixture-model-v1' for result in results)


def test_real_candidate_remains_blocked_and_factory_is_not_called(tmp_path):
    package = tmp_path / 'a005'
    package_candidate(ROOT / 'results/EXP-A005-abdomen-cnn-residual-se', package)
    def forbidden():
        pytest.fail('Candidate must not be loaded as a deployment model')
    service = AnalysisService(backends=[candidate_backend(package, forbidden)])
    result = service.analyze_pcm(audio(), 8000, 'abdomen')
    assert result['status'] == 'unavailable'
    assert result['errors'][0]['code'] == 'MODEL_NOT_AUTHORIZED'


def test_failed_load_is_cached_without_leaking_exception_details():
    loads = []
    def fail():
        loads.append(True)
        raise RuntimeError('secret machine path C:/private/model')
    service = AnalysisService(backends=[BackendDefinition('abdomen', 'test-v1', fail)])
    for _ in range(2):
        result = service.analyze_pcm(audio(), 8000, 'abdomen')
        assert result['errors'][0]['code'] == 'MODEL_LOAD_FAILED'
        assert 'private' not in json.dumps(result)
    assert len(loads) == 1


@pytest.mark.parametrize('kind,code', [('exception', 'INFERENCE_FAILED'), ('nan', 'INVALID_ANALYSIS_RESULT'), ('mode', 'INVALID_ANALYSIS_RESULT')])
def test_backend_failures_have_explicit_codes(kind, code):
    class Broken:
        def analyze(self, samples, sr):
            if kind == 'exception':
                raise RuntimeError('internal details')
            return BackendOutput({'mode': 'heart' if kind == 'mode' else 'abdomen',
                                  'schema_version': 'abdomen-analysis-v1', 'score': float('nan') if kind == 'nan' else 0.5})
    result = AnalysisService(backends=[BackendDefinition('abdomen', 'test-v1', Broken)]).analyze_pcm(audio(), 8000, 'abdomen')
    assert result['errors'][0]['code'] == code
    assert result['analysis'] is None


def test_backend_quality_rejection_does_not_expose_analysis():
    class InvalidSignal:
        def analyze(self, samples, sr):
            return BackendOutput({'mode': 'abdomen', 'schema_version': 'abdomen-analysis-v1',
                                  'quality': {'valid': False, 'reason': 'filtered_signal_too_weak'}})
    result = AnalysisService(backends=[BackendDefinition('abdomen', 'test-v1', InvalidSignal)]).analyze_pcm(audio(), 8000, 'abdomen')
    assert result['errors'][0]['code'] == 'LOW_SIGNAL_QUALITY'
    assert not result['quality']['valid'] and result['analysis'] is None


def test_backend_configuration_rejects_accidental_eligibility_bypass():
    with pytest.raises(ValueError):
        AnalysisService(backends=[BackendDefinition('abdomen', 'test-v1', StubBackend,
                        model_version='model-v1', requires_model=False)])
    with pytest.raises(ValueError):
        AnalysisService(backends=[BackendDefinition('abdomen', 'test-v1', StubBackend,
                        model_version='model-v1', requires_model=True, deployment_eligible='false')])


def test_persistent_worker_recovers_after_bad_json_and_routes_two_modes():
    requests = 'bad json\n' + '\n'.join(json.dumps({
        'mode': mode, 'sample_rate': 8000, 'samples': audio().tolist(), 'request_id': mode,
    }) for mode in ('heart', 'abdomen')) + '\n'
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_recording.py'), '--serve'],
                              input=requests, text=True, capture_output=True, timeout=30)
    assert response.returncode == 0, response.stderr
    results = [json.loads(line) for line in response.stdout.splitlines()]
    assert len(results) == 3
    assert results[0]['errors'][0]['code'] == 'INVALID_REQUEST'
    assert results[1]['request_id'] == 'heart' and results[1]['status'] == 'partial'
    assert results[2]['request_id'] == 'abdomen' and results[2]['status'] == 'unavailable'


def test_worker_supports_wav_base64_and_rejects_ambiguous_input():
    encoded = base64.b64encode(wav(audio())).decode('ascii')
    requests = [ {'mode': 'heart', 'wav_base64': encoded, 'request_id': 'wav-1'},
                 {'mode': 'heart', 'wav_base64': 'invalid'},
                 {'mode': 'heart', 'wav_base64': encoded, 'samples': [0]} ]
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_recording.py'), '--serve'],
                              input='\n'.join(json.dumps(item) for item in requests) + '\n',
                              text=True, capture_output=True, timeout=30)
    assert response.returncode == 0, response.stderr
    results = [json.loads(line) for line in response.stdout.splitlines()]
    assert results[0]['source'] == 'wav' and results[0]['request_id'] == 'wav-1'
    assert results[0]['status'] == 'partial'
    assert all(item['errors'][0]['code'] == 'INVALID_REQUEST' for item in results[1:])
