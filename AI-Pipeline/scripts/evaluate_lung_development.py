"""Summarize saved development predictions, never opens official test labels."""
import argparse
import json
from pathlib import Path
import numpy as np
import _bootstrap  # noqa: F401
from auriscore.lung_evaluation import frame_metrics, select_thresholds

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("Never overwrite evaluation evidence")
    source = json.loads((a.experiment / "source.json").read_text())
    predictions = []
    for file in sorted(a.experiment.glob("fold-*/development_predictions.npz")):
        with np.load(file, allow_pickle=False) as data:
            predictions.append(tuple(data[key] for key in ("truth", "scores", "mask")))
    if not predictions:
        p.error("No development predictions")
    truth, scores, mask = (np.concatenate([row[i] for row in predictions]) for i in range(3))
    thresholds = select_thresholds(truth, scores, mask)
    result = {"schema_version": "lung-development-v1", "role": "development_only", "source": source,
              "classes": source["config"]["classes"], "thresholds": thresholds,
              "metrics": frame_metrics(truth, scores, mask, thresholds), "deployment_eligible": False}
    a.output.write_text(json.dumps(result, indent=2))
