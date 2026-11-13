"""Fictional SPRSound mapping, missing-label masks and test-inventory isolation."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import soundfile as sf
import yaml

from auriscore.acquisition_lung import digest
from auriscore.sprsound import REVISION, eligible_train, parse_annotation, acoustic_mask
from auriscore.lung_multisource import build_cache

CONFIG = yaml.safe_load((Path(__file__).parents[1] / 'configs/lung_cnn.yaml').read_text())


def test_test_patients_and_identical_test_content_excluded_without_reading_labels():
    tree = [{'path': 'BioCAS2022/train2022_wav/1_1_0_p1_1.wav', 'sha': 'a'},
            {'path': 'BioCAS2022/train2022_wav/2_1_0_p1_1.wav', 'sha': 'b'},
            {'path': 'BioCAS2022/train2022_wav/3_1_0_p1_1.wav', 'sha': 'c'},
            {'path': 'BioCAS2022/test2022_wav/1_1_0_p1_2.wav', 'sha': 'x'},
            {'path': 'BioCAS2022/test2022_wav/4_1_0_p1_1.wav', 'sha': 'c'}]
    selected, counts = eligible_train(tree)
    assert [item['sha'] for item in selected] == ['b']
    assert counts['exact_test_blob_conflicts'] == 1


def test_explicit_normal_combination_and_unknown_phases():
    document = {'record_annotation': 'CAS & DAS', 'event_annotation': [
        {'start': '1000', 'end': '2000', 'type': 'Normal'},
        {'start': '3000', 'end': '4000', 'type': 'Wheeze+Crackle'}]}
    events, coverage = parse_annotation(document, 5.)
    assert [e['label'] for e in events] == ['wheeze', 'crackle']
    times = np.array([.5, 1.5, 2.5, 3.5, 5.1])
    targets = np.zeros((5, 6), np.float32); targets[3, [2, 5]] = 1
    mask = acoustic_mask({'times_s': times, 'targets': targets}, coverage, CONFIG, 5.)
    assert not mask[:, :2].any()
    assert not mask[[0, 2, 4]].any()
    assert np.all(mask[[1, 3], 2:] == 1)


@pytest.mark.parametrize('document', [
    {'record_annotation': 'Poor Quality', 'event_annotation': []},
    {'record_annotation': 'Normal', 'event_annotation': []},
    {'record_annotation': 'Normal', 'event_annotation': [{'start': '-1', 'end': '100', 'type': 'Normal'}]},
    {'record_annotation': 'Normal', 'event_annotation': [{'start': '0', 'end': '100', 'type': 'disease'}]},
    {'record_annotation': 'Normal', 'event_annotation': [{'start': True, 'end': '100', 'type': 'Normal'}]},
])
def test_bad_coverage_quality_or_timestamps_do_not_become_negatives(document):
    with pytest.raises(ValueError):
        parse_annotation(document, 5.)


def test_mixed_cache_preserves_original_validation_and_masks_phases(tmp_path):
    base = tmp_path / 'base'; base.mkdir()
    cache = base / 'cache'; cache.mkdir()
    rows, records = [], []
    for i, split in enumerate(('train', 'validation')):
        name = f'base{i}.npz'
        np.savez(cache / name, features=np.ones((309, 96)), targets=np.zeros((309, 6)), mask=np.ones((309, 6)))
        rows.append({'file': name, 'split': split, 'group': str(i), 'source_sha256': str(i), 'recording_id': f'base{i}'})
        records.append({'recording_id': f'base{i}', 'split': split, 'group': str(i), 'sha256': str(i), 'normalized_pcm_sha256': str(i)})
    pd.DataFrame(rows).to_csv(cache / 'index.csv', index=False)
    pd.DataFrame(records).to_csv(base / 'recordings.csv', index=False)
    pd.DataFrame(columns=['recording_id', 'label', 'start_s', 'end_s']).to_csv(base / 'events.csv', index=False)
    (cache / 'config.json').write_text(json.dumps(CONFIG))
    audit = base / 'audit.json'
    audit.write_text(json.dumps({'test_inventory_present': True, 'near_duplicate_review_complete': True,
        'annotation_coverage_verified': True, 'observed_train_labels': CONFIG['classes']}))
    (cache / 'provenance.json').write_text(json.dumps({'audit_sha256': digest(audit), 'config_sha256': digest(cache / 'config.json'),
        'index_sha256': digest(cache / 'index.csv'), 'recordings_sha256': digest(base / 'recordings.csv'), 'events_sha256': digest(base / 'events.csv')}))
    source = tmp_path / 'source'
    (source / 'BioCAS2022/train2022_wav').mkdir(parents=True)
    (source / 'BioCAS2022/train2022_json').mkdir()
    stem = '123_1.2_0_p1_1'
    audio = source / f'BioCAS2022/train2022_wav/{stem}.wav'
    labels = source / f'BioCAS2022/train2022_json/{stem}.json'
    sf.write(audio, np.sin(np.arange(48000) * .1) * .1, 8000)
    labels.write_text(json.dumps({'record_annotation': 'Normal', 'event_annotation': [{'start': '0', 'end': '6000', 'type': 'Normal'}]}))
    (source / 'LICENSE').write_text('Attribution 4.0 International')
    (source / 'receipt.json').write_text(json.dumps({'revision': REVISION, 'official_test_labels_opened': False,
        'official_test_audio_downloaded': False, 'files': [{'path': p.relative_to(source).as_posix(), 'sha256': digest(p)}
            for p in (audio, labels, source / 'LICENSE')]}))
    before = digest(cache / 'base1.npz')
    output = tmp_path / 'mixed'
    result = build_cache(cache, audit, source, output)
    assert result['source_recordings_added'] == 1
    assert result['split_counts'] == {'train': 2, 'validation': 1}
    assert result['training_groups'] == 3
    mixed = pd.read_csv(output / 'cache/index.csv')
    assert mixed[mixed.split == 'validation'].file.tolist() == ['base1.npz']
    assert digest(output / 'cache/base1.npz') == before == digest(cache / 'base1.npz')
    for name in mixed[mixed.file.str.startswith('spr2022_')].file:
        with np.load(output / 'cache' / name) as block:
            assert not block['mask'][:, :2].any()
            assert not block['targets'].any()
            assert block['mask'][:, 2:].any()
    with pytest.raises(ValueError, match='overwrite'):
        build_cache(cache, audit, source, output)
