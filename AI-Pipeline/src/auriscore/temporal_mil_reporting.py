"""Pure reporting on locked predictions; no threshold fitting or model IO."""
import numpy as np
from sklearn.metrics import confusion_matrix,roc_auc_score,average_precision_score,f1_score,recall_score
from scipy.optimize import linear_sum_assignment


def detection(labels,probabilities,threshold:float) -> dict:
    y=np.asarray(labels); p=np.asarray(probabilities,float)
    if y.ndim!=1 or y.shape!=p.shape or set(y.tolist())!={0,1} or not np.isfinite(p).all():
        raise ValueError('Invalid locked prediction population')
    if np.any((p<0)|(p>1)) or not 0<=threshold<=1: raise ValueError('Invalid probability/threshold')
    tn,fp,fn,tp=map(int,confusion_matrix(y,p>=threshold,labels=[0,1]).ravel())
    sensitivity=tp/(tp+fn); specificity=tn/(tn+fp)
    precision=tp/(tp+fp) if tp+fp else 0.
    return dict(TN=tn,FP=fp,FN=fn,TP=tp,accuracy=(tp+tn)/len(y),sensitivity=sensitivity,
                specificity=specificity,precision=precision,F1=2*tp/(2*tp+fp+fn),
                balanced_accuracy=(sensitivity+specificity)/2,ROC_AUC=float(roc_auc_score(y,p)),
                PR_AUC=float(average_precision_score(y,p)),threshold=threshold,population=len(y),
                gate_passed=sensitivity>=.9 and fp<=120,hard_failure=sensitivity<.85)


def cardiac_phase(labels,predictions,valid) -> dict:
    y=np.asarray(labels); pred=np.asarray(predictions); mask=np.asarray(valid,bool)
    if y.shape!=pred.shape or y.shape!=mask.shape: raise ValueError('Phase shape mismatch')
    if not np.isin(y[mask],range(4)).all() or not np.isin(pred[mask],range(4)).all(): raise ValueError('Invalid phase classes')
    if not mask.any(): return dict(valid_frames=0,macro_F1=None,per_state_recall=None)
    return dict(valid_frames=int(mask.sum()),coverage=float(mask.mean()),
                macro_F1=float(f1_score(y[mask],pred[mask],labels=range(4),average='macro',zero_division=0)),
                per_state_recall=recall_score(y[mask],pred[mask],labels=range(4),average=None,zero_division=0).tolist())


def phase_boundary_errors(reference_events:list,predicted_events:list) -> dict:
    """Descriptive one-to-one minimum-distance matching by phase-transition type.

    Events are (seconds, from_state, to_state), states0..3. No tolerance is
    optimized or silently applied. Always report unmatched counts beside MAE;
    errors conditional on matched events are not an event-detection sensitivity.
    """
    arrays=[]
    for events in (reference_events,predicted_events):
        x=np.asarray(events,dtype=float).reshape(-1,3)
        if not np.isfinite(x).all() or np.any(x[:,0]<0) or not np.isin(x[:,1:],range(4)).all():
            raise ValueError('Invalid phase boundary events')
        arrays.append(x)
    ref,pred=arrays; errors=[]
    pairs=set(map(tuple,ref[:,1:]))|set(map(tuple,pred[:,1:]))
    for pair in pairs:
        a=ref[np.all(ref[:,1:]==pair,axis=1),0];b=pred[np.all(pred[:,1:]==pair,axis=1),0]
        if len(a) and len(b):
            cost=np.abs(a[:,None]-b[None,:]);i,j=linear_sum_assignment(cost)
            errors.extend(cost[i,j].tolist())
    return dict(matched=len(errors),unmatched_reference=len(ref)-len(errors),unmatched_prediction=len(pred)-len(errors),
                matched_MAE_seconds=float(np.mean(errors)) if errors else None,
                matched_median_seconds=float(np.median(errors)) if errors else None,
                tolerance_seconds=None,target='cardiac_phase_not_murmur_onset')
