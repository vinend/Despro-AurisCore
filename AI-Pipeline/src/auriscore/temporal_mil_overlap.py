"""Recording-local duration-weighted projection onto an absolute time grid."""
import numpy as np


def reconstruct(seconds: np.ndarray, values: np.ndarray, valid: np.ndarray,
                duration: float, grid_seconds: float=.016) -> dict[str,np.ndarray]:
    """Each temporal sample covers its 128 ms bin; partial overlaps get time weight.

    Uncovered output is NaN with zero coverage, never invented confidence.
    Call once per recording. Neither labels nor TSVs are accepted.
    """
    t=np.asarray(seconds).reshape(-1); v=np.asarray(values); m=np.asarray(valid,bool).reshape(-1)
    if v.shape[:np.asarray(seconds).ndim]!=np.asarray(seconds).shape:
        raise ValueError('Temporal dimensions differ')
    v=v.reshape(len(t),-1)
    if len(m)!=len(t) or duration<=0 or grid_seconds<=0 or not np.isfinite(t).all() or not np.isfinite(v).all():
        raise ValueError('Invalid temporal input')
    edges=np.arange(int(np.ceil(duration/grid_seconds))+1)*grid_seconds
    edges[-1]=duration
    total=np.zeros((len(edges)-1,v.shape[1])); weight=np.zeros(len(edges)-1)
    for center,value in zip(t[m],v[m],strict=True):
        left=max(0.,center-.064); right=min(duration,center+.064)
        lo=max(0,int(np.floor(left/grid_seconds))); hi=min(len(weight),int(np.ceil(right/grid_seconds)))
        for j in range(lo,hi):
            w=max(0.,min(right,edges[j+1])-max(left,edges[j]))
            total[j]+=w*value; weight[j]+=w
    result=np.full_like(total,np.nan)
    np.divide(total,weight[:,None],out=result,where=weight[:,None]>0)
    return dict(seconds=(edges[:-1]+edges[1:])/2,values=result,
                coverage_seconds=weight,valid=weight>0,bin_duration=np.diff(edges))
