"""TRAIN-only original R1 participant roles, recording supervision and phase IO."""
import csv
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from .cardiac_phase_targets import read_intervals,targets
from .temporal_mil_cache import digest
from .temporal_mil_safety import verify_roles,verify_hash

NAME='EXP-H021-fold-local-hard-negative-acoustic-mining'


class FoldData:
    """No outer signal/target opening through development methods."""
    def __init__(self,root:Path,native:Path,spec:dict,fold:int):
        if fold not in range(1,6): raise ValueError('Invalid fold')
        self.root,self.fold=root,fold
        verify_hash(root/'src/auriscore/spectrogram.py','3aa28c6f8cd6afd845d5b057432d54916aa2851bd201a37b3f7163223b67a769')
        verify_hash(root/'src/auriscore/cnn.py','abc4111275e191e842de8f5de6123d8be399a568c9e6084ec32fade5a1fe6cba')
        for path,expected in spec['assets'].items(): verify_hash(Path(path),expected)
        rolepath=root/'analysis/EXP-H015-heart-site-aware-mil/fold_assignments.csv'
        with rolepath.open() as f: roles=list(csv.DictReader(f))
        verify_roles(roles)
        self.roles={r['participant_id']:r['role'] for r in roles if int(r['fold'])==fold}
        self.records=defaultdict(list)
        with (root/'data/processed/segments.csv').open() as f:
            for row in csv.DictReader(f):
                if row['split']!='train': continue
                if row['subject_group'] not in self.roles: raise ValueError('Unexpected TRAIN participant')
                self.records[row['recording_id']].append(row)
        if sum(map(len,self.records.values()))!=15954 or len(self.records)!=2070:
            raise ValueError('R1 TRAIN workload changed')
        self.supervision_path=native/'analysis/EXP-H014-declared-positive-supervision/training_recording_supervision.csv'
        with self.supervision_path.open() as f: audit=list(csv.DictReader(f))
        self.supervision={r['recording_id']:r for r in audit}
        if set(self.supervision)!=set(self.records) or len(audit)!=len(self.records):
            raise ValueError('Supervision inventory mismatch')
        for rid,windows in self.records.items():
            windows.sort(key=lambda r:(int(r['start_sample']),r['segment_id']))
            row=windows[0]; a=self.supervision[rid]
            expected='retained_negative' if row['label']=='Absent' else ('retained_positive' if row['auscultation_location'].upper() in {s.strip().upper() for s in a['source_murmur_locations'].split('+')} else 'ignored_ambiguous')
            if a['supervision_status']!=expected or a['subject_group']!=row['subject_group'] or a['label']!=row['label']:
                raise ValueError('Official recording supervision mismatch')
            if len({(r['subject_group'],r['label'],r['file_path']) for r in windows})!=1:
                raise ValueError('Recording identity mismatch')
        inventory=root/'analysis'/NAME/'hard_negative_inventory'/f'fold_{fold}.csv'
        with inventory.open() as f: mined=list(csv.DictReader(f))
        self.multipliers={r['recording_id']:float(r['sample_weight']) for r in mined}
        if len(mined)!=len(self.multipliers) or not set(self.multipliers.values())<={1.,2.}:
            raise ValueError('Mining multiplier mismatch')
        self.input_hashes={str(rolepath):digest(rolepath),str(self.supervision_path):digest(self.supervision_path),
                          str(root/'data/processed/segments.csv'):digest(root/'data/processed/segments.csv')}
        self.phase_cache={}

    def ids(self,role:str,supervised:bool=False) -> list[str]:
        if role not in ('fit','early_stop','outer_eval'): raise ValueError('Unknown role')
        return sorted(rid for rid,rows in self.records.items()
            if self.roles[rows[0]['subject_group']]==role and
            (not supervised or self.supervision[rid]['supervision_status']!='ignored_ambiguous'))

    def windows(self,rid:str,role:str) -> list[dict]:
        if role not in ('fit','early_stop') or rid not in self.records or self.roles[self.records[rid][0]['subject_group']]!=role:
            raise ValueError('Held-out or wrong-role development signal request')
        return self.records[rid]

    def phases(self,rid:str,role:str) -> tuple[list[dict],dict]:
        rows=self.windows(rid,role); row=rows[0]
        path=(self.root/row['file_path']).with_suffix('.tsv')
        expected=(self.root/'data/external').resolve()
        if not path.resolve().is_relative_to(expected): raise ValueError('TSV path escaped dataset')
        signature=(path.stat().st_size,path.stat().st_mtime_ns,path.stat().st_ctime_ns) if path.is_file() else None
        if rid in self.phase_cache:
            old_signature,result,meta=self.phase_cache[rid]
            if signature!=old_signature: raise ValueError('Official phase annotation changed during session')
            return result,meta
        reason=None
        try:
            intervals=read_intervals(path,float(row['duration_sec']))
            sha=digest(path)
        except (OSError,ValueError) as exc:
            intervals=np.empty((0,3)); sha=digest(path) if path.is_file() else None
            reason=type(exc).__name__+': '+str(exc)
        result=[targets(intervals,int(r['start_sample']),int(r['valid_samples'])) for r in rows]
        meta=dict(recording_id=rid,sha256=sha,phase_unavailable=reason,
                  valid_frames=sum(int(x['valid'].sum()) for x in result))
        self.phase_cache[rid]=(signature,result,meta)
        return result,meta

    def workload(self) -> dict:
        return {role:dict(recordings=len(self.ids(role,True)),
            windows=sum(len(self.records[rid]) for rid in self.ids(role,True)),
            all_recordings=len(self.ids(role)),all_windows=sum(len(self.records[rid]) for rid in self.ids(role)),
            participants=len({self.records[rid][0]['subject_group'] for rid in self.ids(role)}))
            for role in ('fit','early_stop','outer_eval')}
