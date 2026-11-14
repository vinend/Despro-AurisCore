"""Export an exclusive source-only ZIP for private VPS preparation, never upload."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = ['.dockerignore', 'WebApp/package.json', 'WebApp/package-lock.json',
         'WebApp/next.config.ts', 'WebApp/tsconfig.json', 'WebApp/postcss.config.mjs',
         'WebApp/mini-services/device-gateway/package.json',
         'WebApp/mini-services/device-gateway/package-lock.json',
         'WebApp/mini-services/device-gateway/index.ts', 'WebApp/mini-services/device-gateway/gateway.ts',
         'AI-Pipeline/scripts/analyze_recording.py', 'AI-Pipeline/scripts/_bootstrap.py',
         'scripts/prepare_hosting_bundle.py', 'scripts/prepare_hosting_source.py',
         'hosting/Dockerfile', 'hosting/compose.yaml', 'hosting/Caddyfile',
         'hosting/requirements.txt', 'hosting/verify_models.py', 'hosting/README.md',
         'hosting/hosting.env.example']
TREES = ['WebApp/src', 'WebApp/public', 'AI-Pipeline/src']


def export(output: Path) -> int:
    """Whitelist application source, excluding machine state and generated payloads."""
    selected = {ROOT / file for file in FILES}
    for tree in TREES:
        for path in (ROOT / tree).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc', '.pyo'}:
                if path.is_symlink() or path.name.startswith('.env'):
                    raise ValueError('Unexpected sensitive/symlink source entry')
                selected.add(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'x', ZIP_DEFLATED) as archive:
        for path in sorted(selected):
            archive.write(path, path.relative_to(ROOT).as_posix())
    return len(selected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(f'Source-only ZIP created: {export(args.output.resolve())} files. No upload performed.')
