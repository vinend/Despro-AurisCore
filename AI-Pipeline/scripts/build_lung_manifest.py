"""Audit HF training annotations; official test labels remain unread."""
import argparse
import json
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.dataset_lung import build_manifest

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("data/external/hf-lung-v1/extracted"))
    p.add_argument("--output", type=Path, default=Path("data/processed/lung"))
    a = p.parse_args()
    frame, events, audit = build_manifest(a.root)
    a.output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(a.output / "recordings.csv", index=False)
    events.to_csv(a.output / "events.csv", index=False)
    (a.output / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
