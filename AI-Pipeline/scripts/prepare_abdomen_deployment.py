"""Package an explicitly selected final bowel-activity model; never train."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.abdomen_inference import prepare_abdomen_deployment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "metadata", "evaluation", "decision", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare_abdomen_deployment(args.model, args.metadata, args.evaluation, args.decision, args.destination)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Abdomen package preparation failed: {exc}\n")
    print(result)


if __name__ == "__main__":
    main()
