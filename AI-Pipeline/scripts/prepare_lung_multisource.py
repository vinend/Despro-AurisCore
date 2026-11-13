"""Create a new development cache; never change original HF or open test labels."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.lung_multisource import build_cache

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-cache', type=Path, required=True)
    parser.add_argument('--base-audit', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build_cache(args.base_cache, args.base_audit, args.source, args.output)
    print({key: result[key] for key in ('source_recordings_added', 'source_windows_added', 'source_patients_added', 'source_event_counts', 'source_event_patient_support')})
