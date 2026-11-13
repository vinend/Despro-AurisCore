"""Leakage-safe recording-level hard-negative selection for H021."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, train_test_split


def inner_assignments(outer_training: pd.DataFrame, outer_evaluation_ids: set[str],
                      outer_fold: int, *, seed: int = 42) -> pd.DataFrame:
    """Assign only outer-training participants to deterministic inner folds."""
    people = outer_training[["subject_group", "label"]].drop_duplicates().copy()
    people["subject_group"] = people.subject_group.astype(str)
    if people.subject_group.duplicated().any() or set(people.subject_group) & outer_evaluation_ids:
        raise ValueError("Outer-evaluation participant entered inner mining")
    people = people.sort_values("subject_group").reset_index(drop=True)
    if set(people.label) != {"Absent", "Present"}:
        raise ValueError("Both murmur classes required")
    rows = []
    split = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed + outer_fold)
    y = people.label.eq("Present").to_numpy(int)
    for inner_fold, (_, held) in enumerate(split.split(people.subject_group, y), start=1):
        rows.extend({"participant_id": str(people.subject_group.iloc[i]),
                     "inner_fold": inner_fold, "label": str(people.label.iloc[i])} for i in held)
    result = pd.DataFrame(rows)
    if len(result) != len(people) or result.participant_id.duplicated().any():
        raise ValueError("Inner cross-fitting must predict each outer-training participant once")
    return result


def inner_fit_early(people: pd.DataFrame, held_ids: set[str], outer_fold: int,
                    inner_fold: int, *, seed: int = 42) -> tuple[set[str], set[str]]:
    """Split inner-training participants for independent Stage-1 early stopping."""
    available = people.loc[~people.subject_group.astype(str).isin(held_ids), ["subject_group", "label"]].drop_duplicates()
    ids = available.subject_group.astype(str).to_numpy()
    fit, early = train_test_split(ids, test_size=.20, stratify=available.label.to_numpy(),
                                  random_state=seed + outer_fold * 10 + inner_fold)
    fit_ids, early_ids = set(fit), set(early)
    if fit_ids & held_ids or early_ids & held_ids or fit_ids & early_ids:
        raise ValueError("Inner held-out participant entered Stage-1 fit/early subset")
    return fit_ids, early_ids


def select_hard_negatives(scores: pd.DataFrame, eligible_fit_negative_ids: set[str],
                          *, fraction: float = .20) -> pd.DataFrame:
    """Rank Absent recording OOF scores; select exactly ceil(20%) of fit negatives."""
    required = {"participant_id", "recording_id", "site", "inner_fold", "true_label", "cross_fitted_score"}
    if not required.issubset(scores) or scores.recording_id.duplicated().any():
        raise ValueError("Incomplete or duplicate recording OOF scores")
    if not np.isfinite(scores.cross_fitted_score.to_numpy(float)).all() or not scores.cross_fitted_score.between(0, 1).all():
        raise ValueError("Invalid acoustic OOF scores")
    if not set(scores.true_label).issubset({"Absent", "Present"}) or fraction != .20:
        raise ValueError("H021 selection policy changed")
    available = scores.loc[scores.recording_id.isin(eligible_fit_negative_ids)].copy()
    if set(available.recording_id) != eligible_fit_negative_ids or not available.true_label.eq("Absent").all():
        raise ValueError("Mining pool must equal Stage-1 fit Absent recordings")
    rank = available.sort_values(["cross_fitted_score", "recording_id"], ascending=[False, True], kind="stable")
    selected = set(rank.head(math.ceil(len(rank) * fraction)).recording_id)
    result = scores.copy()
    result["hard_negative"] = result.recording_id.isin(selected)
    result["sample_weight"] = np.where(result.hard_negative, 2.0, 1.0)
    if result.loc[result.true_label == "Present", "hard_negative"].any() or int(result.hard_negative.sum()) != math.ceil(len(rank) * fraction):
        raise ValueError("H021 hard-negative selection invalid")
    return result

