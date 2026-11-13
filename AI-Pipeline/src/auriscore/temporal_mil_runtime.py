"""Exclusive artifacts and process-tree deadlines for isolated research work."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import numpy as np


def write_json(path: Path, value: object) -> None:
    """Exclusive creation: never replace an earlier research artifact."""
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)


def seal(directory: Path) -> None:
    """Write a content inventory once; completion markers are never overwritten."""
    hashes={str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob('*')) if p.is_file()}
    write_json(directory/'manifest.json',hashes)


def save_checkpoint(model,optimizer,path:Path) -> None:
    """Exclusive model plus complete ordered optimizer arrays and variable paths."""
    state=path.with_suffix('.optimizer.npz'); meta=path.with_suffix('.optimizer.json')
    if path.exists() or state.exists() or meta.exists(): raise FileExistsError(path)
    with path.with_suffix('.claim').open('x') as claim: claim.write('single writer')
    model.save(path)
    variables=list(optimizer.variables)
    with state.open('xb') as f: np.savez(f,**{f'var_{i:03d}':v.numpy() for i,v in enumerate(variables)})
    write_json(meta,[dict(key=f'var_{i:03d}',path=getattr(v,'path',v.name),shape=list(v.shape)) for i,v in enumerate(variables)])


def supervise(command: list[str], output: Path, seconds: float=43200) -> int:
    """POSIX supervisor kills the complete worker process group at deadline."""
    if os.name!='posix' or not 0<seconds<=43200:
        raise ValueError('Deadline must be positive and <=12 hours; POSIX groups required')
    output.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    with (output/'worker.log').open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write_json(output/'launch.json',dict(pid=process.pid,command=command,budget_seconds=seconds))
        timeout=False
        try:
            code=process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timeout=True
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(); code=124
        write_json(output/'exit.json',dict(code=code,timeout=timeout,seconds=time.monotonic()-start))
    seal(output)
    return code
