"""Launch explicitly authorized development experiments serially, requiring GPU."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.lung_research_queue import run_queue

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorized-training", action="store_true")
    args = parser.parse_args()
    run_queue(args.plan, args.cache, args.audit, args.results, args.output, authorized=args.authorized_training)
