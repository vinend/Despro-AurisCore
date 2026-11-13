"""Frozen B1 coefficients, schedules and complete-recording gradient execution."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import weakref
import numpy as np
import tensorflow as tf
from .logmel_temporal_mil import mil_probability

CONTRACT_SHA = '9b500cbcb65a9463c8963f6012ab7b1a87f4755fa110378fed8f3c6acd246c82'
ROOT = Path(__file__).resolve().parents[2]


def verify_contract(value):
    path = ROOT/'configs/rd_ltmil_scientific_binding_b1.json'
    if value != CONTRACT_SHA or hashlib.sha256(path.read_bytes()).hexdigest() != CONTRACT_SHA:
        raise ValueError('Invalid/missing frozen B1 contract hash')
    spec = ROOT/'configs/rd_logmel_temporal_mil_v1.json'
    if hashlib.sha256(spec.read_bytes()).hexdigest() != json.loads(path.read_text())['base_spec_sha256']:
        raise ValueError('Parent specification changed')


def schedules(ids, fold, role):
    result = []
    for epoch in range(1, 51 if role == 'fit' else 2):
        def key(rid):
            s=f'RD-LTMIL-01-v1-B1|fold={fold}|epoch={epoch}|seed={42+fold}|recording={rid}'
            return hashlib.sha256(s.encode()).hexdigest(), rid
        order=sorted(ids,key=key) if role=='fit' else sorted(ids)
        result.append([order[i:i+32] for i in range(0,len(order),32)])
    return result


def bind(data):
    """Read only fit/early-stop metadata; preserve all original multipliers."""
    verify_contract(CONTRACT_SHA)
    fit=data.ids('fit',True)
    labels={data.windows(r,'fit')[0]['subject_group']:data.windows(r,'fit')[0]['label'] for r in fit}
    counts=Counter(labels.values())
    if set(counts)!={'Absent','Present'}: raise ValueError('Missing fit class')
    factors={c:len(labels)/(2*n) for c,n in counts.items()}
    result={}
    for role in ('fit','early_stop'):
        ids=data.ids(role,True); windows={r:data.windows(r,role) for r in ids}
        participant_labels={}
        totals=Counter()
        for r,rows in windows.items():
            p=rows[0]['subject_group']; y=rows[0]['label']
            if p in participant_labels and participant_labels[p]!=y: raise ValueError('Mixed labels')
            participant_labels[p]=y; totals[p]+=len(rows)
        expected={p for p,v in data.roles.items() if v==role}
        if set(totals)!=expected: raise ValueError('Participant lost or leaked')
        if role=='fit':
            if not set(ids)<=set(data.multipliers): raise ValueError('Mining inventory coverage')
            if any(m==2 and (r not in data.records or data.roles[data.records[r][0]['subject_group']]!='fit') for r,m in data.multipliers.items()):
                raise ValueError('Mining outside fit')
        weights={}; records=[]
        for r,rows in windows.items():
            p=rows[0]['subject_group']; y=rows[0]['label']; m=data.multipliers[r] if role=='fit' else 1.
            if m not in (1.,2.): raise ValueError('Mining multiplier')
            share=len(rows)/totals[p]; weight=len(ids)/len(totals)*factors[y]*share*m
            weights[r]=weight
            records.append(dict(recording_id=r,participant_id=p,official_label=y,window_count=len(rows),
                participant_window_count=totals[p],class_factor=factors[y],recording_share=share,
                mining_multiplier=m,recording_coefficient=weight))
        groups=schedules(ids,data.fold,role)
        result[role]=dict(authoritative_resolution_sha256=CONTRACT_SHA,weights=weights,groups=groups[0],
            epoch_groups=groups,group_hashes=[hashlib.sha256(json.dumps(g,separators=(',',':')).encode()).hexdigest() for g in groups],
            records=records,fit_class_factors=factors,fit_class_counts=dict(counts),input_hashes=data.input_hashes)
    return result


def record_terms(model,x,valid,targets,mask,training):
    murmur=tf.TensorArray(tf.float32,size=0,dynamic_size=True,infer_shape=False)
    phase=tf.TensorArray(tf.float32,size=0,dynamic_size=True,infer_shape=False)
    for i in tf.range((tf.shape(x)[0]+31)//32):
        out=model(x[i*32:(i+1)*32],training=training)
        murmur=murmur.write(i,out['murmur_logits']);phase=phase.write(i,out['phase_logits'])
    tf.debugging.assert_positive(tf.reduce_sum(tf.cast(valid,tf.int32),axis=1))
    p=tf.reduce_mean(mil_probability(murmur.concat(),valid))
    ce=tf.nn.sparse_softmax_cross_entropy_with_logits(labels=tf.where(mask,targets,0),logits=phase.concat())
    return p,tf.reduce_sum(tf.where(mask,ce,0.))


_POOL=weakref.WeakKeyDictionary()
def executor(model, training):
    pool=_POOL.setdefault(model,{})
    if training in pool: return pool[training]
    @tf.function(input_signature=[tf.TensorSpec([None,40,313,1],tf.float32),
        tf.TensorSpec([None,39],tf.bool),tf.TensorSpec([None,39],tf.int32),tf.TensorSpec([None,39],tf.bool),
        tf.TensorSpec([],tf.float32),tf.TensorSpec([],tf.float32),tf.TensorSpec([],tf.float32),tf.TensorSpec([],tf.float32)])
    def run(x,valid,targets,mask,y,w,b,k):
        with tf.GradientTape() as tape:
            p,phase=record_terms(model,x,valid,targets,mask,training)
            safe=tf.clip_by_value(p,1e-7,1-1e-7)
            presence=w*(-y*tf.math.log(safe)-(1-y)*tf.math.log(1-safe))/b
            phase=tf.math.divide_no_nan(phase,k)
            loss=presence+.2*phase
        tf.debugging.assert_all_finite(loss,'Invalid loss')
        if training:
            grads=tape.gradient(loss,model.trainable_variables)
            for g in grads:
                if g is None: raise ValueError('Disconnected gradient')
                tf.debugging.assert_all_finite(g,'Invalid gradient')
        else: grads=[]
        return presence,phase,p,grads
    pool[training]=run
    return run


def gradients(model,records,weights,training=True):
    if not records or len(records)>32 or len(weights)!=len(records) or not np.isfinite(weights).all() or np.any(np.asarray(weights)<=0):
        raise ValueError('Invalid recording group/coefficients')
    count=sum(int(r['phase_valid'].sum()) for r in records)
    accumulated=[tf.zeros_like(v) for v in model.trainable_variables] if training else []
    presence=phase=0.; probs=[]
    run=executor(model,training)
    for r,w in zip(records,weights):
        a,b,p,gs=run(np.asarray(r['x'],np.float32),r['presence_valid'],np.asarray(r['phase'],np.int32),r['phase_valid'],
            np.float32(r['label']),np.float32(w),np.float32(len(records)),np.float32(count))
        accumulated=[x+g for x,g in zip(accumulated,gs)]
        presence+=float(a);phase+=float(b);probs.append(float(p))
    return dict(loss=presence+.2*phase,presence_loss=presence,phase_loss=phase,
        presence_weight=len(records),phase_frames=count,probabilities=probs),accumulated


def batch_step(model,records,presence_weights,optimizer=None):
    result,gs=gradients(model,records,presence_weights,optimizer is not None)
    if optimizer is not None: optimizer.apply_gradients(zip(gs,model.trainable_variables))
    return result
