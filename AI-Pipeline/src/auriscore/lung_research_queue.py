"""Explicit development-only serial Lung experiments; never open official test."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from .acquisition_lung import digest
from .lung_training import preflight
from .lung_training_policy import load_policy


def compare_evaluations(baseline: dict, candidate: dict, *, baseline_id: str = 'L006') -> dict:
    """Compare only matching development classes and held-out date groups."""
    if (baseline.get("role") != "development_only" or candidate.get("role") != "development_only"
            or sorted(baseline["groups"]) != sorted(candidate["groups"])):
        raise ValueError("Matching development populations required")
    for evaluation in (baseline, candidate):
        if (not evaluation["classes"] or len(set(evaluation["classes"])) != len(evaluation["classes"])
                or not len(evaluation["classes"]) == len(evaluation["metrics"]) == len(evaluation["thresholds"])):
            raise ValueError("Incomplete or duplicated evaluation classes")
    reference = dict(zip(baseline["classes"], baseline["metrics"]))
    result = {}
    for label, threshold, metric in zip(candidate["classes"], candidate["thresholds"], candidate["metrics"]):
        if label not in reference:
            raise ValueError("Candidate class absent from baseline")
        old = reference[label]
        if (metric["tp"] + metric["fn"], metric["tn"] + metric["fp"]) != (old["tp"] + old["fn"], old["tn"] + old["fp"]):
            raise ValueError("Class support mismatch; do not compare different masks/populations")
        total = sum(metric[key] for key in ("tn", "fp", "fn", "tp"))
        deltas = {key: metric[key] - old[key] if metric[key] is not None and old[key] is not None else None
                  for key in ("f1", "sensitivity", "specificity", "precision", "roc_auc", "pr_auc")}
        result[label] = {**metric, "threshold": threshold, 'comparison_baseline': baseline_id,
                         "accuracy": (metric["tn"] + metric["tp"]) / total if total else None,
                         "balanced_accuracy": (metric["sensitivity"] + metric["specificity"]) / 2
                         if metric["sensitivity"] is not None and metric["specificity"] is not None else None,
                         "class_counts": {"positive": metric["tp"] + metric["fn"], "negative": metric["tn"] + metric["fp"]},
                         'deltas_from_baseline': deltas,
                         **({'deltas_from_L006': deltas} if baseline_id in {'L006', 'EXP-L006-temporal-cnn-context'} else {})}
    return result


def run_queue(plan_path: Path, cache: Path, audit: Path, results: Path, output: Path,
              *, authorized: bool = False) -> None:
    """Launch fixed independent controls sequentially; fail without overwriting runs."""
    if authorized is not True:
        raise PermissionError("Explicit user training authorization required")
    plan_path, cache, audit, results, output = map(lambda p: Path(p).resolve(), (plan_path, cache, audit, results, output))
    plan = json.loads(plan_path.read_text())
    if plan.get("schema_version") != "lung-development-queue-v1" or not plan.get("runs"):
        raise ValueError("Explicit Lung development queue required")
    config, _ = preflight(cache, audit)
    pipeline = Path(__file__).resolve().parents[2]
    baseline = results / plan["baseline"]
    baseline_source = json.loads((baseline / "source.json").read_text())
    baseline_evaluation = json.loads((baseline / "fold-0/evaluation.json").read_text())
    if (json.loads((baseline / "status.json").read_text())["status"] != "completed"
            or baseline_source.get("config") != config
            or baseline_source.get("index_sha256") != digest(cache / "index.csv")
            or baseline_source.get("audit_sha256") != digest(audit)):
        raise ValueError("Completed baseline bound to the same development cache required")
    ids = [run["experiment_id"] for run in plan["runs"]]
    if (len(set(ids)) != len(ids) or any(Path(name).name != name or not name.startswith("EXP-L") for name in ids)
            or any((results / name).exists() for name in ids) or output.exists()):
        raise ValueError("Fresh unique experiment/output directories required")
    for position, run in enumerate(plan["runs"]):
        if run.get('comparison_baseline', plan['baseline']) not in [plan['baseline'], *ids[:position]]:
            raise ValueError('Comparison control must be the frozen baseline or an earlier queued run')
        policy = (pipeline / run["policy"]).resolve()
        if not policy.is_relative_to(pipeline / "configs"):
            raise ValueError("Queue policy must be under configs")
        load_policy(policy, config)
    import tensorflow as tf
    if not tf.config.list_physical_devices("GPU"):
        raise RuntimeError("GPU required; CPU fallback refused")
    output.mkdir(parents=True)
    inventory = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    (output / "pip-freeze.txt").write_text(inventory)
    frozen = {"plan": plan, "plan_sha256": digest(plan_path), "config": config,
              "threshold_rule": {"population": "development_only", "method": "maximum_F1_per_class",
                                 "grid_start": .05, "grid_stop": .95, "points": 37, "tie": "lowest_threshold"},
              "early_stopping": {"monitor": "val_loss", "patience": config["patience"], "restore_best_weights": True},
              "grouping": "shifted_recording_date; patient independence unverified",
              "runtime": {"python": sys.version, "tensorflow": tf.__version__,
                          "pip_freeze_sha256": digest(output / "pip-freeze.txt")},
              "index_sha256": digest(cache / "index.csv"), "audit_sha256": digest(audit),
              "baseline_evaluation_sha256": digest(baseline / "fold-0/evaluation.json"),
              "official_test_labels_opened": False, "deployment_eligible": False,
              "code_sha256": {str(p.relative_to(pipeline)): digest(p)
                  for pattern in ("src/**/*.py", "scripts/*.py", "configs/*") for p in sorted(pipeline.glob(pattern)) if p.is_file()},
              "policies": {run["experiment_id"]: json.loads((pipeline / run["policy"]).read_text()) for run in plan["runs"]}}
    (output / "protocol.json").write_text(json.dumps(frozen, indent=2))
    status = {"status": "running", "completed": [], "active": None, "deployment_eligible": False}

    def save_status():
        status["updated_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "status.json").write_text(json.dumps(status, indent=2))

    save_status()
    try:
        for run in plan["runs"]:
            identity = run["experiment_id"]
            status["active"] = identity
            save_status()
            experiment = results / identity
            with (output / f"{identity}.log").open("x") as log:
                subprocess.run([sys.executable, "-u", str(pipeline / "scripts/train_lung_cnn.py"),
                    "--cache", str(cache), "--audit", str(audit), "--output", str(experiment),
                    "--training-policy", str(pipeline / run["policy"]), "--authorized-training", "--require-gpu"],
                    cwd=pipeline, stdout=log, stderr=subprocess.STDOUT, check=True)
            for script, suffix in (("diagnose_lung_development.py", "diagnostics"), ("evaluate_lung_localization.py", "localization")):
                with (output / f"{identity}.{suffix}.log").open("x") as log:
                    subprocess.run([sys.executable, str(pipeline / "scripts" / script), "--cache", str(cache),
                        "--audit", str(audit), "--experiment", str(experiment), "--output", str(output / f"{identity}.{suffix}.json")],
                        cwd=pipeline, stdout=log, stderr=subprocess.STDOUT, check=True)
            evaluation = json.loads((experiment / "fold-0/evaluation.json").read_text())
            control_id = run.get('comparison_baseline', plan['baseline'])
            control_evaluation = json.loads((results / control_id / 'fold-0/evaluation.json').read_text())
            comparison = {"baseline": control_id, "candidate": identity,
                          "unit": "supervised_development_frames_including_overlapping_windows",
                          "threshold_selection": "per_class_maximum_F1_on_same_development_population",
                          "independent_patient_validation": False, "deployment_eligible": False,
                          "metrics": compare_evaluations(control_evaluation, evaluation, baseline_id=control_id)}
            (output / f"{identity}.comparison.json").write_text(json.dumps(comparison, indent=2))
            if run.get('pipeline_audit') is True:
                for suffix, arguments in [
                    ('parity', ['verify_lung_reload.py', '--cache', str(cache), '--experiment', str(experiment),
                                '--device', 'gpu', '--deterministic', '--require-parity',
                                '--output', str(output / f'{identity}.parity.json')]),
                    ('pipeline', ['investigate_lung_pipeline.py', '--cache', str(cache), '--audit', str(audit),
                                  '--experiment', str(experiment), '--output', str(output / f'{identity}.pipeline')])]:
                    with (output / f'{identity}.{suffix}.log').open('x') as log:
                        subprocess.run([sys.executable, str(pipeline / 'scripts' / arguments[0]), *arguments[1:]],
                            cwd=pipeline, stdout=log, stderr=subprocess.STDOUT, check=True)
            status["completed"].append(identity)
            save_status()
        status.update(status="completed", active=None)
    except BaseException as error:
        status.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        save_status()
