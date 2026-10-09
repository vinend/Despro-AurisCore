"""TRAIN-only fold-safe acoustic representation precheck for H021."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.neighbors import NearestNeighbors

import _bootstrap  # noqa: F401
from auriscore.linear_head import FEATURES
from auriscore.oof_audit import sha256, verify_train_oof

ROOT = Path(__file__).resolve().parents[1]
H015 = ROOT / "analysis/EXP-H015-heart-site-aware-mil"
H018 = ROOT / "analysis/EXP-H018-participant-ranking-margin/postmortem"
H019 = ROOT / "analysis/EXP-H019-uniform-acoustic-pooling"
H020 = ROOT / "analysis/EXP-H020-linear-participant-head"
OUT = H020 / "representation_precheck"


def cosine(x: np.ndarray, c: np.ndarray) -> np.ndarray:
    return (x @ c) / np.maximum(np.linalg.norm(x, axis=1) * np.linalg.norm(c), 1e-12)


def main() -> None:
    if OUT.exists():
        raise FileExistsError("Representation precheck exists; refuse overwrite")
    folds = pd.read_csv(H015 / "fold_assignments.csv", dtype={"participant_id": str})
    inventory = pd.read_csv(H015 / "train_bag_inventory.csv", dtype={"participant_id": str})
    oof = pd.read_csv(H020 / "predictions_oof.csv", dtype={"participant_id": str}, float_precision="round_trip")
    verify_train_oof(oof, folds, inventory)
    threshold = json.loads((H020 / "metrics.json").read_text())["threshold"]
    h019 = pd.read_csv(H019 / "predictions_oof.csv", dtype={"participant_id": str}, float_precision="round_trip")
    verify_train_oof(h019, folds, inventory)
    h019_threshold = json.loads((H019 / "threshold_lock.json").read_text())["threshold"]
    if sha256(H020 / "protocol.json") != (H020 / "protocol_sha256.txt").read_text().strip():
        raise ValueError("H020 protocol changed")
    rec = pd.read_csv(H018 / "recording_embeddings_oof.csv", dtype={"participant_id": str, "recording_id": str})
    if len(rec) != 2070 or rec.recording_id.duplicated().any() or set(rec.participant_id) != set(inventory.participant_id):
        raise ValueError("Acoustic recording cache incomplete")
    rec = rec.merge(oof[["participant_id", "fold", "label"]], on="participant_id", suffixes=("_rec", "_oof"), validate="many_to_one")
    if not rec.fold_rec.eq(rec.fold_oof).all() or not rec.label_rec.eq(rec.label_oof).all():
        raise ValueError("Recording cache and H020 OOF fold/labels differ")
    group = np.where(oof.label.eq("Present"), np.where(oof.probability >= threshold, "TP", "FN"),
                     np.where(oof.probability >= threshold, "FP", "TN"))
    oof = oof.assign(group=group, margin=oof.probability - threshold)
    old = h019[["participant_id", "probability"]].rename(columns={"probability": "h019_probability"})
    oof = oof.merge(old, on="participant_id", validate="one_to_one")
    oof["persistent_fp_h019_h020"] = oof.group.eq("FP") & (oof.h019_probability >= h019_threshold)
    rows, recording_rows = [], []
    for fold in range(1, 6):
        train = pd.read_csv(H018 / f"probe_train_fold_{fold}.csv", dtype={"participant_id": str})
        held = pd.read_csv(H018 / f"probe_eval_fold_{fold}.csv", dtype={"participant_id": str})
        held_ids = set(folds.loc[(folds.fold == fold) & folds.role.eq("outer_eval"), "participant_id"])
        if set(held.participant_id) != held_ids or set(train.participant_id) & held_ids:
            raise ValueError("Centroid or nearest neighbor fit would leak outer-held participant")
        xtr = train.loc[:, FEATURES].to_numpy(float)
        xev = held.loc[:, FEATURES].to_numpy(float)
        with np.load(H020 / f"models/fold_{fold}_scaler_logistic.npz") as model:
            mean, scale = model["scaler_mean"], model["scaler_scale"]
            coef, intercept = model["coef"].ravel(), float(model["intercept"].item())
        ztr, zev = (xtr - mean) / scale, (xev - mean) / scale
        ytr = train.label.eq("Present").to_numpy(int)
        neg, pos = ztr[ytr == 0], ztr[ytr == 1]
        neg_c, pos_c = neg.mean(axis=0), pos.mean(axis=0)
        knn = NearestNeighbors(n_neighbors=5, metric="cosine").fit(ztr)
        neighbor_positive = ytr[knn.kneighbors(zev, return_distance=False)].mean(axis=1)
        for i, row in enumerate(held.itertuples(index=False)):
            pid = str(row.participant_id)
            rows.append({"participant_id": pid, "fold": fold,
                         "distance_to_absent_centroid": float(np.linalg.norm(zev[i] - neg_c)),
                         "distance_to_present_centroid": float(np.linalg.norm(zev[i] - pos_c)),
                         "cosine_to_absent_centroid": float(cosine(zev[i:i+1], neg_c)[0]),
                         "cosine_to_present_centroid": float(cosine(zev[i:i+1], pos_c)[0]),
                         "knn_present_fraction": float(neighbor_positive[i])})
        one_rec = rec.loc[rec.fold_rec == fold].copy()
        xr = one_rec.loc[:, FEATURES].to_numpy(float)
        zr = (xr - mean) / scale
        one_rec["recording_counterfactual_score"] = expit(zr @ coef + intercept)
        one_rec["recording_closer_present"] = np.linalg.norm(zr - pos_c, axis=1) < np.linalg.norm(zr - neg_c, axis=1)
        recording_rows.append(one_rec[["participant_id", "fold_rec", "recording_id", "site", "recording_counterfactual_score", "recording_closer_present"]])
    diag = oof.merge(pd.DataFrame(rows), on=["participant_id", "fold"], validate="one_to_one")
    rec_scores = pd.concat(recording_rows, ignore_index=True).rename(columns={"fold_rec": "fold"})
    grouped = rec_scores.groupby("participant_id").agg(
        recording_count=("recording_id", "size"),
        recording_score_min=("recording_counterfactual_score", "min"),
        recording_score_max=("recording_counterfactual_score", "max"),
        recording_score_mean=("recording_counterfactual_score", "mean"),
        recording_score_std=("recording_counterfactual_score", lambda x: float(x.std(ddof=0))),
        recording_closer_present_fraction=("recording_closer_present", "mean"),
        sites=("site", lambda x: ";".join(sorted(x))),
        recording_scores=("recording_counterfactual_score", lambda x: ";".join(f"{v:.6f}" for v in x)),
    )
    diag = diag.join(grouped, on="participant_id")
    diag["fraction_recordings_above_participant_threshold"] = rec_scores.groupby("participant_id").recording_counterfactual_score.apply(lambda x: float((x >= threshold).mean())).reindex(diag.participant_id).to_numpy()
    diag["closer_to_present_centroid"] = diag.distance_to_present_centroid < diag.distance_to_absent_centroid
    if len(diag) != 568 or diag.group.value_counts().to_dict() != {"TN": 279, "FP": 179, "TP": 99, "FN": 11}:
        raise ValueError("H020 precheck confusion matrix changed")
    site = rec_scores.merge(diag[["participant_id", "group"]], on="participant_id", validate="many_to_one")
    site_summary = site.groupby(["group", "site"]).agg(recordings=("recording_id", "size"), mean_counterfactual_score=("recording_counterfactual_score", "mean"), closer_present_fraction=("recording_closer_present", "mean")).reset_index()
    fp, tn = diag.loc[diag.group == "FP"], diag.loc[diag.group == "TN"]
    summary = {"scope": "568 TRAIN OOF participants, no validation/test access",
               "threshold": threshold, "confusion_matrix": [[279, 179], [11, 99]],
               "h020_fp": len(fp), "persistent_h019_h020_fp": int(fp.persistent_fp_h019_h020.sum()),
               "fp_closer_present_centroid": int(fp.closer_to_present_centroid.sum()),
               "fp_closer_absent_centroid": int((~fp.closer_to_present_centroid).sum()),
               "tn_closer_present_centroid": int(tn.closer_to_present_centroid.sum()),
               "fp_knn_present_fraction_mean": float(fp.knn_present_fraction.mean()),
               "tn_knn_present_fraction_mean": float(tn.knn_present_fraction.mean()),
               "fp_any_recording_above_threshold": int((fp.fraction_recordings_above_participant_threshold > 0).sum()),
               "fp_only_one_recording_above_threshold": int((fp.fraction_recordings_above_participant_threshold == 1 / fp.recording_count).sum()),
               "fp_all_recordings_above_threshold": int((fp.fraction_recordings_above_participant_threshold == 1).sum()),
               "counterfactual_note": "Recording scores come from applying H020 participant logistic classifier to individual recording embeddings; they are descriptive counterfactuals, not validated recording probabilities.",
               "centroid_note": "Each fold's centroids/neighbors are fitted on its outer-training participants only.",
               "external_validation_opened": False, "sealed_test_opened": False}
    OUT.mkdir(parents=True)
    diag.to_csv(OUT / "participant_diagnostics.csv", index=False)
    rec_scores.to_csv(OUT / "recording_diagnostics.csv", index=False)
    site_summary.to_csv(OUT / "site_summary.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (OUT / "summary.md").write_text("# H020 TRAIN-only acoustic representation precheck\n\n" +
        "Fold-safe embedding centroids and neighbors were fitted only on outer-training participants. " +
        "Individual-recording scores are counterfactual uses of the participant classifier.\n\n" +
        "```json\n" + json.dumps(summary, indent=2) + "\n```\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

