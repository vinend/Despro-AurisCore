"""Review completed development runs without fitting, threshold tuning or test access."""
import argparse
import csv
import gc
import hashlib
import json
from pathlib import Path

import _bootstrap  # noqa: F401
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from auriscore.acquisition_lung import digest
from auriscore.lung_evaluation import frame_metrics
from auriscore.lung_research_queue import compare_evaluations
from auriscore.lung_training_review import early_stop_summary, masked_loss_components, weighted_loss


def array_digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def main(root: Path, output: Path) -> None:
    """Write immutable metrics/loss/score/localization analysis and a static figure."""
    if output.exists():
        raise ValueError('Use a fresh analysis directory')
    output.mkdir(parents=True)
    identities = {'L006': 'EXP-L006-temporal-cnn-context', 'L007': 'EXP-L007-lower-initial-lr',
                  'L008': 'EXP-L008-weight-decay', 'L012': 'EXP-L012-hf-sprsound-context'}
    diagnostics = {
        'L006': root / 'artifacts/lung-launch/EXP-L006-analysis-20261110/diagnostics.json',
        'L007': root / 'artifacts/lung-launch/EXP-L007-L011-20261110/queue/EXP-L007-lower-initial-lr.diagnostics.json',
        'L008': root / 'artifacts/lung-launch/EXP-L007-L011-20261110/queue/EXP-L008-weight-decay.diagnostics.json',
        'L012': root / 'artifacts/lung-launch/EXP-L012-20261110/evidence/diagnostics.json'}
    records = pd.read_csv(root / 'data/processed/lung/recordings.csv').set_index('recording_id')
    cache = json.loads((root / 'data/processed/lung/readiness.json').read_text())['cache'].replace('\\', '/')
    cache = root / cache
    provenance = json.loads((cache / 'provenance.json').read_text())
    if digest(root / 'data/processed/lung/recordings.csv') != provenance['recordings_sha256']:
        raise ValueError('Original device metadata changed after cache audit')
    index = pd.read_csv(cache / 'index.csv').set_index('file')
    result = {'role': 'development_only', 'official_test_labels_opened': False, 'training_started': False,
              'thresholds_reselected': False, 'unit': 'supervised frames including overlapping windows',
              'patient_independence_verified': False, 'runs': {}}
    baseline = None
    baseline_weights = None
    population = None
    metrics_csv = []
    histories = {}
    for tag, identity in identities.items():
        experiment = root / 'results' / identity
        if json.loads((experiment / 'status.json').read_text())['status'] != 'completed':
            raise ValueError(f'{identity} is not completed')
        source = json.loads((experiment / 'source.json').read_text())
        if source.get('evaluation_role') != 'development_only':
            raise ValueError('Only development artifacts may be reviewed')
        evaluation = json.loads((experiment / 'fold-0/evaluation.json').read_text())
        if baseline is None:
            baseline = evaluation
        metrics = compare_evaluations(baseline, evaluation)
        events = [json.loads(line) for line in (experiment / 'process.jsonl').read_text().splitlines()]
        weights_dict = next(event['positive_weights'] for event in events if event['stage'] == 'statistics_completed')
        weights = [weights_dict[name] for name in evaluation['classes']]
        if baseline_weights is None:
            baseline_weights = weights
        history = pd.read_csv(experiment / 'fold-0/history.csv')
        histories[tag] = history
        stop = early_stop_summary(history.to_dict('list'), source['config']['patience'])
        raw = np.load(experiment / 'fold-0/development_predictions.npz', allow_pickle=False)
        y, p, m = (raw[key] for key in ('truth', 'scores', 'mask'))
        raw.close()
        current_population = {'truth_sha256': array_digest(y), 'mask_sha256': array_digest(m),
                              'groups': evaluation['groups'], 'classes': evaluation['classes']}
        if population is None:
            population = current_population
        if current_population != population:
            raise ValueError('Saved truth/masks/groups/classes differ across runs')
        config = source['config']
        frames = (round(config['window_seconds'] * config['sample_rate']) - config['n_fft']) // config['hop_length'] + 1
        components = masked_loss_components(y, p, m, frames)
        own = weighted_loss(components, weights)
        common = weighted_loss(components, baseline_weights)
        order = json.loads((experiment / 'prediction_index.json').read_text())
        if len(order) != components['windows']:
            raise ValueError('Prediction order does not cover saved windows')
        scores = json.loads(diagnostics[tag].read_text())['saved_predictions']['fold-0']['summary']
        joint = scores['phase_joint']
        phase = {**joint, 'predicted_both_fraction': joint['predicted_both_positive'] / joint['jointly_valid_frames'],
                 'truth_both_fraction': joint['truth_both_positive'] / joint['jointly_valid_frames']}
        by_device = {}
        if tag in {'L006', 'L012'}:
            devices = np.array([str(records.loc[index.loc[row['file'], 'recording_id'], 'device']) for row in order])
            yy, pp, mm = (a.reshape(len(order), frames, -1) for a in (y, p, m))
            for device in sorted(set(devices)):
                selected = devices == device
                device_metrics = frame_metrics(yy[selected].reshape(-1, y.shape[1]), pp[selected].reshape(-1, y.shape[1]),
                                              mm[selected].reshape(-1, y.shape[1]), evaluation['thresholds'])
                by_device[device] = dict(zip(evaluation['classes'], device_metrics))
            del yy, pp, mm
        result['runs'][tag] = {'experiment': identity, 'early_stopping': stop, 'metrics': metrics,
            'positive_weights': weights_dict, 'reconstructed_own_weighted_loss': own,
            'loss_reconstruction_difference': own['total'] - stop['best_validation_loss'],
            'loss_under_L006_weights': common, 'phase_joint': phase,
            'score_summary': scores, 'by_device_at_saved_global_threshold': by_device,
            'artifacts_sha256': {str(path.relative_to(experiment)): digest(path) for path in
                (experiment / 'source.json', experiment / 'fold-0/evaluation.json', experiment / 'fold-0/history.csv',
                 experiment / 'fold-0/development_predictions.npz')}}
        for label, values in metrics.items():
            row = {'run': tag, 'class': label, 'threshold': values['threshold'],
                   **{key: values[key] for key in ('tn', 'fp', 'fn', 'tp', 'accuracy', 'balanced_accuracy',
                                                  'precision', 'sensitivity', 'specificity', 'f1', 'roc_auc', 'pr_auc')}}
            metrics_csv.append(row)
        del y, p, m, raw, components
        gc.collect()
        print(f'Reviewed {tag}: best epoch {stop["best_epoch"]}, own reconstructed loss {own["total"]:.6f}, common-weight loss {common["total"]:.6f}', flush=True)
    # Localization summaries are already evaluated at their frozen decoder/thresholds.
    for tag, path in [('L006', root / 'artifacts/lung-launch/EXP-L006-analysis-20261110/localization.json'),
                      ('L012', root / 'artifacts/lung-launch/EXP-L012-20261110/evidence/localization.json')]:
        localized = json.loads(path.read_text())
        result['runs'][tag]['localization'] = {'event_metrics': localized['event_metrics'],
            'boundary_tolerance_s': localized['boundary_tolerance_s'], 'postprocessing': localized['postprocessing'],
            'recordings': len(localized['recordings']), 'respiratory_values_available': sum(
                row.get('respiratory', {}).get('respiratory_rate_per_minute') is not None for row in localized['recordings'])}
        del localized
        gc.collect()
    result['population'] = population
    (output / 'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    with (output / 'metrics.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(metrics_csv[0]))
        writer.writeheader(); writer.writerows(metrics_csv)
    plt.rcParams.update({'font.size': 10})
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), layout='constrained')
    h = histories['L012']; epochs = h.epoch + 1
    axes[0, 0].plot(epochs, h.loss, marker='o', label='TRAIN')
    axes[0, 0].plot(epochs, h.val_loss, marker='o', label='Development validation')
    axes[0, 0].axvline(2, color='#28814b', linestyle='--', label='Best checkpoint: epoch 2')
    axes[0, 0].set(title='L012: loss minimum at epoch 2; stop after 8 stale epochs', xlabel='Epoch', ylabel='Run-specific weighted masked BCE')
    axes[0, 0].legend(fontsize=8)
    classes = baseline['classes']; positions = np.arange(len(classes))
    for ax, key, title in [(axes[0, 1], 'f1', 'F1 at each saved development-selected threshold'),
                           (axes[1, 0], 'pr_auc', 'PR-AUC on identical development frames')]:
        for offset, tag, color in [(-.18, 'L006', '#3b6e9b'), (.18, 'L012', '#d47b40')]:
            ax.bar(positions + offset, [result['runs'][tag]['metrics'][label][key] for label in classes], width=.35, label=tag, color=color)
        ax.set_xticks(positions, classes, rotation=25); ax.set_ylim(0, 1); ax.set_title(title)
        ax.legend()
    axes[1, 1].bar(['Reference overlap', 'L006 both phases', 'L012 both phases'],
        [result['runs']['L006']['phase_joint']['truth_both_fraction'],
         result['runs']['L006']['phase_joint']['predicted_both_fraction'],
         result['runs']['L012']['phase_joint']['predicted_both_fraction']], color=['#28814b', '#3b6e9b', '#d47b40'])
    axes[1, 1].set(title='Simultaneous phases: jointly supervised frames', ylabel='Fraction', ylim=(0, 1))
    for ax in axes.flat:
        ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    figure.suptitle('Lung L012 development review — no final-test use or threshold retuning', fontsize=14)
    figure.savefig(output / 'analysis.png', dpi=160)
    plt.close(figure)
    print(f'Saved read-only review to {output}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.root.resolve(), args.output.resolve())
