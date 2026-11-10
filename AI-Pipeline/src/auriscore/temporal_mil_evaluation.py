"""Frozen inner-only threshold selection; outer labels never enter selection."""
import numpy as np


def select_threshold(labels: np.ndarray, probabilities: np.ndarray, role: str) -> float:
    """Sensitivity >=.90, then specificity, precision, smaller threshold."""
    if role != 'early_stop':
        raise ValueError('Threshold selection requires original early_stop role')
    y=np.asarray(labels); p=np.asarray(probabilities,dtype=float)
    if y.shape!=p.shape or y.ndim!=1 or set(y.tolist())!={0,1} or not np.isfinite(p).all() or np.any((p<0)|(p>1)):
        raise ValueError('Invalid threshold population')
    candidates=[]
    for t in np.unique(np.r_[0.,p,1.]):
        pred=p>=t; tp=np.sum(pred & (y==1)); fp=np.sum(pred & (y==0))
        sensitivity=tp/np.sum(y==1)
        if sensitivity>=.9:
            candidates.append((float(np.sum(~pred & (y==0))/np.sum(y==0)),float(tp/max(tp+fp,1)),-float(t)))
    return -max(candidates)[2]
