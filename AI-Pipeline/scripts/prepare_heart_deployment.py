"""Package an explicitly evaluated final Heart model; never train or invent evidence."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.heart_inference import prepare_heart_deployment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "metadata", "evaluation", "decision", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare_heart_deployment(args.model, args.metadata, args.evaluation, args.decision, args.destination)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Heart package preparation failed: {exc}\n")
    print(result)


if __name__ == "__main__":
    main()
