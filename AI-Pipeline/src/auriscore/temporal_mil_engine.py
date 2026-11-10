"""Recording-MIL execution engine; scientific presence weights must be supplied.

No default experiment weights are chosen. Benchmarks may supply explicit neutral
weights, identified as engineering-only, to exercise the entire execution path.
"""
import json
from pathlib import Path
import time
import weakref
import numpy as np
import tensorflow as tf
from .logmel_temporal_mil import mil_probability
from .temporal_mil_overlap import reconstruct
from .temporal_mil_runtime import write_json,seal,save_checkpoint

from .temporal_mil_b1 import batch_step, verify_contract, bind


def materialize(data,cache,rid:str,role:str) -> dict:
    rows=data.windows(rid,role)
    phase,meta=data.phases(rid,role)
    arrays=[cache.get(r)[0] for r in rows]
    return dict(rid=rid,x=np.stack(arrays),phase=np.stack([p['labels'] for p in phase]),
        phase_valid=np.stack([p['valid'] for p in phase]),
        presence_valid=np.stack([~p['padding'] for p in phase]),seconds=np.stack([p['seconds'] for p in phase]),
        label=float(rows[0]['label']=='Present'),participant=rows[0]['subject_group'],
        duration=float(rows[0]['duration_sec']),phase_metadata=meta)


def predict_recording(model,record:dict) -> dict:
    """Inference consumes waveform geometry only; deliberately ignores phase data."""
    murmur=[]; phases=[]; scores=[]
    for start in range(0,len(record['x']),32):
        out=model(record['x'][start:start+32],training=False)
        scores.extend(mil_probability(out['murmur_logits'],record['presence_valid'][start:start+32]).numpy().tolist())
        murmur.append(tf.sigmoid(out['murmur_logits']).numpy())
        phases.append(tf.nn.softmax(out['phase_logits'],axis=-1).numpy())
    murmur=reconstruct(record['seconds'],np.concatenate(murmur),record['presence_valid'],record['duration'])
    phase=reconstruct(record['seconds'],np.concatenate(phases),record['presence_valid'],record['duration'])
    return dict(probability=float(np.mean(scores)),murmur=murmur,phase=phase)


def export_predictions(model,records:list[dict],directory:Path) -> dict:
    """Exclusive recording/frame export with equal-recording participant means."""
    directory.mkdir(parents=True,exist_ok=False)
    participants={}; recordings=[]
    for record in records:
        rid=record['rid']
        if Path(rid).name!=rid or rid in {r['recording_id'] for r in recordings}: raise ValueError('Unsafe/duplicate recording ID')
        result=predict_recording(model,record)
        with (directory/(rid+'.npz')).open('xb') as f:
            np.savez(f,seconds=result['murmur']['seconds'],murmur=result['murmur']['values'],
                phase=result['phase']['values'],coverage=result['murmur']['coverage_seconds'],
                valid=result['murmur']['valid'],bin_duration=result['murmur']['bin_duration'])
        recordings.append(dict(recording_id=rid,participant_id=record['participant'],probability=result['probability'],
                               temporal_validation='exploratory_not_validated_murmur_intervals'))
        participants.setdefault(record['participant'],[]).append(result['probability'])
    write_json(directory/'recordings.json',recordings)
    probs={p:float(np.mean(values)) for p,values in participants.items()}
    write_json(directory/'participants.json',probs); seal(directory)
    return probs


def train_fold(model,data,cache,directory:Path,fit_weights:dict,early_weights:dict,deadline:float) -> None:
    """Epoch driver. Supplied weights must cover the complete original roles.

    Not exposed by the launcher until objective binding/readiness is approved.
    The executor does not decide batching/weight semantics for the frozen study:
    explicit record groups must be bound in a subsequent authoritative resolution.
    """
    for role,binding in [('fit',fit_weights),('early_stop',early_weights)]:
        ids=data.ids(role,True)
        grouped=[rid for group in binding['groups'] for rid in group]
        if len(grouped)!=len(set(grouped)) or set(grouped)!=set(ids) or set(binding['weights'])!=set(ids):
            raise ValueError('Loss binding omits/duplicates or leaks recordings')
        verify_contract(binding.get('authoritative_resolution_sha256'))
        expected = bind(data)[role]
        if binding != expected: raise ValueError('Binding differs from authoritative fit-only materialization')
    directory.mkdir(parents=True,exist_ok=False)
    write_json(directory/'loss_binding.json',dict(fit=fit_weights,early_stop=early_weights))
    optimizer=tf.keras.optimizers.Adam(learning_rate=.0001,clipnorm=1.)
    best=float('inf'); wait=0
    history=[]
    for epoch in range(50):
        if time.monotonic()>=deadline: raise TimeoutError('Whole-run compute budget exhausted')
        fit_presence=fit_phase=fit_count=fit_frames=0.
        for group in fit_weights['epoch_groups'][epoch]:
            if time.monotonic()>=deadline: raise TimeoutError('Whole-run compute budget exhausted')
            records=[materialize(data,cache,rid,'fit') for rid in group]
            result=batch_step(model,records,np.array([fit_weights['weights'][rid] for rid in group]),optimizer)
            fit_presence+=result['presence_loss']*len(group); fit_count+=len(group)
            fit_phase+=result['phase_loss']*result['phase_frames']; fit_frames+=result['phase_frames']
        presence_sum=phase_sum=presence_weight=phase_count=0.
        for group in early_weights['groups']:
            if time.monotonic()>=deadline: raise TimeoutError('Whole-run compute budget exhausted')
            records=[materialize(data,cache,rid,'early_stop') for rid in group]
            result=batch_step(model,records,np.array([early_weights['weights'][rid] for rid in group]))
            presence_sum+=result['presence_loss']*result['presence_weight']; presence_weight+=result['presence_weight']
            phase_sum+=result['phase_loss']*result['phase_frames']; phase_count+=result['phase_frames']
        val=presence_sum/presence_weight+.2*(phase_sum/phase_count if phase_count else 0.)
        fit_loss=fit_presence/fit_count+.2*(fit_phase/fit_frames if fit_frames else 0.)
        history.append(dict(epoch=epoch+1,train_total_loss=fit_loss,validation_total_loss=val,optimizer_steps=int(optimizer.iterations)))
        print(f'{directory.name} epoch {epoch+1}/50 train={fit_loss:.5f} validation={val:.5f} patience={0 if val<best else wait+1}/8 remaining={deadline-time.monotonic():.0f}s',flush=True)
        write_json(directory/f'epoch-{epoch+1:02d}.json',history[-1])
        if val<best:
            best=val; wait=0
            checkpoint=directory/f'best-epoch-{epoch+1:02d}.keras'
            save_checkpoint(model,optimizer,checkpoint)
            write_json(directory/f'best-epoch-{epoch+1:02d}.json',dict(checkpoint=checkpoint.name,loss=best))
        else:
            wait+=1
        if wait>=8: break
    write_json(directory/'history.json',history)
    write_json(directory/'completed.json',dict(best_loss=best,epochs=len(history)))
    seal(directory)
