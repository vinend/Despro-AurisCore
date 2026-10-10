"""Fictional temporary evidence fixtures test contracts, not model performance."""
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

from auriscore.abdomen_inference import (
    AbdomenInferenceBackend, AbdomenInferenceError, BowelWindowScorer,
    abdomen_backend_definition, load_abdomen_deployment, prepare_abdomen_deployment,
    validate_window_evidence,
)
from auriscore.analysis_service import AnalysisService, BackendDefinition, HeartDSPBackend
from auriscore.model_audit import digest, package_candidate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'results/EXP-A005-abdomen-cnn-residual-se'


def signal(seconds=12.75, sr=8000):
    t = np.arange(round(seconds * sr)) / sr
    return .2 * np.sin(2 * np.pi * 250 * t) + .05 * np.sin(2 * np.pi * 600 * t)


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def inputs(tmp_path):
    metadata = json.loads((SOURCE / 'heart_cnn.json').read_text())
    decision = {'decision_id': 'fictional-test-only', 'status': 'approved_for_engineering_inference',
                'model_role': 'final_deployment_model', 'target': 'bowel_sound_activity',
                'model_version': 'fictional-bowel-v1', 'preprocessing_version': 'fictional-dsp-v1',
                'threshold_version': 'fictional-window-v1', 'deployment_run_id': 'fictional-fixture',
                'engineering_gate': {'recall_sensitivity': .9, 'specificity': .5}}
    evaluation = {'target': 'bowel_sound_activity', 'mode': 'abdomen',
                  'inference_unit': 'window', 'aggregation': 'none',
                  'threshold_selection_split': 'validation', 'participant_disjoint': True,
                  'class_mapping': {'absent': 0, 'present': 1},
                  'model_version': 'fictional-bowel-v1', 'preprocessing_version': 'fictional-dsp-v1',
                  'threshold_version': 'fictional-window-v1', 'dataset_version': 'fictional-unit-test',
                  'split_sha256': 'b' * 64, 'participants': 2, 'decision_threshold': .55,
                  'class_counts': {'absent': 2, 'present': 2}, 'confusion_matrix': [[2, 0], [0, 2]],
                  'metrics': {'accuracy': 1., 'recall_sensitivity': 1., 'specificity': 1.,
                              'precision': 1., 'f1': 1., 'roc_auc': 1., 'pr_auc': 1.},
                  'window_seconds': 5., 'overlap': .5, 'tail_policy': 'discard_incomplete',
                  'model_sha256': digest(SOURCE / 'heart_cnn.keras'),
                  'preprocessing_sha256': hashlib.sha256(json.dumps(metadata['config'], sort_keys=True, allow_nan=False).encode()).hexdigest()}
    for name, value in [('metadata', metadata), ('evaluation', evaluation), ('decision', decision)]:
        save(tmp_path / f'{name}.json', value)
    return tmp_path, metadata, evaluation, decision


@pytest.fixture
def deployment(inputs):
    folder, _, _, _ = inputs
    destination = folder / 'fixture-package'
    prepare_abdomen_deployment(SOURCE / 'heart_cnn.keras', folder / 'metadata.json',
                               folder / 'evaluation.json', folder / 'decision.json', destination)
    return destination


class ModelStub:
    input_shape = (None, 40, 313, 1)
    output_shape = (None, 1)

    def __init__(self, scores=(.1, .55, .9, .3)):
        self.scores, self.offset, self.batches = scores, 0, []

    def __call__(self, tensor, training):
        assert training is False
        self.batches.append(tensor.copy())
        values = [self.scores[(self.offset + i) % len(self.scores)] for i in range(len(tensor))]
        self.offset += len(tensor)
        return np.asarray(values).reshape(-1, 1)


def service_for(deployment, loader):
    backend = AbdomenInferenceBackend(deployment, loader=loader)
    definition = BackendDefinition('abdomen', 'abdomen-inference-v1', lambda: backend,
                                   model_version='fictional-bowel-v1', requires_model=True, deployment_eligible=True)
    return AnalysisService(backends=[definition])


def test_a005_frozen_tensor_parity_resampling_statistics_and_batches(inputs):
    from auriscore.preprocessing import preprocess
    from auriscore.segmentation import segment
    from auriscore.spectrogram import extract_spectrogram_tensor
    _, metadata, _, _ = inputs
    model, loads = ModelStub(), []
    def loader(_):
        loads.append(True)
        return model
    scorer = BowelWindowScorer(SOURCE / 'heart_cnn.keras', metadata, loader=loader, batch_size=2)
    audio = signal(sr=16000)
    output = scorer.score_windows(audio, 16000)
    config = metadata['config']
    expected = np.stack([extract_spectrogram_tensor(window, config) for _, window, _ in
                         segment(preprocess(audio, 16000, config), 8000, 5., .5)])[..., None]
    np.testing.assert_array_equal(np.concatenate(model.batches), expected)
    assert [len(batch) for batch in model.batches] == [2, 2]
    assert [window['start_s'] for window in output['windows']] == [0., 2.5, 5., 7.5]
    assert output['analyzed_duration_s'] == 12.5
    assert output['discarded_tail_s'] == .25
    scorer.score_windows(audio, 16000)
    assert len(loads) == 1


def test_window_threshold_and_summary_do_not_invent_event_rate(deployment):
    result = service_for(deployment, lambda _: ModelStub()).analyze_pcm(signal(), 8000, 'abdomen', request_id='bowel-1')
    assert result['schema_version'] == 'organ-analysis-v1'
    assert result['status'] == 'completed' and result['errors'] == []
    assert result['request_id'] == 'bowel-1'
    analysis = result['analysis']
    assert analysis['schema_version'] == 'abdomen-analysis-v1' and analysis['mode'] == 'abdomen'
    activity = analysis['activity']
    assert [window['label'] for window in activity['windows']] == ['absent', 'present', 'present', 'absent']
    assert activity['active_window_count'] == 2 and activity['active_window_fraction'] == .5
    assert activity['window_count'] == 4 and activity['probability_is_calibrated'] is False
    assert activity['model_version'] == 'fictional-bowel-v1'
    assert activity['inference_unit'] == 'window' and activity['aggregation'] == 'none'
    for field in ('bowel_events', 'bowel_rate_per_minute', 'bowel_rate_variability', 'pattern_categories'):
        assert analysis[field] is None
    assert 'murmur' not in analysis and 'rhythm' not in analysis


def test_wav_float_and_int16_dispatch_parity(deployment):
    pcm = (signal() * 32768).astype(np.int16)
    stream = BytesIO()
    sf.write(stream, pcm, 8000, format='WAV', subtype='PCM_16')
    service = service_for(deployment, lambda _: ModelStub((.6,)))
    wav = service.analyze_wav(stream.getvalue(), 'abdomen')
    integer = service.analyze_pcm(pcm, 8000, 'abdomen', encoding='int16')
    floating = service.analyze_pcm(pcm.astype(float) / 32768, 8000, 'abdomen')
    assert wav['analysis'] == integer['analysis'] == floating['analysis']


@pytest.mark.parametrize('audio', [np.zeros(40000), np.full(40000, .1), np.ones(40000),
                                  np.full(40000, np.nan), np.zeros((40000, 2)), signal(4.9)])
def test_invalid_audio_never_loads_model(deployment, audio):
    loads = []
    result = service_for(deployment, lambda _: loads.append(True)).analyze_pcm(audio, 8000, 'abdomen')
    assert result['status'] == 'error' and result['analysis'] is None
    assert not loads


@pytest.mark.parametrize('seconds,expected', [(5., 1), (7.5, 2), (7.49, 1), (12.75, 4)])
def test_complete_window_geometry(inputs, seconds, expected):
    _, metadata, _, _ = inputs
    result = BowelWindowScorer(SOURCE / 'heart_cnn.keras', metadata, loader=lambda _: ModelStub()).score_windows(signal(seconds), 8000)
    assert len(result['windows']) == expected
    assert all(0 <= w['start_s'] < w['end_s'] <= seconds for w in result['windows'])


def test_short_raw_recording_is_not_padded_or_loaded(inputs):
    _, metadata, _, _ = inputs
    loads = []
    scorer = BowelWindowScorer(SOURCE / 'heart_cnn.keras', metadata, loader=lambda _: loads.append(True))
    with pytest.raises(AbdomenInferenceError) as exc:
        scorer.score_windows(signal(4.99), 8000)
    assert exc.value.code == 'ABDOMEN_INSUFFICIENT_AUDIO' and not loads


def test_model_load_failure_is_cached_and_explicit(deployment):
    loads = []
    def failed(_):
        loads.append(True)
        raise RuntimeError('private file path')
    service = service_for(deployment, failed)
    for _ in range(2):
        result = service.analyze_pcm(signal(), 8000, 'abdomen')
        assert result['status'] == 'partial'
        assert result['analysis']['activity'] is None
        assert result['errors'][0]['code'] == 'MODEL_LOAD_FAILED'
        assert 'private' not in json.dumps(result)
    assert len(loads) == 1


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -.1, 1.1])
def test_invalid_predictions_never_produce_activity(deployment, value):
    result = service_for(deployment, lambda _: ModelStub((value,))).analyze_pcm(signal(), 8000, 'abdomen')
    assert result['analysis']['activity'] is None
    assert result['errors'][0]['code'] == 'INFERENCE_FAILED'


@pytest.mark.parametrize('key,value', [('mode', 'heart'), ('target', 'murmur_presence'),
    ('inference_unit', 'recording'), ('aggregation', 'mean_window_score'),
    ('participant_disjoint', False), ('participants', 1), ('participants', True),
    ('threshold_selection_split', 'test'), ('decision_threshold', float('nan')),
    ('class_mapping', {'absent': 1, 'present': 0}), ('model_version', 'different'),
    ('split_sha256', 'bad'), ('class_counts', {'absent': 4, 'present': 0}),
    ('confusion_matrix', [[1, 0], [0, 2]])])
def test_incompatible_evidence_is_rejected(inputs, key, value):
    _, _, evaluation, decision = inputs
    evaluation[key] = value
    with pytest.raises(ValueError):
        validate_window_evidence(evaluation, decision)


@pytest.mark.parametrize('key,value', [('target', 'murmur_presence'), ('status', 'candidate'),
                                      ('model_role', 'research_fold'), ('engineering_gate', {}),
                                      ('engineering_gate', {'recall_sensitivity': 1.1, 'specificity': .5})])
def test_missing_or_incompatible_selection_is_rejected(inputs, key, value):
    _, _, evaluation, decision = inputs
    decision[key] = value
    with pytest.raises(ValueError):
        validate_window_evidence(evaluation, decision)


@pytest.mark.parametrize('key,value', [('model_sha256', 'a' * 64), ('preprocessing_sha256', 'a' * 64),
                                      ('window_seconds', 4.), ('overlap', 0.), ('tail_policy', 'pad')])
def test_weights_and_geometry_binding(inputs, key, value):
    folder, _, evaluation, _ = inputs
    evaluation[key] = value
    save(folder / 'evaluation.json', evaluation)
    with pytest.raises(ValueError):
        prepare_abdomen_deployment(SOURCE / 'heart_cnn.keras', folder / 'metadata.json',
                                   folder / 'evaluation.json', folder / 'decision.json', folder / 'package')
    assert not (folder / 'package').exists()


def test_candidate_cannot_be_promoted(tmp_path):
    destination = tmp_path / 'candidate'
    package_candidate(SOURCE, destination)
    with pytest.raises(ValueError):
        abdomen_backend_definition(destination)


def test_package_is_immutable_and_checks_tampering(inputs, deployment):
    folder, _, _, _ = inputs
    with pytest.raises(FileExistsError):
        prepare_abdomen_deployment(SOURCE / 'heart_cnn.keras', folder / 'metadata.json',
                                   folder / 'evaluation.json', folder / 'decision.json', deployment)
    model = deployment / 'model.keras'
    model.write_bytes(model.read_bytes() + b'tampered')
    with pytest.raises(ValueError):
        load_abdomen_deployment(deployment)


def test_post_registration_weight_tampering_blocks_inference(deployment):
    definition = abdomen_backend_definition(deployment)
    model = deployment / 'model.keras'
    model.write_bytes(model.read_bytes() + b'tampered')
    result = AnalysisService(backends=[definition]).analyze_pcm(signal(), 8000, 'abdomen')
    assert result['errors'][0]['code'] == 'MODEL_LOAD_FAILED'
    assert result['analysis']['activity'] is None


def test_concurrent_recordings_load_one_model(deployment):
    from concurrent.futures import ThreadPoolExecutor
    loads = []
    def loader(_):
        loads.append(True)
        return ModelStub((.7,))
    service = service_for(deployment, loader)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: service.analyze_pcm(signal(5.), 8000, 'abdomen'), range(4)))
    assert len(loads) == 1
    assert all(result['status'] == 'completed' for result in results)


def test_invalid_tensor_shape_cannot_classify(deployment):
    model = ModelStub()
    model.input_shape = (None, 40, 312, 1)
    result = service_for(deployment, lambda _: model).analyze_pcm(signal(), 8000, 'abdomen')
    assert result['errors'][0]['code'] == 'MODEL_LOAD_FAILED'
    assert result['analysis']['activity'] is None


def test_preprocessing_statistics_frozen_and_validated(inputs):
    _, metadata, _, _ = inputs
    model = ModelStub()
    scorer = BowelWindowScorer(SOURCE / 'heart_cnn.keras', metadata, loader=lambda _: model)
    metadata['config']['spectrogram_frequency_std'][0] = 0
    assert scorer.score_windows(signal(5.), 8000)['windows']
    with pytest.raises(ValueError):
        BowelWindowScorer(SOURCE / 'heart_cnn.keras', metadata)


def test_window_resource_limit_rejects_before_load(inputs):
    _, metadata, _, _ = inputs
    metadata['config']['overlap'] = .9999
    loads = []
    scorer = BowelWindowScorer(SOURCE / 'heart_cnn.keras', metadata, loader=lambda _: loads.append(True))
    with pytest.raises(AbdomenInferenceError) as exc:
        scorer.score_windows(signal(), 8000)
    assert exc.value.code == 'AUDIO_TOO_LARGE' and not loads


def test_gate_checks_metrics_and_matrix_not_only_declared_accuracy(inputs):
    _, _, evaluation, decision = inputs
    evaluation['confusion_matrix'] = [[2, 0], [1, 1]]
    evaluation['metrics'].update(accuracy=.75, recall_sensitivity=.5, precision=1., f1=2/3)
    with pytest.raises(ValueError, match='gate'):
        validate_window_evidence(evaluation, decision)


def test_raw_a005_scoring_is_not_deployment_selection(inputs):
    _, metadata, _, _ = inputs
    scorer = BowelWindowScorer(SOURCE / 'heart_cnn.keras', metadata)
    result = scorer.score_windows(signal(5.), 8000)
    assert len(result['windows']) == 1 and 0 <= result['windows'][0]['score'] <= 1
    assert 'label' not in result['windows'][0] and 'threshold' not in result


def test_heart_and_abdomen_dispatch_are_independent(deployment):
    abdomen = service_for(deployment, lambda _: ModelStub())._slots['abdomen'].definition
    service = AnalysisService(backends=[BackendDefinition('heart', 'heart-dsp-prototype-0.1.0', HeartDSPBackend), abdomen])
    heart = service.analyze_pcm(signal(), 8000, 'heart')
    bowel = service.analyze_pcm(signal(), 8000, 'abdomen')
    assert heart['analysis']['mode'] == 'heart' and heart['analysis']['murmur']['status'] == 'unavailable'
    assert bowel['analysis']['mode'] == 'abdomen' and bowel['status'] == 'completed'


def clean_env():
    return {key: value for key, value in os.environ.items() if key not in ('AURISCORE_HEART_PACKAGE', 'AURISCORE_ABDOMEN_PACKAGE')}


def test_cli_bad_package_rejected_before_processing(tmp_path):
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_recording.py'), '--serve',
                               '--abdomen-package', str(tmp_path / 'missing')], input=b'',
                              capture_output=True, env=clean_env(), timeout=30)
    assert response.returncode == 2 and not response.stdout


def test_stdin_wav_adapter_preserves_unavailable_and_invalid_quality():
    for audio, status in [(signal(5.), 'unavailable'), (np.zeros(40000), 'error')]:
        stream = BytesIO()
        sf.write(stream, audio, 8000, format='WAV')
        response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_recording.py'), '--stdin', '--mode', 'abdomen'],
                                  input=stream.getvalue(), capture_output=True, env=clean_env(), timeout=30)
        result = json.loads(response.stdout)
        assert response.returncode == 1
        assert result['status'] == status and result['mode'] == 'abdomen'
        assert result['analysis'] is None


def test_worker_runs_real_a005_on_synthetic_audio_and_keeps_heart_default(deployment):
    # Synthetic smoke verification, with fictional selection fixture only.
    requests = [{'samples': signal(7.5).tolist(), 'sample_rate': 8000, 'mode': mode, 'request_id': mode}
                for mode in ('abdomen', 'abdomen', 'heart')]
    env = dict(clean_env(), AURISCORE_ABDOMEN_PACKAGE=str(deployment), TF_CPP_MIN_LOG_LEVEL='3', CUDA_VISIBLE_DEVICES='-1')
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_recording.py'), '--serve'],
                              input=''.join(json.dumps(req) + '\n' for req in requests).encode(),
                              capture_output=True, env=env, timeout=60)
    assert response.returncode == 0, response.stderr.decode(errors='replace')
    first, second, heart = [json.loads(line) for line in response.stdout.splitlines()]
    assert first['status'] == second['status'] == 'completed'
    assert first['analysis'] == second['analysis']
    assert first['analysis']['activity']['window_count'] == 2
    assert all(0 <= w['score'] <= 1 for w in first['analysis']['activity']['windows'])
    assert heart['analysis']['mode'] == 'heart'
    assert heart['analysis']['murmur']['status'] == 'unavailable'


def test_configured_stdin_wav_bridge_returns_real_activity(deployment):
    stream = BytesIO()
    sf.write(stream, signal(7.5), 8000, format='WAV')
    env = dict(clean_env(), TF_CPP_MIN_LOG_LEVEL='3', CUDA_VISIBLE_DEVICES='-1')
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_recording.py'), '--stdin', '--mode', 'abdomen',
                               '--abdomen-package', str(deployment)], input=stream.getvalue(),
                              capture_output=True, env=env, timeout=60)
    assert response.returncode == 0, response.stderr.decode(errors='replace')
    result = json.loads(response.stdout)
    assert result['status'] == 'completed' and result['source'] == 'wav'
    assert result['analysis']['activity']['window_count'] == 2
    assert result['analysis']['activity']['model_version'] == 'fictional-bowel-v1'
