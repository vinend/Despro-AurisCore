"""Build listenable development timelines selected from saved phase/sound errors."""
import argparse
import gc
import html
import json
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd
import soundfile as sf
from auriscore.acquisition_lung import digest
from auriscore.lung_alignment import review_alignment, timeline
from auriscore.lung_error_review import window_errors
from auriscore.lung_training import preflight


def review(cache: Path, audit: Path, root: Path, results: Path, analyses: Path, output: Path) -> None:
    """Recompute sampled source/cache alignment and display model/reference events."""
    if output.exists():
        raise ValueError('Fresh review directory required')
    config, index = preflight(cache, audit)
    records = pd.read_csv(audit.parent / 'recordings.csv', dtype={'group': str}).set_index('recording_id')
    lookup = index.set_index('file')
    chosen, cues = [], []
    used_groups = set()
    frames = (round(config['sample_rate'] * config['window_seconds']) - config['n_fft']) // config['hop_length'] + 1
    runs = ['EXP-L010-phase-only', 'EXP-L011-sound-only']
    for identity in runs:
        experiment = results / identity
        source = json.loads((experiment / 'source.json').read_text())
        if (source.get('evaluation_role') != 'development_only' or source.get('config') != config
                or source.get('index_sha256') != digest(cache / 'index.csv') or source.get('audit_sha256') != digest(audit)
                or json.loads((experiment / 'status.json').read_text())['status'] != 'completed'):
            raise ValueError('Completed development run bound to this cache required')
        evaluation = json.loads((experiment / 'fold-0/evaluation.json').read_text())
        order = json.loads((experiment / 'prediction_index.json').read_text())
        rows = lookup.loc[[row['file'] for row in order]]
        if not rows.split.eq('validation').all():
            raise ValueError('Only declared development validation predictions allowed')
        with np.load(experiment / 'fold-0/development_predictions.npz', allow_pickle=False) as saved:
            metrics = window_errors(saved['truth'], saved['scores'], saved['mask'], evaluation['classes'], evaluation['thresholds'], frames)
        if len(rows) != len(next(iter(metrics.values()))[0]):
            raise ValueError('Prediction order does not match window count')
        for kind, (errors, support) in metrics.items():
            grouped = pd.DataFrame({'recording_id': rows.recording_id.to_numpy(), 'errors': errors, 'support': support}).groupby('recording_id').sum()
            grouped = grouped[(grouped.support >= 50) & (grouped.errors > 0)]
            grouped['score'] = grouped.errors / grouped.support
            for device in ('steth', 'trunc'):
                candidates = grouped.loc[grouped.index.intersection(records.index[records.device == device])].sort_values(['score', 'errors'], ascending=False)
                if candidates.empty:
                    continue
                diverse = candidates.loc[[name for name in candidates.index if str(records.loc[name, 'group']) not in used_groups]]
                candidate = (diverse if not diverse.empty else candidates).iloc[0]
                name = candidate.name
                used_groups.add(str(records.loc[name, 'group']))
                if name not in chosen:
                    chosen.append(name)
                cues.append({'recording_id': name, 'device': device, 'group': str(records.loc[name, 'group']),
                             'run': identity, 'cue': kind, 'error_count': int(candidate.errors), 'valid_support': int(candidate.support),
                             'score': float(candidate.score)})
        del metrics
        gc.collect()
    output.mkdir(parents=True)
    alignment = review_alignment(cache, audit, root, output / 'alignment', recording_ids=chosen)
    pd.DataFrame(cues).to_csv(output / 'review_cases.csv', index=False)
    report = {'role': 'development_only', 'official_test_labels_opened': False, 'training_started': False,
              'source_cache_agreement': alignment['source_cache_agreement'], 'human_acoustic_review_pending': True,
              'automatic_relabeling': False, 'recordings': len(chosen), 'cues': cues,
              'selection': 'highest saved-threshold review cue per type/device; diversify date groups where possible',
              'limitations': 'Correlated overlapping windows; selection is not an unbiased error-rate estimate or proof labels are wrong.'}
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    predictions = {name: [] for name in chosen}
    for identity in runs:
        data = json.loads((analyses / f'{identity}.localization.json').read_text())
        for recording in data['recordings']:
            if recording['recording_id'] in predictions:
                predictions[recording['recording_id']].extend(recording['phase_intervals'] + recording['sound_events'])
        del data
        gc.collect()
    sections = []
    for position, item in enumerate(alignment['recordings']):
        name = item['recording_id']
        audio_path = output / 'alignment' / f'recording-{position}.wav'
        audio, rate = sf.read(audio_path)
        overlay = [{**event, 'label': 'REF ' + event['label']} for event in item['events']]
        overlay += [{**event, 'label': 'PRED ' + event['label']} for event in predictions[name]]
        labels = ['REF ' + label for label in config['classes']] + ['PRED ' + label for label in config['classes']]
        cue_names = ', '.join(cue['cue'] for cue in cues if cue['recording_id'] == name)
        sections.append(f'<section><h2>{html.escape(name)}</h2><p>{html.escape(cue_names)}</p>'
                        f'<audio controls src="alignment/recording-{position}.wav"></audio>'
                        + timeline(audio, rate, overlay, labels) + '</section>')
    (output / 'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Lung development error review</title>'
        '<style>body{font:15px sans-serif;max-width:1400px;margin:25px auto}svg{width:100%}section{margin:35px 0}</style>'
        '<h1>Reference annotations and saved model events</h1><p>Review candidates only. Do not infer label errors from model disagreement. '
        'Mechanical alignment does not verify audible annotation correctness. CC BY 4.0 HF_Lung_V1 source audio; '
        '<a href="https://doi.org/10.1371/journal.pone.0254134">source authors</a>. Official test remains closed.</p>'
        + ''.join(sections), encoding='utf-8')
    if not alignment['source_cache_agreement']:
        raise ValueError('Source/cache mismatch: resolve before training')
    print(f'Saved {len(chosen)} development review cases; source/cache agreement passed; listening review remains pending.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('cache', 'audit', 'root', 'results', 'analyses', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    review(args.cache, args.audit, args.root, args.results, args.analyses, args.output)
