"""One H022-initialized Temporal MIL run, with a fit-only H022 logistic comparator."""
import json
import time
import hashlib
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from auriscore.cardiac_phase_targets import targets
from auriscore.logmel_temporal_mil import build_model
from auriscore.temporal_mil_b1 import bind, CONTRACT_SHA, verify_contract
from auriscore.temporal_mil_cache import LogMelCache
from auriscore.temporal_mil_data import FoldData
from auriscore.temporal_mil_engine import train_fold, export_predictions
from auriscore.temporal_mil_reporting import detection
from auriscore.temporal_mil_runtime import write_json, seal

FEATURES = [f'embedding_{i:02d}' for i in range(64)]


def threshold(labels, scores, role):
    """Maximize precision subject to sensitivity >=90% on early-stop participants."""
    y, p = np.asarray(labels), np.asarray(scores, dtype=float)
    if role != 'early_stop' or y.shape != p.shape or set(y) != {0, 1} or not np.isfinite(p).all() or np.any((p<0)|(p>1)):
        raise ValueError('Invalid early-stop population or scores')
    eligible = []
    for t in np.unique(np.r_[0., p]):
        pred = p >= t
        tp, fp = np.sum(pred & (y == 1)), np.sum(pred & (y == 0))
        sensitivity = tp / np.sum(y == 1)
        if sensitivity >= .90:
            eligible.append((tp/(tp+fp), -int(fp), sensitivity, float(t)))
    return max(eligible)[-1]


def fold_data(root, fold):
    # The transport manifest replaces the old absolute-path references.
    return FoldData(root, root, {'assets': {}}, fold)


def labels_for(data, role):
    return {rows[0]['subject_group']:int(rows[0]['label']=='Present')
            for rows in data.records.values() if data.roles[rows[0]['subject_group']]==role}


def embeddings(file, data, roles):
    frame=pd.read_csv(file,dtype={'participant_id':str}).set_index('participant_id')
    labels={p:y for role in roles for p,y in labels_for(data,role).items()}
    if not frame.index.is_unique or set(frame.index)!=set(labels) or not frame.fold.eq(data.fold).all():
        raise ValueError('Embedding fold/role mismatch')
    if any(frame.loc[p,'label']!=('Present' if y else 'Absent') for p,y in labels.items()):
        raise ValueError('Embedding label mismatch')
    if not np.isfinite(frame[FEATURES].values).all():
        raise ValueError('Invalid embedding')
    return frame[FEATURES]


def record(data,cache,rid,role):
    rows=data.records[rid]
    if role not in ('early_stop','outer_eval') or data.roles[rows[0]['subject_group']]!=role:
        raise ValueError('Inference role mismatch')
    geom=[targets(np.empty((0,3)),int(r['start_sample']),int(r['valid_samples'])) for r in rows]
    return dict(rid=rid,participant=rows[0]['subject_group'],duration=float(rows[0]['duration_sec']),
                x=np.stack([cache.get(r)[0] for r in rows]),presence_valid=np.stack([~g['padding'] for g in geom]),
                seconds=np.stack([g['seconds'] for g in geom]))


def train_one(root,out,fold,deadline):
    data=fold_data(root,fold)
    folder=root/'h022'/f'fold-{fold}'
    cache=LogMelCache(root,out/'cache',fold,folder/'normalization.json')
    weights=bind(data)
    model=build_model(str(folder/'acoustic.keras'),42+fold)
    output=out/f'fold-{fold}'
    train_fold(model,data,cache,output,weights['fit'],weights['early_stop'],deadline)
    markers=[json.loads(p.read_text()) for p in sorted(output.glob('best-epoch-[0-9][0-9].json'))]
    best=min(markers,key=lambda x:x['loss'])
    model=tf.keras.models.load_model(output/best['checkpoint'],compile=False)
    def infer(role):
        return export_predictions(model,(record(data,cache,rid,role) for rid in data.ids(role)),
                                  out/f'fold-{fold}-{role}')
    fit=labels_for(data,'fit')
    early=labels_for(data,'early_stop')
    table=embeddings(folder/'train_embeddings.csv',data,['fit','early_stop'])
    head=make_pipeline(StandardScaler(),LogisticRegression(C=.1,class_weight='balanced',max_iter=1000,random_state=42+fold))
    head.fit(table.loc[list(fit)],list(fit.values()))
    scaler,lr=head.steps[0][1],head.steps[1][1]
    with (out/f'fold-{fold}-comparator.npz').open('xb') as f:
        np.savez(f,mean=scaler.mean_,scale=scaler.scale_,coef=lr.coef_,intercept=lr.intercept_,classes=lr.classes_)
    early_proba=infer('early_stop')
    if set(early_proba)!=set(early):
        raise ValueError('Missing early-stop predictions')
    baseline_early=head.predict_proba(table.loc[list(early)])[:,1]
    thresholds=dict(temporal=threshold(list(early.values()),[early_proba[p] for p in early],'early_stop'),
                    baseline=threshold(list(early.values()),baseline_early,'early_stop'))
    write_json(out/f'fold-{fold}-operating-points.json',dict(thresholds=thresholds,role='early_stop',
               comparator_scores=dict(zip(early,baseline_early,strict=True))))
    temporal=infer('outer_eval')
    outer=embeddings(folder/'outer_embeddings.csv',data,['outer_eval'])
    baseline=dict(zip(outer.index,head.predict_proba(outer)[:,1],strict=True))
    labels=labels_for(data,'outer_eval')
    if set(temporal)!=set(labels) or set(baseline)!=set(labels):
        raise ValueError('Unmatched held participants')
    rows=[dict(participant_id=p,fold=fold,y=y,temporal=temporal[p],baseline=baseline[p],
               temporal_threshold=thresholds['temporal'],baseline_threshold=thresholds['baseline']) for p,y in sorted(labels.items())]
    write_json(out/f'fold-{fold}-paired.json',rows)
    tf.keras.backend.clear_session()
    return rows


def summarize(rows):
    result={}
    for key in ('baseline','temporal'):
        y=np.array([r['y'] for r in rows])
        scores=np.array([r[key] for r in rows])
        decisions=[r[key]>=r[key+'_threshold'] for r in rows]
        metrics=detection(y,decisions,.5)
        ranking=detection(y,scores,.5)
        metrics.update(ROC_AUC=ranking['ROC_AUC'],PR_AUC=ranking['PR_AUC'],threshold='per-fold early_stop')
        metrics.pop('gate_passed')
        result[key]=metrics
    return result


def run(root,out):
    verify_contract(CONTRACT_SHA)
    deadline=time.monotonic()+43200
    out.mkdir()
    here=Path(__file__).resolve().parent
    pipeline=here.parents[1]
    sources=[*here.glob('*.py'),*pipeline.glob('src/auriscore/temporal_mil_*.py'),
             pipeline/'src/auriscore/logmel_temporal_mil.py',pipeline/'src/auriscore/cardiac_phase_targets.py',
             pipeline/'configs/rd_ltmil_scientific_binding_b1.json',pipeline/'configs/rd_logmel_temporal_mil_v1.json']
    write_json(out/'provenance.json',dict(experiment='RD-H022-TMIL-P1',
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=here,text=True).strip(),
        source_sha256={str(p.relative_to(pipeline)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        input_manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
        python=platform.python_version(),libraries={n:version(n) for n in ('tensorflow','keras','numpy','scikit-learn','librosa')},
        gpu=tf.config.experimental.get_device_details(tf.config.list_physical_devices('GPU')[0]),
        protocol=(here/'README.md').read_text(),gate='precision>matched baseline AND sensitivity>=.90 AND FP<=120'))
    rows=[]
    for fold in range(1,6):
        print(f'Starting fold {fold}/5',flush=True)
        rows.extend(train_one(root,out,fold,deadline))
        print(f'Finished fold {fold}/5',flush=True)
    if len(rows)!=568 or len({r['participant_id'] for r in rows})!=568:
        raise ValueError('Duplicate or missing OOF participants')
    summary=summarize(rows)
    t,b=summary['temporal'],summary['baseline']
    summary.update(per_fold={f:summarize([r for r in rows if r['fold']==f]) for f in range(1,6)},
                   performance_gate_passed=t['precision']>b['precision'] and t['sensitivity']>=.90 and t['FP']<=120,
                   precision_target_065_reached=t['precision']>=.65,
                   scope='TRAIN development only; no model promotion or localization accuracy claim')
    write_json(out/'results.json',summary)
    seal(out)
