"""Immutable fold-local log-mel cache, independent of labels and phase targets."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from collections import OrderedDict
import numpy as np


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''): h.update(chunk)
    return h.hexdigest()


class LogMelCache:
    """Keys bind waveform bytes, window geometry, fold, norm and exact extractor."""
    def __init__(self, root: Path, cache: Path, fold: int, norm: Path):
        if fold not in range(1,6): raise ValueError('Invalid fold')
        self.root,self.cache,self.fold=root,cache,fold
        self.config=json.loads(norm.read_text())
        self.norm_sha=digest(norm)
        source=root/'src/auriscore/spectrogram.py'
        self.source_sha=digest(source)
        spec=importlib.util.spec_from_file_location('recovered_r1_spectrogram',source)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.extract=module.extract_spectrogram_tensor
        self.waveforms={}
        self.wave_signatures={}
        self.verified_tensors=OrderedDict()

    def get(self, row: dict) -> tuple[np.ndarray,str]:
        if row['split']!='train': raise ValueError('Cache accepts TRAIN only')
        path=(self.root/row['processed_path']).resolve()
        if not path.is_relative_to((self.root/'data/processed/audio').resolve()):
            raise ValueError('Waveform escaped approved audio root')
        if path not in self.waveforms:
            # Read/hash once, then keep a read-only memory map for this process.
            self.waveforms[path]=(digest(path),np.load(path,mmap_mode='r',allow_pickle=False))
            info=path.stat(); self.wave_signatures[path]=(info.st_size,info.st_mtime_ns,info.st_ctime_ns)
        info=path.stat()
        if (info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=self.wave_signatures[path]:
            raise ValueError('Source waveform changed during cache session')
        wave_sha,wave=self.waveforms[path]
        start,valid,size=[int(row[k]) for k in ('start_sample','valid_samples','window_samples')]
        if size!=40000 or valid<=0 or start<0 or start+valid>len(wave) or valid>size:
            raise ValueError('Invalid waveform window')
        identity=dict(fold=self.fold,norm=self.norm_sha,source=self.source_sha,waveform=wave_sha,
                      start=start,valid=valid,size=size)
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        folder=self.cache/f'fold-{self.fold}'/key
        if key in self.verified_tensors:
            tensor,signature=self.verified_tensors[key]
            p=folder/'tensor.npy'; meta=folder/'manifest.json'
            if (p.stat().st_mtime_ns,p.stat().st_size,meta.stat().st_mtime_ns,meta.stat().st_size)!=signature:
                raise ValueError('Verified cache entry changed during session')
            self.verified_tensors.move_to_end(key)
            return tensor,key
        if folder.exists():
            meta=json.loads((folder/'manifest.json').read_text())
            if meta['identity']!=identity or digest(folder/'tensor.npy')!=meta['tensor_sha256']:
                raise ValueError('Cache corruption')
        else:
            folder.parent.mkdir(parents=True,exist_ok=True)
            tmp=Path(tempfile.mkdtemp(prefix='.pending-',dir=folder.parent))
            tensor=self.extract(np.pad(wave[start:start+valid],(0,size-valid)),self.config)[...,None]
            if tensor.shape!=(40,313,1) or not np.isfinite(tensor).all(): raise ValueError('Bad tensor')
            np.save(tmp/'tensor.npy',tensor,allow_pickle=False)
            (tmp/'manifest.json').write_text(json.dumps(dict(identity=identity,tensor_sha256=digest(tmp/'tensor.npy')),sort_keys=True))
            # Atomic publish; never replace another complete cache entry.
            os.rename(tmp,folder)
        tensor=np.load(folder/'tensor.npy',mmap_mode='r',allow_pickle=False)
        p=folder/'tensor.npy'; meta=folder/'manifest.json'
        signature=(p.stat().st_mtime_ns,p.stat().st_size,meta.stat().st_mtime_ns,meta.stat().st_size)
        self.verified_tensors[key]=(tensor,signature)
        if len(self.verified_tensors)>256: self.verified_tensors.popitem(last=False)
        return tensor,key

    def verify_equality(self,row:dict) -> None:
        cached,_=self.get(row)
        wave=self.waveforms[(self.root/row['processed_path']).resolve()][1]
        a,n,size=[int(row[k]) for k in ('start_sample','valid_samples','window_samples')]
        actual=self.extract(np.pad(wave[a:a+n],(0,size-n)),self.config)[...,None]
        np.testing.assert_array_equal(cached,actual)
