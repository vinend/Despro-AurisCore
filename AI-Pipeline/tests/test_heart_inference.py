"""Deployment-contract fixtures are fictional; none establishes model performance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from auriscore.analysis_service import AnalysisService, BackendDefinition
from auriscore.heart_inference import (
    HeartInferenceBackend, MurmurInferenceError, RecordingMurmurScorer,
    load_heart_deployment, prepare_heart_deployment, validate_recording_evidence,
)
from auriscore.model_audit import digest, package_candidate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'results/EXP-H001-cnn-compact'


def signal(seconds=8, sr=8000):
    t = np.arange(round(seconds * sr)) / sr
    return .2 * np.sin(2 * np.pi * 65 * t) + .05 * np.sin(2 * np.pi * 140 * t)


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def inputs(tmp_path):
    metadata = json.loads((SOURCE / 'heart_cnn.json').read_text())
    decision = {'decision_id': 'fictional-test-decision', 'status': 'approved_for_engineering_inference',
                'model_role': 'final_deployment_model', 'target': 'murmur_presence',
                'model_version': 'fixture-model-v1', 'preprocessing_version': 'fixture-dsp-v1',
                'threshold_version': 'fixture-threshold-v1', 'deployment_run_id': 'fictional-unit-test'}
    evaluation = {'inference_unit': 'recording', 'aggregation': 'mean_window_score',
                  'threshold_selection_split': 'validation', 'participant_disjoint': True,
                  'model_version': 'fixture-model-v1', 'preprocessing_version': 'fixture-dsp-v1',
                  'threshold_version': 'fixture-threshold-v1', 'dataset_version': 'fictional-fixture',
                  'split_sha256': 'a' * 64, 'participants': 4, 'decision_threshold': .55,
                  'class_counts': {'absent': 2, 'present': 2}, 'confusion_matrix': [[2, 0], [0, 2]],
                  'metrics': {'recall_sensitivity': 1., 'specificity': 1., 'precision': 1., 'f1': 1.,
                              'roc_auc': 1., 'pr_auc': 1., 'accuracy': 1.},
                  'model_sha256': digest(SOURCE / 'heart_cnn.keras'),
                  'preprocessing_sha256': hashlib.sha256(json.dumps(metadata['config'], sort_keys=True, allow_nan=False).encode()).hexdigest()}
    for name, value in [('metadata', metadata), ('evaluation', evaluation), ('decision', decision)]:
        save(tmp_path / f'{name}.json', value)
    return tmp_path, metadata, evaluation, decision


@pytest.fixture
def deployment(inputs):
    folder, _, _, _ = inputs
    destination = folder / 'test-package'
    prepare_heart_deployment(SOURCE / 'heart_cnn.keras', folder / 'metadata.json',
                             folder / 'evaluation.json', folder / 'decision.json', destination)
    return destination


class ModelStub:
    input_shape = (None, 40, 313, 1)
    output_shape = (None, 1)

    def __init__(self, value=.8):
        self.value, self.batches = value, []

    def __call__(self, tensor, training):
        assert training is False
        self.batches.append(tensor.copy())
        return np.full((len(tensor), 1), self.value)


def test_existing_webapp_bridge_runs_configured_model(deployment):
    from io import BytesIO
    import os
    import soundfile as sf
    stream = BytesIO()
    sf.write(stream, signal(), 8000, format='WAV')
    # Fictional approval fixture exercises transport only, not model performance.
    env = dict(os.environ, AURISCORE_HEART_PACKAGE=str(deployment),
               CUDA_VISIBLE_DEVICES='-1', TF_CPP_MIN_LOG_LEVEL='3')
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_heart_wav.py'), '--stdin'],
                              input=stream.getvalue(), capture_output=True, env=env, timeout=60)
    assert response.returncode == 0, response.stderr.decode(errors='replace')
    result = json.loads(response.stdout)
    assert result['schema_version'] == 'heart-analysis-v1'
    assert result['rhythm'] is not None and result['cardiac_events'] is not None
    assert result['murmur']['status'] == 'available'
    assert result['murmur']['model_version'] == 'fixture-model-v1'
    assert result['murmur']['window_count'] == 2


def test_existing_webapp_bridge_rejects_bad_package_configuration(tmp_path):
    import os
    env = dict(os.environ, AURISCORE_HEART_PACKAGE=str(tmp_path / 'missing'))
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_heart_wav.py'), '--stdin'],
                              input=b'', capture_output=True, env=env, timeout=30)
    assert response.returncode == 3
    assert not response.stdout


def test_frozen_tensor_pipeline_matches_existing_implementation(inputs):
    from auriscore.preprocessing import preprocess
    from auriscore.segmentation import segment
    from auriscore.spectrogram import extract_spectrogram_tensor
    _, metadata, _, _ = inputs
    model = ModelStub(.4)
    loads = []
    def loader(path):
        loads.append(path)
        return model
    scorer = RecordingMurmurScorer(SOURCE / 'heart_cnn.keras', metadata, loader=loader, batch_size=2)
    audio = signal(12.5, 16000)
    result = scorer.score(audio, 16000)
    config = metadata['config']
    expected = np.stack([extract_spectrogram_tensor(window, config) for _, window, _ in
                        segment(preprocess(audio, 16000, config), 8000, 5, .5)])[..., None]
    assert result == {'score': .4, 'window_count': 4}
    np.testing.assert_array_equal(np.concatenate(model.batches), expected)
    scorer.score(audio, 16000)
    assert len(loads) == 1


def test_all_three_heart_branches_use_one_versioned_result(deployment):
    backend = HeartInferenceBackend(deployment, loader=lambda _: ModelStub())
    definition = BackendDefinition('heart', 'heart-inference-v1', lambda: backend,
                                   model_version='fixture-model-v1', requires_model=True, deployment_eligible=True)
    result = AnalysisService(backends=[definition]).analyze_pcm(signal(), 8000, 'heart')
    assert result['status'] == 'completed' and not result['errors']
    heart = result['analysis']
    assert heart['rhythm'] is not None and heart['cardiac_events'] is not None
    assert heart['murmur']['label'] == 'present'
    assert heart['murmur']['model_version'] == 'fixture-model-v1'
    assert heart['murmur']['threshold'] == .55
    assert heart['murmur']['inference_unit'] == 'recording'
    assert heart['murmur']['probability_is_calibrated'] is False


def test_model_load_failure_is_cached_and_preserves_heart_dsp(deployment):
    loads = []
    def loader(_):
        loads.append(True)
        raise RuntimeError('private runtime information')
    backend = HeartInferenceBackend(deployment, loader=loader)
    for _ in range(2):
        result = backend.analyze(signal(), 8000)
        assert result.status == 'partial'
        assert result.analysis['rhythm'] is not None
        assert result.analysis['murmur']['status'] == 'unavailable'
        assert result.errors[0].code == 'MODEL_LOAD_FAILED'
    assert len(loads) == 1


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1., 1.5])
def test_bad_predictions_do_not_discard_dsp(deployment, value):
    result = HeartInferenceBackend(deployment, loader=lambda _: ModelStub(value)).analyze(signal(), 8000)
    assert result.status == 'partial' and result.errors[0].code == 'INFERENCE_FAILED'
    assert result.analysis['cardiac_events'] is not None
    assert result.analysis['murmur']['status'] == 'unavailable'


def test_short_recording_keeps_dsp_without_padding_for_model(deployment):
    def forbidden(_):
        pytest.fail('Short audio cannot load a model')
    result = HeartInferenceBackend(deployment, loader=forbidden).analyze(signal(3.5), 8000)
    assert result.status == 'partial'
    assert result.errors[0].code == 'MURMUR_INSUFFICIENT_AUDIO'


def test_invalid_audio_cannot_load_model(deployment):
    def forbidden(_):
        pytest.fail('Invalid audio cannot load a model')
    result = HeartInferenceBackend(deployment, loader=forbidden).analyze(np.zeros(40000), 8000)
    assert not result.analysis['quality']['valid']
    assert result.analysis['murmur'] is None


@pytest.mark.parametrize('change', [
    lambda e, d: e.update(inference_unit='participant'),
    lambda e, d: e.update(aggregation='mean_fold_probability'),
    lambda e, d: e.update(threshold_selection_split='sealed_test'),
    lambda e, d: e.update(participant_disjoint=False),
    lambda e, d: e.update(decision_threshold=float('nan')),
    lambda e, d: e.update(class_counts={'absent': 0, 'present': 4}),
    lambda e, d: e['metrics'].update(f1=.60),
    lambda e, d: e['metrics'].update(roc_auc=.80),
    lambda e, d: e.update(preprocessing_version='different'),
    lambda e, d: e.update(participants=1),
    lambda e, d: e.update(confusion_matrix=[[1, 1], [1, 1]]),
    lambda e, d: d.update(status='engineering_candidate'),
    lambda e, d: d.update(model_role='outer_fold_evaluation'),
    lambda e, d: d.update(deployment_run_id='EXP-H021-fold-local-hard-negative-acoustic-mining'),
])
def test_reject_incompatible_or_unsupported_deployment_evidence(inputs, change):
    _, _, evaluation, decision = inputs
    change(evaluation, decision)
    with pytest.raises(ValueError):
        validate_recording_evidence(evaluation, decision)


def test_candidate_package_cannot_be_activated(tmp_path):
    package = tmp_path / 'candidate'
    package_candidate(SOURCE, package)
    with pytest.raises(ValueError, match='eligible'):
        load_heart_deployment(package)


def test_package_tampering_is_detected(deployment):
    with (deployment / 'model.keras').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='integrity'):
        load_heart_deployment(deployment)


def test_post_registration_weight_changes_preserve_dsp(deployment):
    backend = HeartInferenceBackend(deployment, loader=lambda _: ModelStub())
    with (deployment / 'model.keras').open('ab') as stream:
        stream.write(b'changed')
    result = backend.analyze(signal(), 8000)
    assert result.status == 'partial' and result.errors[0].code == 'MODEL_LOAD_FAILED'
    assert result.analysis['rhythm'] is not None


def test_model_evaluation_binding_rejects_wrong_weights(inputs):
    folder, _, evaluation, _ = inputs
    evaluation['model_sha256'] = '0' * 64
    save(folder / 'evaluation.json', evaluation)
    with pytest.raises(ValueError, match='different model weights'):
        prepare_heart_deployment(SOURCE / 'heart_cnn.keras', folder / 'metadata.json',
                                 folder / 'evaluation.json', folder / 'decision.json', folder / 'bad-package')
    assert not (folder / 'bad-package').exists()


def test_cli_rejects_missing_deployment_without_starting_worker(tmp_path):
    response = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_recording.py'), '--serve',
                               '--heart-package', str(tmp_path / 'missing')],
                              capture_output=True, text=True, timeout=30)
    assert response.returncode == 2 and not response.stdout


def test_real_saved_cnn_runs_raw_recording_inference_without_deployment_claim():
    metadata = json.loads((SOURCE / 'heart_cnn.json').read_text())
    scorer = RecordingMurmurScorer(SOURCE / 'heart_cnn.keras', metadata)
    result = scorer.score(signal(7.5), 8000)
    assert result['window_count'] == 2 and 0 <= result['score'] <= 1
    assert set(result) == {'score', 'window_count'}  # No threshold, label, or deployment promotion.
