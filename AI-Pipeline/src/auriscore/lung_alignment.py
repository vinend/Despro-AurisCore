"""Sampled development alignment evidence, never holdout labels or model fitting."""
import html
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import soundfile as sf

from .acquisition_lung import digest
from .dataset_lung import parse_labels
from .lung_preprocessing import windows
from .lung_training import preflight


def source_path(root: Path, relative: str) -> Path:
    """Keep reviewed source files inside the supplied extraction directory."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Unsafe/missing development source path")
    return path


def timeline(audio: np.ndarray, rate: int, events: list[dict], classes: list[str]) -> str:
    """Render waveform and original interval lanes on the same seconds axis."""
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    duration = len(mono) / rate
    width, left, span = 1000, 110, 860
    height = 130 + len(classes) * 32
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Waveform and annotated intervals">']
    maximum = max(float(np.abs(mono).max()), 1e-12)
    # Preserve extrema so short sounds remain visible when downsampling for display.
    for i, samples in enumerate(np.array_split(mono, min(860, len(mono)))):
        x = left + i * span / min(860, len(mono))
        parts.append(f'<path d="M{x:.2f},{60-35*samples.max()/maximum:.2f} V{60-35*samples.min()/maximum:.2f}" stroke="#24476b"/>')
    for second in range(int(duration) + 1):
        x = left + span * second / duration
        parts.append(f'<path d="M{x:.2f},20 V{height-20}" stroke="#ddd"/><text x="{x:.2f}" y="105" font-size="11">{second}s</text>')
    for i, label in enumerate(classes):
        y = 120 + i * 32
        parts.append(f'<text x="4" y="{y+14}" font-size="13">{html.escape(label)}</text>')
        for event in events:
            if event["label"] == label:
                start, end = event["start_s"], event["end_s"]
                parts.append(f'<rect x="{left+span*start/duration:.2f}" y="{y}" width="{span*(end-start)/duration:.2f}" height="20" fill="#368576"><title>{html.escape(label)} {start:.3f}–{end:.3f}s</title></rect>')
    return "".join(parts) + "</svg>"


def review_alignment(cache: Path, audit: Path, root: Path, output: Path,
                     *, recording_ids: list[str] | None = None) -> dict:
    """Recompute sampled source features/targets and generate a listenable review.

    Automatic checks establish source/cache agreement, not acoustic correctness
    of annotations. A human must listen and inspect the timeline before fitting.
    """
    cache, audit, root, output = map(Path, (cache, audit, root, output))
    if output.exists():
        raise ValueError("Never overwrite alignment evidence")
    config, index = preflight(cache, audit)
    records = pd.read_csv(audit.parent / "recordings.csv", dtype={"group": str})
    development = records[records.split.isin(["train", "validation"]) & (records.original_split == "train")]
    if development.recording_id.duplicated().any():
        raise ValueError("Duplicate development identities")
    development = development[development.recording_id.isin(index.recording_id)]
    all_events = pd.read_csv(audit.parent / "events.csv")
    events = all_events[all_events.recording_id.isin(development.recording_id)]
    if recording_ids is None:
        chosen = development.sort_values("recording_id").groupby(["split", "device"], sort=True).head(1)
        ids = chosen.recording_id.tolist()
        for label in ("stridor", "rhonchi"):
            candidates = sorted(set(events.loc[events.label == label, "recording_id"]) - set(ids))
            if candidates:
                ids.append(candidates[0])
    else:
        ids = recording_ids
    if not ids or len(set(ids)) != len(ids) or not set(ids).issubset(development.recording_id):
        raise ValueError("Select unique cached development IDs only; test/quarantine forbidden")
    report = {"schema_version": "lung-alignment-review-v1", "role": "development_only",
              "training_started": False, "official_test_labels_opened": False,
              "acoustic_alignment_verified": False, "human_review_required": True,
              "index_sha256": digest(cache / "index.csv"), "audit_sha256": digest(audit), "recordings": []}
    output.mkdir(parents=True)
    sections = []
    for position, identity in enumerate(ids):
        row = development.set_index("recording_id").loc[identity]
        audio_path, label_path = source_path(root, row.file_path), source_path(root, row.label_path)
        if digest(audio_path) != row.sha256 or digest(label_path) != row.label_sha256:
            raise ValueError("Development source changed after audit")
        audio, rate = sf.read(audio_path)
        if not audio.size or not np.isfinite(audio).all():
            raise ValueError("Invalid development audio")
        labels = events[events.recording_id == identity].drop(columns="recording_id").to_dict("records")
        parsed = parse_labels(label_path, len(audio) / rate)
        def canonical(items):
            return sorted((e["label"], round(e["start_s"], 8), round(e["end_s"], 8)) for e in items)
        if canonical(labels) != canonical(parsed):
            raise ValueError("Parsed annotations disagree with audited events")
        rows = index[index.recording_id == identity]
        if not (rows.split.eq(row.split).all() and rows.group.eq(str(row.group)).all()
                and rows.source_sha256.eq(row.sha256).all()):
            raise ValueError("Cache/manifest identity mismatch")
        mismatches, checked = [], []
        for block in windows(audio, rate, labels, config, valid_end_s=row.valid_end_s,
                             coverage=config.get("annotation_coverage_verified") is True):
            name = f"{identity}_{block['start_sample']}.npz"
            if name not in set(rows.file):
                raise ValueError("Missing sampled cache window")
            checked.append(name)
            with np.load(cache / name, allow_pickle=False) as saved:
                for key in ("features", "targets", "mask", "times_s", "start_sample"):
                    expected = np.asarray(block[key])
                    actual = saved[key]
                    matches = (actual.shape == expected.shape and
                               (np.allclose(actual, expected, atol=1e-5, rtol=1e-5) if key == "features"
                                else np.array_equal(actual, expected)))
                    if not matches:
                        mismatches.append({"file": name, "field": key})
        if set(checked) != set(rows.file):
            raise ValueError("Extra sampled cache windows")
        destination = f"recording-{position}.wav"
        shutil.copyfile(audio_path, output / destination)
        item = {"recording_id": identity, "split": row.split, "device": row.device,
                "sample_rate": rate, "duration_s": len(audio) / rate,
                "audio_sha256": row.sha256, "label_sha256": row.label_sha256,
                "windows_checked": len(checked), "mismatches": mismatches,
                "source_cache_agreement": not mismatches, "license": row.license, "events": labels}
        report["recordings"].append(item)
        sections.append(f'<section><h2>{html.escape(identity)} ({html.escape(row.split)}, {html.escape(row.device)})</h2>'
                        f'<p>Source/cache agreement: {not mismatches}; windows checked: {len(checked)}.</p>'
                        f'<audio controls src="{destination}"></audio>{timeline(audio, rate, labels, config["classes"])}</section>')
        print(f"Reviewed {identity}: {len(checked)} windows, {len(mismatches)} mismatches", flush=True)
    report["source_cache_agreement"] = all(item["source_cache_agreement"] for item in report["recordings"])
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    page = ('<!doctype html><meta charset="utf-8"><title>Lung alignment review</title>'
            '<style>body{font:16px sans-serif;max-width:1100px;margin:30px auto;padding:16px}svg{width:100%}section{margin:35px 0}</style>'
            '<h1>Development audio and annotation alignment</h1><p>Listen while following the seconds axis. '
            'Check phase transitions and event intervals. Source/cache agreement does not establish acoustic label accuracy. '
            'No test labels opened; no training. Copied audio retains the dataset license (CC BY 4.0). '
            '<a href="https://doi.org/10.1371/journal.pone.0254134">Dataset authors and source</a>.</p>')
    (output / "review.html").write_text(page + "".join(sections), encoding="utf-8")
    return report
