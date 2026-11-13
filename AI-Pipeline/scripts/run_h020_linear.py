"""Locked TRAIN-only H020 linear-head experiment on saved fold-local embeddings."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn import __version__ as sklearn_version
from sklearn.metrics import average_precision_score, roc_auc_score

import _bootstrap  # noqa: F401
from auriscore.linear_head import C_GRID, FEATURES, choose_c, make_classifier
from auriscore.oof_audit import best_at_sensitivity, sha256, threshold_tradeoff, verify_train_oof

ROOT = Path(__file__).resolve().parents[1]
H015 = ROOT / "analysis/EXP-H015-heart-site-aware-mil"
H018 = ROOT / "analysis/EXP-H018-participant-ranking-margin"
H019 = ROOT / "analysis/EXP-H019-uniform-acoustic-pooling"
CACHE = H018 / "postmortem"
OUT = ROOT / "analysis/EXP-H020-linear-participant-head"
EXPERIMENT = "EXP-H020-linear-participant-head"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")


def inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    assignments = pd.read_csv(H015 / "fold_assignments.csv", dtype={"participant_id": str})
    inventory = pd.read_csv(H015 / "train_bag_inventory.csv", dtype={"participant_id": str})
    p18, p19 = read(H018 / "protocol.json"), read(H019 / "protocol.json")
    if p18["stage1_sources"] != p19["stage1_sources"]:
        raise ValueError("H018/H019 frozen fold encoders differ")
    for source in p19["stage1_sources"].values():
        if sha256(ROOT / source["model_path"]) != source["model_sha256"]:
            raise ValueError("Frozen Stage-1 encoder file changed")
        if sha256(ROOT / source["normalization_path"]) != source["normalization_sha256"]:
            raise ValueError("Frozen Stage-1 normalization changed")
    for fold in range(1, 6):
        fit, held = fold_cache(fold)
        fit_ids, held_ids = set(fit.participant_id), set(held.participant_id)
        one = assignments.loc[assignments.fold == fold]
        expected_held = set(one.loc[one.role == "outer_eval", "participant_id"])
        if fit_ids != set(inventory.participant_id) - expected_held or held_ids != expected_held or fit_ids & held_ids:
            raise ValueError(f"Fold {fold} cached embeddings violate outer split")
        for table in (fit, held):
            if table.participant_id.duplicated().any() or not np.isfinite(table.loc[:, FEATURES].to_numpy(float)).all():
                raise ValueError(f"Fold {fold} has duplicate or nonfinite embeddings")
            joined = table.merge(inventory[["participant_id", "participant_label"]], on="participant_id", validate="one_to_one")
            if len(joined) != len(table) or not joined.label.eq(joined.participant_label).all():
                raise ValueError(f"Fold {fold} embedding labels changed")
    return assignments, inventory, p19


def fold_cache(fold: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = []
    for role in ("train", "eval"):
        path = CACHE / f"probe_{role}_fold_{fold}.csv"
        table = pd.read_csv(path, dtype={"participant_id": str}, float_precision="round_trip")
        if not set(FEATURES).issubset(table) or not {"participant_id", "fold", "label"}.issubset(table):
            raise ValueError(f"Invalid cached embedding schema: {path}")
        if len(table) != (568 - (114 if fold <= 3 else 113) if role == "train" else (114 if fold <= 3 else 113)):
            raise ValueError("Cached fold size changed")
        if not table.fold.eq(fold).all():
            raise ValueError("Cached fold ID changed")
        result.append(table)
    return result[0], result[1]


def prepare() -> None:
    if OUT.exists():
        raise FileExistsError("H020 output already exists")
    assignments, inventory, h19 = inputs()
    hashes = {str(fold): {role: sha256(CACHE / f"probe_{role}_fold_{fold}.csv")
                          for role in ("train", "eval")} for fold in range(1, 6)}
    protocol = {
        "experiment": EXPERIMENT, "version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "A regularized linear participant head generalizes better than H019's neural participant decision stack",
        "single_change": "Replace H019 participant head/focal+ranking training with L2 logistic classification",
        "unchanged": ["H015 exact 5 outer folds", "H016 frozen fold-local acoustic encoder", "H019 uniform mean pooling", "train participant inventory and labels", "preprocessing/normalization from fold-local Stage-1", "sensitivity-first threshold"],
        "embedding_source": str(CACHE.relative_to(ROOT)),
        "embedding_sha256_by_fold": hashes,
        "stage1_sources": h19["stage1_sources"],
        "fold_assignments_sha256": sha256(H015 / "fold_assignments.csv"),
        "train_inventory_sha256": sha256(H015 / "train_bag_inventory.csv"),
        "h019_protocol_sha256": sha256(H019 / "protocol.json"),
        "h019_postmortem_sha256": sha256(H019 / "postmortem/summary.json"),
        "encoder_retrained": False,
        "encoder_weights_reused_from_h014": False,
        "pooling": "uniform arithmetic mean of frozen recording acoustic embeddings, cached as 64d participant embedding",
        "classifier": {"library": "scikit-learn", "version": sklearn_version, "type": "LogisticRegression", "penalty": "l2", "solver": "lbfgs", "max_iter": 1000, "class_weight": "balanced", "class_weight_reason": "preserve diagnostic H018 linear-probe setup; no weighting search"},
        "scaler": "StandardScaler fit within each inner-fit split and again on outer-train only",
        "C_grid": list(C_GRID),
        "inner_cv": "5 stratified participant folds of outer-train only; seed 42+outer fold",
        "inner_selection": "max F1 at sensitivity >=0.90, then specificity, precision, smaller C; fallback max sensitivity then F1",
        "inner_limit": "cached encoder was fitted on the entire outer-train split; C selection is conditional on frozen features, not a full-pipeline nested estimate",
        "outer_cv": "one prediction per outer-held participant; exact H015 fold assignments",
        "oof_threshold": "repository best_at_sensitivity: sensitivity>=0.90, max F1, then specificity, precision",
        "master_seed": 42,
        "minimum_improvement": {"sensitivity_min": .90, "fp_below": 195, "f1_above": .4900990099},
        "strong_result": {"sensitivity_min": .90, "fp_at_most": 150},
        "external_validation_eligibility_gate": {"sensitivity_min": .90, "fp_at_most": 150, "f1_above": .4900990099, "roc_auc_min": .90, "pr_auc_min": .80},
        "external_validation": "CLOSED; not accessed in this task",
        "sealed_test": "CLOSED; not accessed in this task",
        "target": "murmur_label Absent=0 Present=1 Unknown excluded",
    }
    OUT.mkdir(parents=True)
    write(OUT / "protocol.json", protocol)
    (OUT / "protocol_sha256.txt").write_text(sha256(OUT / "protocol.json") + "\n")
    write(OUT / "config.json", {"experiment": EXPERIMENT, "protocol_sha256": sha256(OUT / "protocol.json"), "outer_folds": 5, "C_grid": list(C_GRID), "class_weight": "balanced", "feature_dim": 64})
    print("H020 protocol locked:", sha256(OUT / "protocol.json"))
    print("TRAIN participants:", len(inventory), "fold evaluation sizes:", list(assignments.loc[assignments.role == "outer_eval"].groupby("fold").size()))


def plot_curves(pred: pd.DataFrame) -> None:
    from sklearn.metrics import precision_recall_curve, roc_curve
    y = pred.label.eq("Present").to_numpy(dtype=int)
    p = pred.probability.to_numpy(float)
    for kind in ("roc", "pr"):
        fig, ax = plt.subplots(figsize=(7, 5))
        if kind == "roc":
            x, z, _ = roc_curve(y, p)
            ax.plot(x, z, label=f"H020 OOF ROC-AUC {roc_auc_score(y,p):.3f}")
            ax.plot([0, 1], [0, 1], "--", color="gray", label="Random")
            ax.set(xlabel="False positive rate", ylabel="True positive rate", title="H020 TRAIN OOF ROC")
        else:
            z, x, _ = precision_recall_curve(y, p)
            ax.plot(x, z, label=f"H020 OOF PR-AUC {average_precision_score(y,p):.3f}")
            ax.axhline(y.mean(), ls="--", color="gray", label="Class prevalence")
            ax.set(xlabel="Recall", ylabel="Precision", title="H020 TRAIN OOF precision-recall")
        ax.legend(); fig.tight_layout(); fig.savefig(OUT / ("roc_curve.png" if kind == "roc" else "pr_curve.png"), dpi=180); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 5))
    for label in ("Absent", "Present"):
        ax.hist(pred.loc[pred.label == label, "probability"], bins=25, alpha=.55, label=label)
    ax.set(xlabel="OOF probability", ylabel="Participants", title="H020 TRAIN OOF score distribution")
    ax.legend(); fig.tight_layout(); fig.savefig(OUT / "score_distribution.png", dpi=180); plt.close(fig)


def run() -> None:
    if not OUT.exists() or (OUT / "metrics.json").exists():
        raise RuntimeError("H020 protocol absent or experiment already complete")
    protocol = read(OUT / "protocol.json")
    if sha256(OUT / "protocol.json") != (OUT / "protocol_sha256.txt").read_text().strip():
        raise ValueError("Protocol lock changed")
    assignments, inventory, h19 = inputs()
    if sha256(H015 / "fold_assignments.csv") != protocol["fold_assignments_sha256"] or sha256(H015 / "train_bag_inventory.csv") != protocol["train_inventory_sha256"]:
        raise ValueError("Split provenance changed")
    if h19["stage1_sources"] != protocol["stage1_sources"]:
        raise ValueError("Frozen encoder provenance changed")
    for fold in range(1, 6):
        for role in ("train", "eval"):
            if sha256(CACHE / f"probe_{role}_fold_{fold}.csv") != protocol["embedding_sha256_by_fold"][str(fold)][role]:
                raise ValueError("Frozen embedding cache changed")
    all_pred, hp_rows, fold_rows = [], [], []
    model_dir = OUT / "models"; model_dir.mkdir(exist_ok=False)
    for fold in range(1, 6):
        train, held = fold_cache(fold)
        selected, hp = choose_c(train, 42 + fold)
        hp["outer_fold"] = fold
        hp["selected"] = hp.C.eq(selected)
        hp_rows.append(hp)
        model = make_classifier(selected, 42 + fold)
        model.fit(train.loc[:, FEATURES].to_numpy(float), train.label.eq("Present").to_numpy(int))
        scores = model.predict_proba(held.loc[:, FEATURES].to_numpy(float))[:, 1]
        if not np.isfinite(scores).all():
            raise ValueError("Nonfinite outer OOF probability")
        part = held[["participant_id", "fold", "label"]].copy(); part["probability"] = scores
        all_pred.append(part)
        y = part.label.eq("Present").to_numpy(int)
        fold_rows.append({"fold": fold, "C": selected, "n": len(part), "present": int(y.sum()),
                          "absent": int(len(y)-y.sum()), "roc_auc": float(roc_auc_score(y,scores)),
                          "pr_auc": float(average_precision_score(y,scores))})
        scaler, logistic = model.steps[0][1], model.steps[1][1]
        np.savez(model_dir / f"fold_{fold}_scaler_logistic.npz", scaler_mean=scaler.mean_, scaler_scale=scaler.scale_,
                 scaler_var=scaler.var_, coef=logistic.coef_, intercept=logistic.intercept_, classes=logistic.classes_, C=selected)
        print(f"Fold {fold}: selected C={selected:g}; outer held n={len(part)}", flush=True)
    pred = pd.concat(all_pred, ignore_index=True).sort_values(["fold", "participant_id"])
    verify_train_oof(pred, assignments, inventory)
    trade = threshold_tradeoff(pred)
    chosen = best_at_sensitivity(trade, .90)
    y = pred.label.eq("Present").to_numpy(int)
    metrics = {"experiment": EXPERIMENT, "population": "568 TRAIN participants, genuine outer OOF", **chosen,
               "roc_auc": float(roc_auc_score(y,pred.probability)),
               "pr_auc": float(average_precision_score(y,pred.probability)),
               "confusion_matrix": [[chosen["tn"], chosen["fp"]], [chosen["fn"], chosen["tp"]]],
               "protocol_sha256": sha256(OUT / "protocol.json"),
               "external_validation_opened": False, "sealed_test_opened": False}
    gate = protocol["external_validation_eligibility_gate"]
    metrics["eligible_for_external_validation"] = bool(chosen["sensitivity"] >= gate["sensitivity_min"] and chosen["fp"] <= gate["fp_at_most"] and chosen["f1"] > gate["f1_above"] and metrics["roc_auc"] >= gate["roc_auc_min"] and metrics["pr_auc"] >= gate["pr_auc_min"])
    metrics["minimum_improvement"] = bool(chosen["sensitivity"] >= .90 and chosen["fp"] < 195 and chosen["f1"] > .4900990099)
    metrics["strong_result"] = bool(chosen["sensitivity"] >= .90 and chosen["fp"] <= 150)
    metrics["very_strong_result"] = bool(chosen["sensitivity"] >= .90 and chosen["fp"] <= 136)
    metrics["final_engineering_target"] = bool(chosen["sensitivity"] >= .90 and chosen["specificity"] >= .85 and chosen["precision"] >= .65 and chosen["f1"] >= .75 and metrics["roc_auc"] >= .92 and metrics["pr_auc"] >= .85)
    pred.to_csv(OUT / "predictions_oof.csv", index=False)
    pd.concat(hp_rows).to_csv(OUT / "fold_hyperparameters.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(OUT / "fold_metrics.csv", index=False)
    trade.to_csv(OUT / "threshold_tradeoff.csv", index=False)
    compare = pd.read_csv(H019 / "h016_h017_h018_h019_comparison.csv")
    comparison_row = {column: metrics[column] for column in compare.columns if column in metrics}
    comparison_row.update(experiment="H020", recall_sensitivity=metrics["sensitivity"])
    compare = pd.concat([compare, pd.DataFrame([comparison_row])], ignore_index=True)
    compare.to_csv(OUT / "comparison_h016_h020.csv", index=False)
    plot_curves(pred)
    write(OUT / "metrics.json", metrics)
    summary = {"experiment": EXPERIMENT, "selected_C_by_fold": {str(row["fold"]): row["C"] for row in fold_rows},
               "h019_postmortem": read(H019 / "postmortem/summary.json")["transitions"], "metrics": metrics,
               "interpretation": "Simple head materially improves only if predeclared sensitivity and FP/F1 criteria hold; comparison is TRAIN OOF only.",
               "limitation": protocol["inner_limit"], "next_step": "No H021 automatically. External validation remains closed."}
    write(OUT / "summary.json", summary)
    (OUT / "summary.md").write_text("# H020 TRAIN-only result\n\n" + json.dumps(summary, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run"])
    args = parser.parse_args()
    prepare() if args.action == "prepare" else run()

