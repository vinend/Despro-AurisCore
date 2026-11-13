"""Explicit HF+SPRSound development run with fixed HF validation and bounded GPU."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

import _bootstrap  # noqa: F401
from auriscore.acquisition_lung import digest
from auriscore.lung_training import preflight, train
from auriscore.lung_training_policy import load_policy
from auriscore.lung_research_queue import compare_evaluations


def execute(args) -> None:
    """Freeze one source-addition experiment; no fitting without explicit authorization."""
    if not args.authorized_training:
        raise PermissionError('Explicit training authorization required')
    config, index = preflight(args.cache, args.audit)
    policy = load_policy(args.policy, config)
    source = json.loads((args.baseline / 'source.json').read_text())
    baseline = json.loads((args.baseline / 'fold-0/evaluation.json').read_text())
    provenance = json.loads((args.cache / 'provenance.json').read_text())
    audit = json.loads(args.audit.read_text())
    if (source['config'] != config or provenance.get('base_index_sha256') != source['index_sha256']
            or sorted(index.loc[index.split == 'validation', 'group'].unique()) != sorted(baseline['groups'])
            or audit.get('official_test_labels_opened') is not False):
        raise ValueError('Original HF validation and audited source-addition provenance required')
    # Verify that the validation filenames/order/group/source identities match the control.
    order = json.loads((args.baseline / 'prediction_index.json').read_text())
    validation = index[index.split == 'validation']
    if [(r.file, str(r.group)) for r in validation.itertuples()] != [(r['file'], str(r['group'])) for r in order]:
        raise ValueError('HF validation population/order changed')
    if args.output.exists() or args.evidence.exists():
        raise ValueError('Fresh output and evidence paths required')
    args.evidence.mkdir(parents=True)
    pipeline = Path(__file__).resolve().parents[1]
    inventory = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
    (args.evidence / 'pip-freeze.txt').write_text(inventory)
    protocol = {'schema_version': 'lung-source-addition-v1', 'experiment_id': args.output.name,
        'runtime': {'python': sys.version, 'pip_freeze_sha256': digest(args.evidence / 'pip-freeze.txt')},
        'role': 'development_only', 'baseline': args.baseline.name,
        'change': 'Add audited patient-disjoint SPRSound 2022 TRAIN acoustic supervision; original HF validation unchanged',
        'config': config, 'training_policy': policy, 'audit_sha256': digest(args.audit),
        'index_sha256': digest(args.cache / 'index.csv'), 'provenance': provenance,
        'early_stopping': {'monitor': 'val_loss', 'patience': config['patience'], 'restore_best_weights': True},
        'threshold_rule': 'maximum-F1 per class, 37-point 0.05..0.95 development grid; lowest tie',
        'localization': {'version': 'lung-frame-events-v2', 'minimum_s': 0, 'merge_gap_s': 0, 'boundary_tolerance_s': .1},
        'source_counts': {k: v for k, v in audit.items() if k.startswith('source_')},
        'compute': {'require_gpu': True, 'gpu_memory_mb': args.gpu_memory_mb,
                    'concurrent_runs_permitted': True, 'latency_comparison_valid': False,
                    'reason': 'User requests fast launch while prior independent GPU queue continues; memory bounded'},
        'annotation_assumptions': 'Acoustic taxonomy exhaustive only in explicitly categorized SPR events; missing I/E and unannotated audio masked',
        'independent_patient_validation': False, 'deployment_eligible': False, 'official_test_labels_opened': False,
        'code_sha256': {str(p.relative_to(pipeline)): digest(p) for pattern in ('src/**/*.py', 'scripts/*.py', 'configs/*')
                        for p in sorted(pipeline.glob(pattern)) if p.is_file()}}
    (args.evidence / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    status = {'status': 'waiting_for_gpu', 'experiment_id': args.output.name}

    def save():
        status['updated_utc'] = datetime.now(timezone.utc).isoformat()
        (args.evidence / 'status.json').write_text(json.dumps(status, indent=2))

    save()
    try:
        import tensorflow as tf
        devices = tf.config.list_physical_devices('GPU')
        if not devices:
            raise RuntimeError('GPU required; CPU fallback refused')
        deadline = time.monotonic() + 3600
        while True:
            free = int(subprocess.check_output(['nvidia-smi', '--id=0', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True).strip())
            if free >= args.gpu_memory_mb + 512:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Insufficient free GPU memory within the declared wait window')
            time.sleep(30)
        tf.config.set_logical_device_configuration(devices[0], [tf.config.LogicalDeviceConfiguration(memory_limit=args.gpu_memory_mb)])
        status['status'] = 'training'
        save()
        train(args.cache, args.audit, args.output, authorized=True, training_policy=args.policy)
        tf.keras.backend.clear_session()
        status['status'] = 'development_analysis'
        save()
        for script, suffix in (('diagnose_lung_development.py', 'diagnostics'), ('evaluate_lung_localization.py', 'localization')):
            subprocess.run([sys.executable, str(pipeline / 'scripts' / script), '--cache', str(args.cache),
                '--audit', str(args.audit), '--experiment', str(args.output), '--output', str(args.evidence / f'{suffix}.json')], check=True)
        evaluation = json.loads((args.output / 'fold-0/evaluation.json').read_text())
        (args.evidence / 'comparison.json').write_text(json.dumps({'baseline': args.baseline.name,
            'unit': 'unchanged HF supervised validation frames including overlapping windows',
            'metrics': compare_evaluations(baseline, evaluation), 'deployment_eligible': False}, indent=2))
        status['status'] = 'completed'
    except BaseException as error:
        status.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('cache', 'audit', 'policy', 'baseline', 'output', 'evidence'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--gpu-memory-mb', type=int, default=3072)
    parser.add_argument('--authorized-training', action='store_true')
    args = parser.parse_args()
    if not 2048 <= args.gpu_memory_mb <= 4096:
        parser.error('Use a bounded GPU allocation of 2048..4096 MiB')
    for key in ('cache', 'audit', 'policy', 'baseline', 'output', 'evidence'):
        setattr(args, key, getattr(args, key).resolve())
    execute(args)
