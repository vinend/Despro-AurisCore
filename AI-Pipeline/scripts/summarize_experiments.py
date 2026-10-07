"""Print completed validation results and regenerate the comparison figure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.experiment_queue import is_completed
from auriscore.visualization import summarize_best, update_comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", help="Optional existing baseline EXP-H... directory")
    parser.add_argument("--best", help="Optional existing best EXP-H... directory")
    parser.add_argument("--pattern", default="EXP-*", help="Glob pattern for experiment folders (e.g. EXP-A*, EXP-H*, EXP-*)")
    args = parser.parse_args()
    if bool(args.baseline) != bool(args.best):
        parser.error("--baseline and --best must be provided together")
    root = args.root.resolve()
    fields = (
        ("accuracy", "Accuracy"), ("precision", "Precision"),
        ("recall_sensitivity", "Recall"), ("specificity", "Specificity"),
        ("f1", "F1"), ("balanced_accuracy", "Balanced Acc"),
        ("roc_auc", "ROC-AUC"), ("pr_auc", "PR-AUC"),
    )
    try:
        patterns = [args.pattern] if args.pattern != "EXP-*" else ["EXP-H*", "EXP-A*"]
        for pat in patterns:
            directories = [directory for directory in sorted((root / "results").glob(pat))
                           if directory.is_dir() and is_completed(directory)]
            if not directories:
                continue
            domain = "Abdomen" if "EXP-A" in pat else "Heart"
            print(f"\n=== {domain} Completed Experiments ({len(directories)}) ===")
            print(f"{'Experiment':39} " + " ".join(f"{label:>12}" for _, label in fields) + f" {'Best Epoch':>10} {'Val Loss':>10}")
            for directory in directories:
                data = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
                metrics_source = data["validation"].get("recording") if "EXP-A" in pat else data["validation"].get("subject", {})
                losses = data.get("training_history", {}).get("val_loss", [])
                epoch = min(range(len(losses)), key=lambda index: losses[index]) + 1 if losses else None
                best_val_loss = losses[epoch - 1] if epoch is not None and losses else data.get("best_validation_loss")
                values = " ".join(f"{metrics_source[key]:12.4f}" if metrics_source.get(key) is not None else f"{'-':>12}"
                                  for key, _ in fields)
                loss_str = f"{best_val_loss:10.4f}" if best_val_loss is not None else f"{'-':>10}"
                print(f"{directory.name:39} {values} {epoch if epoch is not None else '-':>10} {loss_str}")
            update_comparison(root, directories[0])
        if args.baseline and args.best:
            print(f"\nSummary: {summarize_best(root, args.baseline, args.best)}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Cannot summarize experiments: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
