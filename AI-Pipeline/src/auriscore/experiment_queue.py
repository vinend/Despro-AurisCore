"""Idempotent, process-aware orchestration for sequential Heart CNN runs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psutil

from .config import load_config
from .experiment_runtime import atomic_json
from .io import read_table
from .validation import sha256


def slug(name: str) -> str:
    """Use the same stable experiment suffix as the artifact allocator."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "experiment"


def load_plan(path: Path) -> dict[str, Any]:
    """Validate a queue manifest without importing TensorFlow."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("experiments"), list) or not data["experiments"]:
        raise ValueError("Queue requires schema_version 1 and an experiments list")
    names = [item["name"] for item in data["experiments"]]
    if len(names) != len(set(names)) or any(not isinstance(item.get("overrides"), dict)
                                            for item in data["experiments"]):
        raise ValueError("Queue experiment names must be unique and have object overrides")
    return data


def find_experiment(root: Path, name: str) -> Path | None:
    """Find the sole pre-existing directory for an experiment name."""
    results = root / "results"
    if not results.exists():
        return None
    pattern = re.compile(rf"EXP-[A-Za-z]\d+-{re.escape(slug(name))}$")
    matches = [path for path in results.iterdir() if path.is_dir() and pattern.fullmatch(path.name)]
    if len(matches) > 1:
        raise RuntimeError(f"Duplicate directories already exist for {name}: {matches}")
    return matches[0] if matches else None

def active_training_processes() -> list[dict[str, Any]]:
    """Find independently running AurisCore trainers from process command lines."""
    found = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            if process.pid == os.getpid():
                continue
            args = process.info["cmdline"] or []
            script = next((Path(arg).name.lower() for arg in args
                           if Path(arg).name.lower() in {
                               "train_cnn_experiment.py", "train_cnn.py", "run_experiment_queue.py",
                           }), None)
            if script is None:
                continue
            name = args[args.index("--name") + 1] if "--name" in args and len(args) > args.index("--name") + 1 else None
            found.append({"pid": process.pid, "name": name, "script": script})
        except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError, IndexError):
            continue
    return found


def _best_from_metrics(metrics: dict[str, Any]) -> tuple[int | None, float | None]:
    losses = metrics.get("training_history", {}).get("val_loss", [])
    if not losses:
        return None, None
    index = min(range(len(losses)), key=lambda position: losses[position])
    return index + 1, float(losses[index])


def is_completed(directory: Path) -> bool:
    """Require both numerical results and a saved model before skipping."""
    if (directory / "request.json").exists():
        status_file = directory / "status.json"
        if not status_file.exists():
            return False
        try:
            if json.loads(status_file.read_text(encoding="utf-8")).get("status") != "completed":
                return False
        except (OSError, ValueError):
            return False
    metrics_path = directory / "metrics.json"
    if not metrics_path.exists() or not any(
        (directory / name).exists() for name in ("best_model.keras", "heart_cnn.keras")
    ):
        return False
    try:
        json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return True


def backfill_completed(directory: Path) -> None:
    """Add missing orchestration metadata to completed pre-queue experiments."""
    if not is_completed(directory):
        return
    (directory / "checkpoints").mkdir(exist_ok=True)
    best_model = directory / "best_model.keras"
    if not best_model.exists():
        shutil.copy2(directory / "heart_cnn.keras", best_model)
    status_path = directory / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    if status.get("status") != "completed":
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        best_epoch, best_loss = _best_from_metrics(metrics)
        status.update(status="completed", experiment=directory.name,
                      current_epoch=metrics.get("training_epochs"),
                      best_epoch=best_epoch, best_val_loss=best_loss,
                      legacy_run=not (directory / "request.json").exists(),
                      pid=None, updated_at=time.time())
        atomic_json(status_path, status)


def backfill_active(directory: Path, pid: int) -> None:
    """Give a pre-checkpoint job basic visible status without altering its model."""
    status_path = directory / "status.json"
    if not status_path.exists():
        atomic_json(status_path, {"status": "running", "experiment": directory.name,
                                  "current_epoch": None, "best_epoch": None,
                                  "best_val_loss": None, "legacy_run": True,
                                  "pid": pid, "updated_at": time.time()})


def status_rows(root: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Read compact status without opening Keras logs or importing TensorFlow."""
    processes = active_training_processes()
    rows = []
    for item in plan["experiments"]:
        name = item["name"]
        directory = find_experiment(root, name)
        status = {}
        if directory and (directory / "status.json").exists():
            try:
                status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                status = {}
        running = next((process for process in processes if process["name"] == name), None)
        if directory and is_completed(directory):
            state = "completed"
            if status.get("best_epoch") is None:
                metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
                best_epoch, best_loss = _best_from_metrics(metrics)
                status.update(current_epoch=metrics.get("training_epochs"),
                              best_epoch=best_epoch, best_val_loss=best_loss)
        elif running:
            state = "running"
        elif directory and status.get("status") == "running":
            owner = status.get("pid")
            state = "running" if owner and psutil.pid_exists(int(owner)) else "interrupted"
        elif directory:
            state = status.get("status", "incomplete")
        else:
            state = "queued"
        rows.append({"name": name, "experiment_id": directory.name if directory else None,
                     "status": state, "epoch": status.get("current_epoch"),
                     "best_val_loss": status.get("best_val_loss"),
                     "pid": running["pid"] if running else status.get("pid")})
    return rows


@contextmanager
def queue_lock(root: Path) -> Iterator[None]:
    """Hold one OS file lock for the entire sequential queue lifetime."""
    path = root / ".runtime" / "training-queue.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            handle.seek(0)
            if handle.read(1) != b"1":
                handle.seek(0)
                handle.write(b"1")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("A training queue is already running") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def wait_for_other_trainers(interval_seconds: int = 30) -> None:
    """Keep the detached queue idle while a prior trainer owns the CPU."""
    while active_training_processes():
        time.sleep(interval_seconds)


def verify_segments(root: Path, base: dict[str, Any]) -> str:
    """Verify prepared data without invalidating it for training-code edits."""
    table = root / "data" / "processed" / "segments.csv"
    provenance = root / "data" / "processed" / "segments_provenance.json"
    data = json.loads(provenance.read_text(encoding="utf-8"))
    if data.get("config") != base or data.get("table_sha256") != sha256(table):
        raise ValueError("Prepared segments differ from their preprocessing provenance")
    return data["table_sha256"]


def _request(config: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(config, sort_keys=True).encode("utf-8")
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "config": config}


def _check_existing_config(directory: Path, request: dict[str, Any]) -> None:
    """Prevent a completed name from silently referring to different settings."""
    request_path = directory / "request.json"
    if request_path.exists():
        saved = json.loads(request_path.read_text(encoding="utf-8"))
        if saved.get("sha256") != request["sha256"]:
            raise ValueError(f"Configuration changed for existing experiment {directory.name}")
        return
    config_path = directory / "config.json"
    if config_path.exists():
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        differences = [key for key, value in request["config"].items()
                       if key != "experiment_name" and saved.get(key) != value]
        if differences:
            raise ValueError(f"Configuration differs from legacy experiment {directory.name}: {differences}")


def run_one(root: Path, base: dict[str, Any], item: dict[str, Any]) -> str:
    """Skip, wait for, resume, or create exactly one named CNN experiment."""
    name = item["name"]
    request_config = dict(base, **item["overrides"], experiment_name=name)
    request = _request(request_config)
    directory = find_experiment(root, name)
    if directory and is_completed(directory):
        _check_existing_config(directory, request)
        backfill_completed(directory)
        return f"skipped completed {directory.name}"
    wait_for_other_trainers()
    directory = find_experiment(root, name)
    if directory and is_completed(directory):
        _check_existing_config(directory, request)
        backfill_completed(directory)
        return f"skipped completed {directory.name}"
    segments_sha = verify_segments(root, base)
    if directory is None:
        from .visualization import allocate_experiment
        directory = allocate_experiment(root, name)
        atomic_json(directory / "request.json", request)
        atomic_json(directory / "config.json", request_config)
        atomic_json(directory / "status.json", {
            "status": "queued", "experiment": directory.name,
            "current_epoch": 0, "best_epoch": None, "best_val_loss": None,
            "segments_sha256": segments_sha, "request_sha256": request["sha256"],
            "updated_at": time.time(),
        })
    elif not (directory / "request.json").exists():
        raise RuntimeError(
            f"{directory.name} is an incomplete pre-checkpoint legacy run; "
            "there is no training state to resume"
        )
    _check_existing_config(directory, request)
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    status_file = directory / "status.json"
    status = json.loads(status_file.read_text(encoding="utf-8"))
    if status.get("segments_sha256") not in (None, segments_sha):
        raise ValueError(f"Prepared dataset changed for existing experiment {directory.name}")
    status.update(status="running", pid=os.getpid(), updated_at=time.time(),
                  request_sha256=request["sha256"], segments_sha256=segments_sha)
    atomic_json(status_file, status)
    print(f"[{directory.name}] Starting CNN training ({config.get('cnn_epochs', 50)} max epochs, patience {config.get('cnn_patience', 8)})...", flush=True)
    started = time.perf_counter()
    try:
        from .cnn import train_cnn  # TensorFlow remains lazy until training is needed.
        result = train_cnn(read_table(root / "data/processed/segments.csv"), config, root,
                           output_dir=directory / "intermediate", experiment_dir=directory)
        duration = time.perf_counter() - started
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        best_epoch, best_loss = _best_from_metrics(metrics)
        atomic_json(directory / "runtime.json", {
            "training_and_reporting_seconds_this_attempt": duration,
            "python_executable": sys.executable,
            "tensorflow": result["tensorflow"],
        })
        status.update(status="completed", current_epoch=metrics["training_epochs"],
                      best_epoch=best_epoch, best_val_loss=best_loss,
                      pid=None, updated_at=time.time())
        atomic_json(status_file, status)
        from .visualization import update_comparison
        try:
            update_comparison(root, directory)
        except (OSError, ValueError, KeyError) as exc:
            print(f"Comparison refresh failed; run summarize_experiments.py: {exc}", file=sys.stderr, flush=True)
        return f"completed {directory.name}"
    except BaseException as exc:
        latest = json.loads(status_file.read_text(encoding="utf-8"))
        latest.update(status="failed", pid=None, error=f"{type(exc).__name__}: {exc}",
                      updated_at=time.time())
        atomic_json(status_file, latest)
        raise


def run_queue(root: Path, plan: dict[str, Any], only: str | None = None) -> list[str]:
    """Run a fixed manifest sequentially in the caller process."""
    base = load_config(root / plan["base_config"])
    if base.get("model_type") != "cnn":
        raise ValueError("Queue base configuration must select a CNN")
    items = [item for item in plan["experiments"] if only is None or item["name"] == only]
    if not items:
        raise ValueError(f"Experiment not present in queue: {only}")
    queue_state = root / ".runtime" / "training-queue.json"
    with queue_lock(root):
        atomic_json(queue_state, {"status": "running", "pid": os.getpid(),
                                  "current_experiment": None, "updated_at": time.time()})
        outcomes = []
        print(f"\n======================================================================", flush=True)
        print(f"  AurisCore AI Training Queue ({len(items)} experiment(s) scheduled)", flush=True)
        print(f"======================================================================\n", flush=True)
        try:
            for idx, item in enumerate(items, start=1):
                print(f">>> [{idx}/{len(items)}] Initializing {item['name']} ...", flush=True)
                atomic_json(queue_state, {"status": "running", "pid": os.getpid(),
                                          "current_experiment": item["name"],
                                          "updated_at": time.time()})
                outcome = run_one(root, base, item)
                outcomes.append(outcome)
                print(f"✓ [{idx}/{len(items)}] {outcome}\n", flush=True)
            atomic_json(queue_state, {"status": "completed", "pid": None,
                                      "current_experiment": None, "updated_at": time.time()})
        except BaseException as exc:
            atomic_json(queue_state, {"status": "failed", "pid": None,
                                      "current_experiment": item["name"],
                                      "error": f"{type(exc).__name__}: {exc}",
                                      "updated_at": time.time()})
            raise
    return outcomes
