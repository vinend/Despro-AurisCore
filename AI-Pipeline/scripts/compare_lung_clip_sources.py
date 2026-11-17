"""Compare two frozen Lung runs on identical development clips by source."""
import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_curve

from auriscore.lung_evaluation import frame_metrics

CLASSES = ("wheeze", "rhonchi", "crackle")


def read_run(folder: Path, arm: str):
    if json.loads((folder / "status.json").read_text())["status"] != "completed":
        raise ValueError(f"Run has not completed: {folder}")
    protocol = json.loads((folder / "protocol.json").read_text())
    if tuple(protocol["classes"]) != CLASSES:
        raise ValueError("Unexpected class order")
    index = json.loads((folder / "prediction_index.json").read_text())
    thresholds = json.loads((folder / "comparison.json").read_text())[arm]["thresholds"]
    with np.load(folder / arm / "outer_predictions.npz", allow_pickle=False) as data:
        truth, scores, mask = (data[key] for key in ("clip_truth", "clip_scores", "clip_mask"))
    return protocol, index, thresholds, truth, scores, mask


def compare(reference: Path, reference_arm: str, candidate: Path, candidate_arm: str) -> dict:
    old = read_run(reference, reference_arm)
    new = read_run(candidate, candidate_arm)
    protocol, index, _, truth, _, mask = old
    if (new[0]["clip_frames"] != protocol["clip_frames"] or new[1] != index
            or not np.array_equal(new[3], truth) or not np.array_equal(new[5], mask)):
        raise ValueError("Runs do not share the same clips, truth and annotation masks")
    sources = np.asarray([row["file"].split("_", 1)[0] for row in index])
    if len(sources) != len(truth) or set(sources) != {"steth", "trunc"}:
        raise ValueError("Expected aligned HF steth and trunc source rows")
    report = {}
    for name, rows in (("pooled", np.ones(len(index), bool)),
                       ("steth", sources == "steth"), ("trunc", sources == "trunc")):
        report[name] = {}
        for arm, run in ((reference_arm, old), (candidate_arm, new)):
            _, _, thresholds, _, scores, _ = run
            metrics = frame_metrics(truth[rows], scores[rows], mask[rows], thresholds)
            for i, item in enumerate(metrics):
                tp, tn, fp, fn = (item[k] for k in ("tp", "tn", "fp", "fn"))
                if not (tp + fn and tn + fp):
                    raise ValueError(f"Missing class support for {name}/{CLASSES[i]}")
                item["accuracy"] = (tp + tn) / (tp + tn + fp + fn)
                item["fp_rate"] = fp / (fp + tn)
                covered = mask[rows, :, i].astype(bool)
                y, p = truth[rows, :, i][covered], scores[rows, :, i][covered]
                fpr, tpr, _ = roc_curve(y, p, drop_intermediate=False)
                true_positives, false_positives = tpr * (tp + fn), fpr * (tn + fp)
                accuracy = (true_positives + tn + fp - false_positives) / len(y)
                f1 = 2 * true_positives / (tp + fn + true_positives + false_positives)
                item["diagnostic_best_joint"] = float(np.minimum(accuracy, f1).max())
            report[name][arm] = dict(zip(CLASSES, metrics))
    return {"evaluation": "development_only", "thresholds": "frozen inner validation",
            "best_joint_is_descriptive_only": True, "sources": report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("reference_arm")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("candidate_arm")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = compare(args.reference, args.reference_arm, args.candidate, args.candidate_arm)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
