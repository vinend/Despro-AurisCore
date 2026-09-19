"""Deterministic stratified participant splitting, with hard leakage checks."""
from typing import Any
import pandas as pd
from sklearn.model_selection import train_test_split
from .validation import validate_manifest


def assert_no_leakage(frame: pd.DataFrame) -> None:
    """Fail on overlapping subjects, repeat-participant groups, recordings or hashes."""
    active = frame[frame.split.isin(["train", "validation", "test"])]
    for column in ("subject_id", "subject_group", "recording_id", "sha256"):
        if column not in active:
            raise ValueError(f"Missing leakage-check column {column}")
        nonempty = active[active[column].notna() & active[column].ne("")]
        if nonempty.groupby(column).split.nunique().gt(1).any():
            raise ValueError(f"Leakage detected for {column}")
    if active[["subject_id", "subject_group"]].isna().any().any() or active.subject_id.eq("").any() or active.subject_group.eq("").any():
        raise ValueError("Missing subject identity in assigned split")


def assign_splits(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Split linked subjects 70/15/15; exclude unknowns and conflicting visit labels."""
    validate_manifest(frame)
    result = frame.copy()
    result["split"] = "excluded"
    unusable = result.quality_flag.str.contains(r"(?:^|;)(?:invalid|silent)(?:;|$)", regex=True, na=True)
    eligible = result[result.label.isin(["Absent", "Present"]) & ~unusable]
    validate_manifest(eligible, require_subjects=True)
    conflicts = eligible.groupby("subject_group").label.nunique()
    bad_groups = conflicts[conflicts > 1].index
    result.loc[result.subject_group.isin(bad_groups), "notes"] += "; Conflicting linked-visit labels; excluded"
    eligible = eligible[~eligible.subject_group.isin(bad_groups)]
    subjects = eligible[["subject_group", "label"]].drop_duplicates().sort_values("subject_group")
    if subjects.empty or subjects.label.nunique() != 2 or subjects.label.value_counts().min() < 7:
        raise ValueError("Need at least seven independent subjects in each binary class for stratified three-way splitting")
    try:
        train, rest = train_test_split(subjects, test_size=1 - config["train_fraction"],
                                       random_state=config["seed"], stratify=subjects.label)
        validation, test = train_test_split(rest, test_size=config["test_fraction"] / (config["test_fraction"] + config["validation_fraction"]),
                                            random_state=config["seed"], stratify=rest.label)
    except ValueError as exc:
        raise ValueError(f"Cannot make stratified subject splits; add subjects or adjust fractions: {exc}") from exc
    for split, group in [("train", train), ("validation", validation), ("test", test)]:
        mask = result.index.isin(eligible.index) & result.subject_group.isin(group.subject_group)
        result.loc[mask, "split"] = split
    assert_no_leakage(result)
    return result


def split_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Counts of recording IDs, original IDs, independent groups and labels."""
    return {str(name): {"subjects": int(part.subject_group.nunique()),
                        "original_subject_ids": int(part.subject_id.nunique()),
                        "recordings": int(part.recording_id.nunique()),
                        "recording_class_counts": part.drop_duplicates("recording_id").label.value_counts().to_dict(),
                        "subject_class_counts": part.groupby("subject_group").label.agg(lambda values: "+".join(sorted(set(values)))).value_counts().to_dict()}
            for name, part in frame.groupby("split")}
