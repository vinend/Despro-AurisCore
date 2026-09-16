"""Dataset summaries and plots derived exclusively from local measurements."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from .splitting import split_summary


def analyze_dataset(root: Path, manifest: pd.DataFrame) -> dict:
    """Save auditable quality statistics, plots and a Markdown dataset report."""
    output = root / "artifacts/dataset_analysis"
    output.mkdir(parents=True, exist_ok=True)
    quality = pd.read_csv(root / "metadata/audio_validation.csv", keep_default_na=False)
    durations = pd.to_numeric(manifest.duration_sec, errors="coerce")
    hashes = manifest[manifest.sha256.ne("")]
    duplicates = hashes[hashes.sha256.duplicated(keep=False)]
    duplicates.to_csv(output / "duplicates.csv", index=False)
    missing = {c: int((manifest[c].isna() | manifest[c].eq("")).sum()) for c in manifest.columns}
    stats = {
        "recordings": len(manifest), "original_subject_ids": manifest.subject_id.replace("", pd.NA).nunique(),
        "linked_subjects": manifest.subject_group.replace("", pd.NA).nunique(),
        "class_distribution_recordings": manifest.label.value_counts().to_dict(),
        "class_distribution_subject_ids": manifest.drop_duplicates("subject_id").label.value_counts().to_dict(),
        "sampling_rates": manifest.original_sampling_rate.value_counts().to_dict(),
        "duration_sec": durations.describe().dropna().to_dict(),
        "missing_fields": missing, "duplicate_recordings": len(duplicates),
        "quality_flags": manifest.quality_flag.value_counts().to_dict(),
        "channels": quality.channels.value_counts().to_dict(),
        "splits": split_summary(manifest),
    }
    (output / "statistics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    plots = {
        "class_distribution": manifest.label.value_counts(),
        "recordings_per_subject": manifest.groupby("subject_group").size().value_counts().sort_index(),
        "auscultation_location": manifest.auscultation_location.value_counts(),
    }
    for name, values in plots.items():
        fig, ax = plt.subplots(figsize=(7, 4))
        if not values.empty:
            values.plot.bar(ax=ax)
        ax.set(title=name.replace("_", " "), ylabel="Count")
        fig.tight_layout()
        fig.savefig(output / f"{name}.png", dpi=140)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(durations.dropna(), bins=30)
    ax.set(xlabel="Duration (seconds)", ylabel="Recordings")
    fig.tight_layout()
    fig.savefig(output / "duration_distribution.png", dpi=140)
    plt.close(fig)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/dataset_report.md").write_text(
        "# Dataset report\n\nSelected: CirCor DigiScope 1.0.3 public release. "
        "[Source](https://physionet.org/content/circor-heart-sound/1.0.3/). "
        "Citation: Oliveira et al. (2022), doi:10.13026/tshs-mw03; "
        "Oliveira et al., doi:10.1109/JBHI.2021.3137048. License: ODC-By-1.0; "
        "original LICENSE.txt preserved with data.\n\n"
        "The following counts are measured locally, not inferred from the full cohort description.\n\n"
        f"```json\n{json.dumps(stats, indent=2)}\n```\n\n"
        "## Interpretation and limitations\n\n"
        "Murmur labels are participant/visit annotations, not window-local annotations. "
        "Unknown annotations remain in the manifest and are excluded from training. "
        "Outcome is a separate clinical assessment and is never used as a feature or target. "
        "Repeat participants are linked transitively using Additional ID before splitting. "
        "Excluded-group counts can overlap active-group counts when one visit has an unknown label "
        "and another has a known label; excluded recordings never enter the model. "
        "Combined class names in excluded subject counts denote conflicting visit labels. "
        "Blank notes and Additional ID fields are optional, not missing required annotations. "
        "Conflicting labels across linked visits are excluded. Exact file hashes crossing splits "
        "cause failure; perceptually similar recordings are not detected by file hashing. "
        "Clipping and low energy are engineering quality flags, not validated quality scores. "
        "Data primarily represent young participants from Brazilian screening campaigns and "
        "a different recording device than AurisCore. Resampling 4 kHz recordings to 8 kHz "
        "does not restore information above 2 kHz. Public-release holdouts are local research "
        "splits, not the official hidden Challenge test set. No clinical validity is established.\n",
        encoding="utf-8")
    return stats
