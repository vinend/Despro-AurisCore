"""Deep frozen L016-L018 review: no fitting, threshold selection or holdout access."""
import argparse
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
from auriscore.lung_training import preflight, load_block
from auriscore.lung_training_review import early_stop_summary
from auriscore.lung_deep_review import window_loss_matrix, inverse_positive_weight, merge_record_windows, conditional_auc
from auriscore.lung_evaluation import frame_metrics

RUNS = {'L016': 'EXP-L016-numerical-contract', 'L017': 'EXP-L017-window-objective',
        'L018': 'EXP-L018-supervised-windows'}


def metrics(y, p, m, thresholds, classes):
    output = frame_metrics(y, p, m, thresholds)
    for item in output:
        count = sum(item[k] for k in ('tp', 'tn', 'fp', 'fn'))
        item['accuracy'] = (item['tp']+item['tn'])/count if count else None
        item['balanced_accuracy'] = (item['sensitivity']+item['specificity'])/2 if item['sensitivity'] is not None and item['specificity'] is not None else None
        item['positive'] = item['tp']+item['fn']; item['negative'] = item['tn']+item['fp']
    return dict(zip(classes, output))


def main(root: Path, cache: Path, audit: Path, output: Path) -> None:
    if output.exists():
        raise ValueError('Fresh review directory required')
    config, index = preflight(cache, audit)
    records = pd.read_csv(audit.parent / 'recordings.csv', dtype={'group': str}).set_index('recording_id')
    events = pd.read_csv(audit.parent / 'events.csv')
    # Only audited development identities enter any statistical summary.
    development = records[records.split.isin(['train', 'validation'])]
    events = events[events.recording_id.isin(development.index)].copy()
    output.mkdir(parents=True)
    result = {'training_started': False, 'official_test_labels_opened': False,
              'thresholds_reselected': False, 'patient_independence_verified': False,
              'index_sha256': digest(cache / 'index.csv'), 'audit_sha256': digest(audit),
              'later_epoch_weights_available': False, 'runs': {}}
    population = None; common_weights = None; selected = None
    all_metrics = []; conditional_rows = []; overlap_rows = []
    queue = root / 'artifacts/lung-launch/EXP-L016-20261110/queue'
    histories = {}
    for tag, identity in RUNS.items():
        path = root / 'results' / identity
        source = json.loads((path / 'source.json').read_text())
        evaluation = json.loads((path / 'fold-0/evaluation.json').read_text())
        objective = json.loads((path / 'fold-0/objective.json').read_text())
        if (json.loads((path / 'status.json').read_text())['status'] != 'completed'
                or source['evaluation_role'] != 'development_only' or source['config'] != config
                or source['index_sha256'] != result['index_sha256'] or source['audit_sha256'] != result['audit_sha256']):
            raise ValueError('Completed bound development artifacts required')
        order = json.loads((path / 'prediction_index.json').read_text())
        if any(item['fold'] != 0 for item in order):
            raise ValueError('Single held-out development partition required')
        with np.load(path / 'fold-0/development_predictions.npz', allow_pickle=False) as saved:
            truth, scores, mask = (saved[k] for k in ('truth', 'scores', 'mask'))
        current = {'truth': hashlib.sha256(truth.tobytes()).hexdigest(), 'mask': hashlib.sha256(mask.tobytes()).hexdigest(),
                   'order': hashlib.sha256(json.dumps(order, sort_keys=True).encode()).hexdigest(),
                   'classes': evaluation['classes'], 'groups': evaluation['groups']}
        if population is None:
            population = current
            selected = index.set_index('file').loc[[item['file'] for item in order]].copy()
            if not selected.split.eq('validation').all() or selected.index.duplicated().any():
                raise ValueError('Only held-out development windows allowed')
            selected['device'] = selected.recording_id.map(records.device)
            selected['start_frame'] = [int(name.rsplit('_', 1)[1].split('.')[0]) // config['hop_length'] for name in selected.index]
        elif current != population:
            raise ValueError('Different evaluation populations/masks/order')
        weights = np.asarray(objective['positive_weights'])
        if common_weights is None:
            common_weights = weights.copy()
        classes = evaluation['classes']; frames = len(truth) // len(order)
        y, p, m = (a.reshape(len(order), frames, len(classes)) for a in (truth, scores, mask))
        loss = window_loss_matrix(y, p, m, weights)
        common = window_loss_matrix(y, p, m, common_weights)
        history = pd.read_csv(path / 'fold-0/history.csv'); histories[tag] = history
        stop = early_stop_summary(history.to_dict('list'), config['patience'])
        pipeline = json.loads((queue / (identity + '.pipeline/report.json')).read_text())
        localization = json.loads((queue / (identity + '.localization.json')).read_text())
        item = {'stopping': stop, 'weights': weights.tolist(), 'thresholds': evaluation['thresholds'],
                'hashes': {name: digest(path / name) for name in ('source.json', 'fold-0/model.keras', 'fold-0/development_predictions.npz')},
                'saved_metrics': metrics(truth, scores, mask, evaluation['thresholds'], classes),
                'best_loss_reconstructed': float(loss.mean(axis=0).sum()),
                'loss_reconstruction_difference': float(loss.mean(axis=0).sum()-stop['best_validation_loss']),
                'common_L016_weight_loss': float(common.mean(axis=0).sum()),
                'per_class_loss': dict(zip(classes, loss.mean(axis=0).sum(axis=1).tolist())),
                'positive_negative_loss': dict(zip(classes, loss.mean(axis=0).tolist())),
                'device_metrics': pipeline['stratified_validation']['device'],
                'device_only_nuisance': pipeline['TRAIN_device_only_baseline'],
                'event_metrics': localization['event_metrics'], 'loss_by_date': {}, 'reliability': {}}
        for group, positions in selected.groupby('group').indices.items():
            total = float(loss[positions].sum())
            item['loss_by_date'][str(group)] = {'windows': len(positions), 'mean_loss': total/len(positions),
                                               'share_of_total_loss': total/float(loss.sum())}
        corrected = inverse_positive_weight(scores, weights)
        for j, label in enumerate(classes):
            active = mask[:, j] > 0
            yy, pp, cc = truth[active, j], scores[active, j], corrected[active, j]
            item['reliability'][label] = {'observed_prevalence': float(yy.mean()), 'mean_raw_score': float(pp.mean()),
                'mean_inverse_weight_score': float(cc.mean()), 'raw_brier': float(np.mean((pp-yy)**2)),
                'inverse_weight_brier': float(np.mean((cc-yy)**2)),
                'positive_score_quantiles': np.quantile(pp[yy > 0], [.1, .5, .9]).tolist(),
                'negative_score_quantiles': np.quantile(pp[yy == 0], [.1, .5, .9]).tolist(),
                'interpretation': 'raw scores optimize weighted BCE, not unweighted clinical probabilities; inverse is descriptive, not validated calibration'}
            all_metrics.append({'run': tag, 'class': label, **item['saved_metrics'][label], 'threshold': evaluation['thresholds'][j]})
        # Absolute-frame overlap analysis: no new model predictions or labels.
        merged_y, merged_p, merged_m, means, device_labels = [], [], [], [], []
        for record_id, positions in selected.groupby('recording_id', sort=True).indices.items():
            record = records.loc[record_id]
            physical = (round(record.valid_end_s*config['sample_rate'])-config['n_fft']) // config['hop_length']+1
            merged = merge_record_windows(y[positions], p[positions], m[positions],
                selected.iloc[positions].start_frame.to_numpy(), physical, np.asarray(evaluation['thresholds']))
            yy, pp, mm = (merged[k] for k in ('truth', 'scores', 'mask'))
            for j, entry in enumerate(conditional_auc(yy, pp, mm)):
                conditional_rows.append({'run': tag, 'recording_id': record_id, 'device': record.device,
                    'group': str(record.group), 'class': classes[j], **entry})
                for scope, values in merged['disagreement'].items():
                    overlap_rows.append({'run': tag, 'class': classes[j], 'scope': scope,
                        **{k: values[k][j] for k in values}})
            merged_y.append(yy); merged_p.append(pp); merged_m.append(mm)
            # Audio-score-only record prior: no labels or threshold fitting.
            means.append(np.broadcast_to(pp.mean(axis=0), pp.shape))
            device_labels.extend([str(record.device)]*len(yy))
        yy, pp, mm, prior = map(np.concatenate, (merged_y, merged_p, merged_m, means))
        item['deduplicated_frame_metrics'] = metrics(yy, pp, mm, evaluation['thresholds'], classes)
        item['record_mean_score_baseline'] = metrics(yy, prior, mm, evaluation['thresholds'], classes)
        item['deduplicated_frame_count'] = len(yy)
        item['within_record_auc'] = {}
        rows = pd.DataFrame(conditional_rows); rows = rows[rows.run == tag]
        for (device, label), subset in rows.groupby(['device', 'class']):
            valid = subset[subset.roc_auc.notna()]
            item['within_record_auc'][device+'/'+label] = {'recordings': len(subset), 'mixed_label_recordings': len(valid),
                'median_auc': float(valid.roc_auc.median()) if len(valid) else None,
                'pair_weighted_auc': float(np.average(valid.roc_auc, weights=valid.positive*valid.negative)) if len(valid) else None}
        rows = pd.DataFrame(overlap_rows); rows = rows[rows.run == tag]
        item['overlap_prediction_inconsistency'] = {}
        for (label, scope), subset in rows.groupby(['class', 'scope']):
            n = int(subset.valid_repeated.sum())
            item['overlap_prediction_inconsistency'][label+'/'+scope] = {'repeated_unique_supervised_frames': n,
                'mean_probability_range': float(subset.sum_absolute_range.sum()/n) if n else None,
                'threshold_disagreement_fraction': float(subset.threshold_crossings.sum()/n) if n else None}
        result['runs'][tag] = item
        del truth, scores, mask, y, p, m, loss, common, corrected, merged_y, merged_p, merged_m, means, yy, pp, mm, prior
        gc.collect()
        print(tag + ' frozen-score review complete', flush=True)
    result['population'] = population
    result['development_support'] = {}
    for split, subset in development.groupby('split'):
        result['development_support'][split] = {'recordings': len(subset), 'date_groups': subset.group.nunique(),
            'unique_normalized_pcm': subset.normalized_pcm_sha256.nunique(),
            'annotation_events': {label: int(((events.label == label)&events.recording_id.isin(subset.index)).sum()) for label in population['classes']}}
    result['annotation_durations'] = {}
    for (split, device, label), subset in events.assign(
            split=events.recording_id.map(development.split), device=events.recording_id.map(development.device)).groupby(['split', 'device', 'label']):
        if label in population['classes']:
            result['annotation_durations']['/'.join([split, device, label])] = {'events': len(subset),
                'quantiles_seconds': np.quantile(subset.end_s-subset.start_s, [.1, .5, .9]).tolist()}
    # Fixed source-balanced sample of actual cached feature overlaps (TRAIN and validation).
    feature_rows = []; pairs = []
    for (split, device), subset in development.groupby(['split', 'device']):
        for record_id in subset.sample(n=min(32, len(subset)), random_state=42).index:
            windows = index[index.recording_id == record_id].sort_values('file', key=lambda c: c.map(lambda x: int(x.rsplit('_', 1)[1].split('.')[0])))
            if len(windows) < 2:
                continue
            a, b = windows.iloc[:2].file.tolist()
            with np.load(cache / a, allow_pickle=False) as first, np.load(cache / b, allow_pickle=False) as second:
                start_a, start_b = int(first['start_sample']), int(second['start_sample'])
                if start_a % config['hop_length'] or start_b % config['hop_length']:
                    raise ValueError('Overlap is not on shared frame grid')
                delta = (start_b-start_a)//config['hop_length']
                left = first['features'][delta:]; right = second['features'][:len(left)]
                diff = left-right; offset = float(np.median(diff))
                feature_rows.append({'recording_id': record_id, 'split': split, 'device': device,
                    'db_offset': offset, 'mean_absolute_feature_difference': float(np.mean(np.abs(diff))),
                    'residual_mean_absolute_difference': float(np.mean(np.abs(diff-offset)))})
                pairs.append({'recording_id': record_id, 'split': split, 'device': device,
                              'first_file': a, 'second_file': b, 'hop_delta': delta, 'db_offset': offset})
    pd.DataFrame(feature_rows).to_csv(output / 'feature-overlaps.csv', index=False)
    (output / 'feature-pairs.json').write_text(json.dumps(pairs, indent=2))
    result['feature_overlap_summary'] = {}
    for (split, device), rows in pd.DataFrame(feature_rows).groupby(['split', 'device']):
        offsets = rows.db_offset.abs()
        result['feature_overlap_summary'][split+'/'+device] = {'pairs': len(rows),
            'absolute_offset_quantiles_db': np.quantile(offsets, [.5, .9, 1.]).tolist(),
            'fraction_offset_over_1db': float((offsets > 1).mean()),
            'median_residual_absolute_difference': float(rows.residual_mean_absolute_difference.median())}
    pd.DataFrame(all_metrics).to_csv(output / 'metrics.csv', index=False)
    pd.DataFrame(conditional_rows).to_csv(output / 'within-record.csv', index=False)
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for tag, history in histories.items():
        axes[0].plot(history.epoch+1, history.loss, label=tag+' TRAIN')
        axes[0].plot(history.epoch+1, history.val_loss, '--', label=tag+' validation')
    axes[0].set(title='Observed objective histories', xlabel='Epoch', ylabel='Own weighted loss'); axes[0].legend(fontsize=6)
    x = np.arange(3)
    for i, (tag, item) in enumerate(result['runs'].items()):
        axes[1].bar(x+(i-1)*.24, [item['saved_metrics'][c]['pr_auc'] for c in population['classes']], .24, label=tag)
        axes[2].bar(x+(i-1)*.24, [item['device_metrics'][d]['metrics']['crackle']['roc_auc'] for d in ['steth', 'trunc']]+[item['saved_metrics']['crackle']['roc_auc']], .24, label=tag)
    axes[1].set(xticks=x, xticklabels=population['classes'], title='Same-population PR-AUC', ylim=(0, 1)); axes[1].legend()
    axes[2].set(xticks=x, xticklabels=['steth', 'trunc', 'pooled'], title='Crackle ROC-AUC by source', ylim=(0, 1)); axes[2].axhline(.5, color='gray', linestyle=':')
    fig.tight_layout(); fig.savefig(output / 'review.png', dpi=150); plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'cache', 'audit', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.cache, args.audit, args.output)
