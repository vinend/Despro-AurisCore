"""Build a private TRAIN-only transport from verified source installations, without fitting."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = 'EXP-H022-fold-local-hard-negative-contrastive-representation'
MINING = 'EXP-H021-fold-local-hard-negative-acoustic-mining'
ROLES = 'analysis/EXP-H015-heart-site-aware-mil/fold_assignments.csv'
SUPERVISION = 'analysis/EXP-H014-declared-positive-supervision/training_recording_supervision.csv'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('native','stage','audio-audit','destination'):
        parser.add_argument('--'+key, required=True, type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise FileExistsError(args.destination)
    sys.path.insert(0, str(args.native/'src'))
    import tensorflow as tf
    import numpy as np
    from auriscore.contrastive_acoustic import ContrastiveAcousticTrainer
    stage, native = args.stage, args.native
    locks = json.loads((HERE/'h022_provenance.json').read_text())['folds']
    legacy = json.loads((HERE.parents[1]/'configs/rd_logmel_temporal_mil_v1.json').read_text())['assets']
    audit_path = args.audio_audit/'recording_checks.csv'
    if sha(audit_path) != json.loads((args.audio_audit/'summary.json').read_text())['recording_checks_sha256']:
        raise ValueError('Audio provenance mismatch')
    with audit_path.open() as f:
        audit = {r['recording_id']:r for r in csv.DictReader(f)}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        def copy(src, rel, expected=None):
            dest = root/rel
            if not dest.resolve().is_relative_to(root) or dest.exists():
                raise ValueError('Unsafe or duplicate transfer member')
            if expected and sha(src) != expected:
                raise ValueError(f'Wrong source hash: {src}')
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dest)
        def historic(rel):
            return next(v for k,v in legacy.items() if k.endswith('/'+rel))
        copy(stage/ROLES,ROLES,historic(ROLES))
        copy(native/SUPERVISION,SUPERVISION)
        for name,expected in [('cnn.py','abc4111275e191e842de8f5de6123d8be399a568c9e6084ec32fade5a1fe6cba'),
                              ('spectrogram.py','3aa28c6f8cd6afd845d5b057432d54916aa2851bd201a37b3f7163223b67a769')]:
            rel='src/auriscore/'+name
            copy(stage/rel,rel,expected)
        rel='data/processed/segments.csv'
        if sha(stage/rel) != '922eae4edf4f59a6e1714751b4f4e3aecada3f75d06975c8b7eb66dd02358df3':
            raise ValueError('Source inventory changed')
        (root/rel).parent.mkdir(parents=True)
        with (stage/rel).open() as src,(root/rel).open('w',newline='') as dst:
            reader=csv.DictReader(src)
            writer=csv.DictWriter(dst,fieldnames=reader.fieldnames)
            writer.writeheader()
            seen=set()
            windows=0
            for row in reader:
                if row['split']!='train':
                    continue
                writer.writerow(row)
                windows+=1
                rid=row['recording_id']
                if rid in seen:
                    continue
                seen.add(rid)
                wave=row['processed_path']
                copy(stage/wave,wave,audit[rid]['processed_sha256'])
                tsv=Path(row['file_path']).with_suffix('.tsv')
                if (stage/tsv).is_file():
                    copy(stage/tsv,tsv)
            if seen!=set(audit) or len(seen)!=2070 or windows!=15954:
                raise ValueError('Incomplete TRAIN bundle')
        for lock in locks:
            fold=lock['fold']
            rel=f'analysis/{MINING}/hard_negative_inventory/fold_{fold}.csv'
            copy(stage/rel,rel,historic(rel))
            source=native/'results'/EXP/'folds'/f'fold-{fold}'
            dest=f'h022/fold-{fold}'
            file=source/'stage1/best_model.keras'
            if sha(file)!=lock['model_sha256']:
                raise ValueError('H022 model hash mismatch')
            original=tf.keras.models.load_model(file,compile=False).acoustic_model
            copy(source/'stage1/normalization_config.json',dest+'/normalization.json',lock['normalization_sha256'])
            plain=root/dest/'acoustic.keras'
            original.save(plain)
            restored=tf.keras.models.load_model(plain,compile=False)
            for a,b in zip(original.get_weights(),restored.get_weights(),strict=True):
                np.testing.assert_array_equal(a,b)
            for name in ('train_embeddings.csv','outer_embeddings.csv'):
                copy(source/name,dest+'/'+name,lock['outer_embeddings_sha256'] if name.startswith('outer') else None)
        manifest={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
        (root/'manifest.json').write_text(json.dumps(manifest,sort_keys=True))
        with tarfile.open(args.destination,'x') as tar:
            tar.add(root,arcname='heart-train')
        print('Archive SHA-256',sha(args.destination),'manifest SHA-256',sha(root/'manifest.json'), 'files',len(manifest),flush=True)


if __name__=='__main__':
    main()
