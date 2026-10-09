"""Read-only H021 provenance audit and locked H022 launch preflight.

Only saved TRAIN fold assignments, Stage-1 recording supervision, and H021
inner cross-fitted mining files are opened. No OOF error identities are read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "EXP-H022-fold-local-hard-negative-contrastive-representation"
H021_NAME = "EXP-H021-fold-local-hard-negative-acoustic-mining"
H021 = ROOT / "analysis" / H021_NAME
H021_RESULTS = ROOT / "results" / H021_NAME
H022 = ROOT / "analysis" / NAME
FOLDS = ROOT / "analysis/EXP-H015-heart-site-aware-mil/fold_assignments.csv"
SUPERVISION = ROOT / "analysis/EXP-H014-declared-positive-supervision/training_recording_supervision.csv"
EXPECTED_H021_PROTOCOL = "fc288f92085ab8c0487a98bf6b36298e4c061fe9edc6049f33229fe0a5ee533c"
EXPECTED_BRANCH = "reconcile/research-master-20261009"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def truth(value: str) -> bool:
    if value not in {"True", "False"}:
        raise ValueError(f"Invalid saved boolean: {value}")
    return value == "True"


def audit_mining() -> dict:
    """Reconstruct each fit-only top-20% selection from immutable H021 files."""
    if digest(H021 / "protocol.json") != EXPECTED_H021_PROTOCOL:
        raise ValueError("H021 protocol SHA changed")
    base = read_json(H021 / "config.json")
    if digest(FOLDS) != base["fold_assignments_sha256"] or digest(SUPERVISION) != base["stage1_supervision_sha256"]:
        raise ValueError("H021 fold/supervision provenance changed")
    assignment, supervision = rows(FOLDS), rows(SUPERVISION)
    supervised = {r["recording_id"]: r for r in supervision if r["supervision_status"] == "retained_negative"}
    if len(supervised) == 0 or any(r["label"] != "Absent" for r in supervised.values()):
        raise ValueError("Absent supervision audit is invalid")
    report: dict[str, object] = {"h021_protocol_sha256": EXPECTED_H021_PROTOCOL,
        "fold_assignments_sha256": digest(FOLDS), "folds": {}}
    all_held: list[str] = []
    for fold in range(1, 6):
        fold_rows = [r for r in assignment if int(r["fold"]) == fold]
        roles = {role: {r["participant_id"] for r in fold_rows if r["role"] == role}
                 for role in ("fit", "early_stop", "outer_eval")}
        if len(fold_rows) != 568 or sum(map(len, roles.values())) != 568 or any(
                roles[a] & roles[b] for a, b in (("fit", "early_stop"), ("fit", "outer_eval"), ("early_stop", "outer_eval"))):
            raise ValueError(f"Fold {fold}: participant role leakage")
        all_held.extend(roles["outer_eval"])
        folder = H021_RESULTS / "folds" / f"fold-{fold}"
        inventory_file = H021 / "hard_negative_inventory" / f"fold_{fold}.csv"
        inventory = rows(inventory_file)
        completed = read_json(folder / "completed.json")
        if digest(inventory_file) != completed["hard_negative_inventory_sha256"]:
            raise ValueError(f"Fold {fold}: inventory hash differs from completed result")
        inner = rows(folder / "inner_assignments.csv")
        inner_by_person = {r["participant_id"]: int(r["inner_fold"]) for r in inner}
        outer_train = roles["fit"] | roles["early_stop"]
        if len(inner_by_person) != len(inner) or set(inner_by_person) != outer_train:
            raise ValueError(f"Fold {fold}: inner assignment incomplete/leaked")
        scores = []
        for i in range(1, 6):
            score_file = folder / "mining" / f"inner-{i}" / "recording_scores.csv"
            part = rows(score_file)
            if any(r["participant_id"] not in outer_train or r["participant_id"] in roles["outer_eval"]
                   or inner_by_person[r["participant_id"]] != i or int(r["inner_fold"]) != i for r in part):
                raise ValueError(f"Fold {fold} inner {i}: held score membership invalid")
            scores += part
        score_map = {r["recording_id"]: r for r in scores}
        inventory_map = {r["recording_id"]: r for r in inventory}
        if len(score_map) != len(scores) or len(inventory_map) != len(inventory) or set(score_map) != set(inventory_map):
            raise ValueError(f"Fold {fold}: missing/duplicate cross-fitted recording")
        for rid, row in inventory_map.items():
            source = score_map[rid]
            if any(row[key] != source[key] for key in ("participant_id", "site", "true_label", "segment_count", "inner_fold")):
                raise ValueError(f"Fold {fold}: score provenance differs for {rid}")
            if not math.isclose(float(row["cross_fitted_score"]), float(source["cross_fitted_score"]), abs_tol=1e-8):
                raise ValueError(f"Fold {fold}: cross-fitted score differs for {rid}")
            if row["participant_id"] not in outer_train or row["participant_id"] in roles["outer_eval"]:
                raise ValueError(f"Fold {fold}: outer-eval participant in inventory")
            if not math.isfinite(float(row["cross_fitted_score"])) or not 0 <= float(row["cross_fitted_score"]) <= 1:
                raise ValueError(f"Fold {fold}: invalid acoustic score")
            expected_weight = 2.0 if truth(row["hard_negative"]) else 1.0
            if float(row["sample_weight"]) != expected_weight or (truth(row["hard_negative"]) and row["true_label"] != "Absent"):
                raise ValueError(f"Fold {fold}: selected label/weight invalid")
        eligible = {rid for rid, rec in supervised.items() if rec["subject_group"] in roles["fit"]}
        available = [inventory_map[rid] for rid in eligible]
        if len(available) != len(eligible):
            raise ValueError(f"Fold {fold}: fit Absent recording missing")
        ranked = sorted(available, key=lambda r: (-float(r["cross_fitted_score"]), r["recording_id"]))
        selected = {r["recording_id"] for r in ranked[:math.ceil(.20 * len(ranked))]}
        actual = {r["recording_id"] for r in inventory if truth(r["hard_negative"])}
        if selected != actual or len(actual) != completed["hard_negative_count"]:
            raise ValueError(f"Fold {fold}: top-20% selection changed")
        selected_hash = hashlib.sha256(("\n".join(sorted(selected)) + "\n").encode()).hexdigest()
        report["folds"][str(fold)] = {"outer_fit_participants": len(roles["fit"]),
            "outer_early_participants": len(roles["early_stop"]),
            "outer_eval_participants": len(roles["outer_eval"]),
            "cross_fitted_recordings": len(inventory), "eligible_absent_fit_recordings": len(eligible),
            "hard_negative_count": len(selected), "selected_recording_ids_sha256": selected_hash,
            "inventory_sha256": digest(inventory_file),
            "inner_assignments_sha256": digest(folder / "inner_assignments.csv")}
    if len(all_held) != 568 or len(set(all_held)) != 568:
        raise ValueError("Outer evaluation uniqueness failed")
    return report


def verify_lock() -> dict:
    audit = audit_mining()
    protocol = read_json(H022 / "protocol.json")
    config = read_json(H022 / "config.json")
    if digest(H022 / "protocol.json") != (H022 / "protocol_sha256.txt").read_text().strip():
        raise ValueError("H022 protocol hash differs from lock")
    if digest(H022 / "config.json") != protocol["config_sha256"]:
        raise ValueError("H022 config hash differs from protocol")
    if protocol["hard_negative_provenance"] != audit:
        raise ValueError("H021 hard-negative provenance differs from H022 lock")
    if protocol["h021_protocol_sha256"] != EXPECTED_H021_PROTOCOL:
        raise ValueError("Wrong H021 parent protocol")
    if any(digest(ROOT / name) != expected for name, expected in protocol["source_sha256"].items()):
        raise ValueError("H022 training/preprocessing source differs from locked protocol")
    if digest(ROOT / "results/EXP-H014-cnn-per-frequency-augmentation-declared-positive-only/config.json") != read_json(H021 / "config.json")["stage1_base_config_sha256"]:
        raise ValueError("H014 Stage-1 config changed")
    if config["temperature"] != .10 or config["representation_loss_weight"] != .10:
        raise ValueError("H022 loss constants changed")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT.parent, text=True).strip()
    if branch != EXPECTED_BRANCH or ROOT.parent.resolve() != Path("/home/rowen/projects/Despro-AurisCore").resolve():
        raise ValueError("Wrong research checkout or branch")
    if not (ROOT / "data/processed/segments.csv").is_file():
        raise FileNotFoundError("TRAIN segment inventory missing")
    if not (ROOT / "results/EXP-H014-cnn-per-frequency-augmentation-declared-positive-only/config.json").is_file():
        raise FileNotFoundError("H014 architecture/preprocessing config missing")
    for key in ("external_validation", "sealed_test"):
        if config[key] != "closed":
            raise ValueError(f"{key} boundary changed")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["audit", "check"])
    args = parser.parse_args()
    result = audit_mining() if args.action == "audit" else verify_lock()
    print(json.dumps(result, indent=2, sort_keys=True))
