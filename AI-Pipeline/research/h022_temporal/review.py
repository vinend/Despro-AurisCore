"""Fresh-process replay and post-fit phase evaluation on sealed TRAIN outer predictions."""
import csv
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
import tensorflow as tf


from experiment import fold_data, record, LogMelCache, summarize
from auriscore.cardiac_phase_targets import read_intervals
from auriscore.temporal_mil_engine import predict_recording
from auriscore.temporal_mil_runtime import write_json, seal


def verify_result(root:Path,output:Path):
    evaluation=output.with_name(output.name+'-evaluation')
    if evaluation.exists():
        raise FileExistsError(evaluation)
    for rel,expected in json.loads((output/'manifest.json').read_text()).items():
        file=output/rel
        if not file.resolve().is_relative_to(output):
            raise ValueError('Invalid output path')
        with file.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:
                raise ValueError(f'Output integrity failed: {rel}')
    rows=[]
    confusion=np.zeros((4,4),dtype=np.int64)
    total_frames=0
    missing=0
    n_candidates=0
    max_error=0.
    evaluation.mkdir()
    with (evaluation/'exploratory_intervals.csv').open('x',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['fold','recording_id','start_seconds','end_seconds','mean_score','status'])
        for fold in range(1,6):
            tf.keras.utils.set_random_seed(42+fold)
            data=fold_data(root,fold)
            folder=output/f'fold-{fold}'
            markers=[json.loads(p.read_text()) for p in sorted(folder.glob('best-epoch-[0-9][0-9].json'))]
            best=min(markers,key=lambda r:r['loss'])
            model=tf.keras.models.load_model(folder/best['checkpoint'],compile=False)
            saved=output/f'fold-{fold}-outer_eval'
            participants={}
            fold_rows=json.loads((output/f'fold-{fold}-paired.json').read_text())
            rows.extend(fold_rows)
            with tempfile.TemporaryDirectory(dir=evaluation) as scratch:
                cache=LogMelCache(root,Path(scratch),fold,root/'h022'/f'fold-{fold}'/'normalization.json')
                for rid in data.ids('outer_eval'):
                    rec=record(data,cache,rid,'outer_eval')
                    result=predict_recording(model,rec)
                    participants.setdefault(rec['participant'],[]).append(result['probability'])
                    with np.load(saved/(rid+'.npz')) as z:
                        for key in ('murmur','phase'):
                            pred=result[key]['values']
                            np.testing.assert_allclose(pred,z[key],rtol=0,atol=1e-6,equal_nan=True)
                            max_error=max(max_error,float(np.nanmax(np.abs(pred-z[key]))))
                        seconds,valid,width=z['seconds'],z['valid'].astype(bool),z['bin_duration']
                        score=z['murmur'].reshape(-1)
                        active=valid & (score>=.5)
                        starts=np.flatnonzero(active & ~np.r_[False,active[:-1]])
                        ends=np.flatnonzero(active & ~np.r_[active[1:],False])
                        for a,b in zip(starts,ends,strict=True):
                            writer.writerow([fold,rid,seconds[a]-width[a]/2,seconds[b]+width[b]/2,
                                             np.mean(score[a:b+1]),'exploratory_not_validated_murmur_interval'])
                        n_candidates+=len(starts)
                        total_frames+=len(seconds)
                        tsv=(root/data.records[rid][0]['file_path']).with_suffix('.tsv')
                        try:
                            intervals=read_intervals(tsv,rec['duration'])
                        except (ValueError,OSError):
                            missing+=1
                            continue
                        refs=np.full(len(seconds),-1)
                        mask=valid.copy()
                        for a,b,state in intervals:
                            if state:
                                refs[(seconds>=a)&(seconds<b)]=int(state)-1
                            mask &= (np.abs(seconds-a)>.064)&(np.abs(seconds-b)>.064)
                        mask &= refs>=0
                        phase=np.nan_to_num(z['phase']).argmax(axis=-1)
                        np.add.at(confusion,(refs[mask],phase[mask]),1)
            for row in fold_rows:
                p=float(np.mean(participants[row['participant_id']]))
                max_error=max(max_error,abs(row['temporal']-p))
                if abs(row['temporal']-p)>1e-6 or (p>=row['temporal_threshold'])!=(row['temporal']>=row['temporal_threshold']):
                    raise ValueError('Participant replay changed')
            tf.keras.backend.clear_session()
    tp=confusion.diagonal()
    def safe_ratio(top,bottom):
        return np.divide(top,bottom,out=np.zeros(4),where=bottom!=0)
    if len(rows)!=568 or len({r['participant_id'] for r in rows})!=568:
        raise ValueError('Incomplete OOF inventory')
    metrics=summarize(rows)
    for key in metrics:
        if metrics[key]!=json.loads((output/'results.json').read_text())[key]:
            raise ValueError('Frozen summary changed')
    phase_f1=safe_ratio(2*tp,confusion.sum(axis=0)+confusion.sum(axis=1))
    write_json(evaluation/'report.json',dict(replay='PASS',max_abs_difference=max_error,
        matched_results=metrics,phase_confusion=confusion.tolist(),phase_states=['S1','systole','S2','diastole'],
        phase_macro_f1=float(phase_f1.mean()) if confusion.sum() else None,
        phase_recall=safe_ratio(tp,confusion.sum(axis=1)).tolist(),phase_valid_coverage=float(confusion.sum()/total_frames),
        phase_unavailable_recordings=missing,exploratory_intervals=n_candidates))
    seal(evaluation)
