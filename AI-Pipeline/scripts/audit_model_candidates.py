"""Audit models, optionally smoke-test inference, and package engineering candidates."""
import argparse
import json
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.model_audit import audit_repository, package_candidate, verify_package


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime', action='store_true', help='Load Keras models and infer on synthetic audio')
    parser.add_argument('--report', type=Path, help='Create a new JSON report; existing files are preserved')
    parser.add_argument('--package', help='Experiment directory name to package')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--verify', type=Path, help='Verify an existing candidate package')
    args = parser.parse_args()
    if args.package and not args.destination:
        parser.error('--package requires --destination')
    try:
        if args.verify:
            report = verify_package(args.verify)
        elif args.package:
            source = (args.root / 'results' / args.package).resolve()
            if source.parent != (args.root / 'results').resolve():
                raise ValueError('Package must name one experiment directory')
            package_candidate(source, args.destination, runtime=args.runtime)
            report = verify_package(args.destination)
        else:
            report = audit_repository(args.root, runtime=args.runtime)
        output = json.dumps(report, indent=2, allow_nan=False) + '\n'
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open('x', encoding='utf-8') as stream:
                stream.write(output)
        print(output)
        if 'candidates' in report and any(not item['structural_valid'] or (args.runtime and item['runtime']['status'] != 'passed') for item in report['candidates']):
            raise SystemExit(1)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'Model audit failed: {exc}\n')


if __name__ == '__main__':
    main()
