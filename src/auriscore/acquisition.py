"""Download the public, versioned CirCor release and verify original bytes."""
import logging
import shutil
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from .validation import sha256

BASE = "https://physionet.org/files/circor-heart-sound/1.0.3/"
ARCHIVE = "https://physionet.org/static/published-projects/circor-heart-sound/the-circor-digiscope-phonocardiogram-dataset-1.0.3.zip"
LOG = logging.getLogger(__name__)


def download_file(url: str, destination: Path) -> None:
    """Download atomically, retry transient errors, never overwrite originals."""
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            partial.replace(destination)
            return
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def acquire(destination: Path, workers: int = 16) -> dict[str, int]:
    """Acquire all public files (~449.5 MB ZIP); validate published SHA256 hashes."""
    destination.mkdir(parents=True, exist_ok=True)
    download_file(BASE + "SHA256SUMS.txt", destination / "SHA256SUMS.txt")
    sums = {}
    for line in (destination / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.lstrip("*").removeprefix("./")] = digest
    missing = [name for name in sums if not (destination / name).exists()]
    if missing and workers > 0:
        # PhysioNet explicitly advertises this public S3 distribution on its source page.
        mirror = "https://physionet-open.s3.amazonaws.com/circor-heart-sound/1.0.3/"
        def fetch(name: str) -> None:
            output = destination / name
            if not output.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Unsafe published path")
            try:
                download_file(mirror + name, output)
            except OSError:
                LOG.warning("S3 unavailable for %s; retrying original PhysioNet endpoint", name)
                download_file(BASE + name, output)
            if sha256(output) != sums[name]:
                raise ValueError(f"Checksum mismatch: {name}; restore manually")
        LOG.info("Downloading %d public files with %d connections", len(missing), workers)
        failures = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fetch, name) for name in missing]
            for index, future in enumerate(as_completed(futures), start=1):
                try:
                    future.result()
                except (OSError, ValueError) as exc:
                    failures.append(str(exc))
                    LOG.warning("File download failed: %s", exc)
                if index % 250 == 0:
                    LOG.info("Downloaded %d/%d files", index, len(missing))
        if failures:
            raise ValueError(f"{len(failures)} downloads failed. Rerun to resume. First error: {failures[0]}")
    elif missing:
        archive = destination / "release.zip"
        LOG.info("Downloading public CirCor archive; this may take several minutes")
        download_file(ARCHIVE, archive)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if member.is_dir():
                    continue
                parts = Path(member.filename).parts
                # Archive has one dataset root directory. Only extract published entries.
                name = Path(*parts[1:]).as_posix() if len(parts) > 1 else parts[0]
                if name not in sums:
                    continue
                output = destination / name
                if not output.resolve().is_relative_to(destination.resolve()):
                    raise ValueError("Unsafe archive path")
                if output.exists():
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                partial = output.with_suffix(output.suffix + ".part")
                with bundle.open(member) as source, partial.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if sha256(partial) != sums[name]:
                    raise ValueError(f"Checksum mismatch: {name}")
                partial.replace(output)
    for name, digest in sums.items():
        path = destination / name
        if not path.exists() or sha256(path) != digest:
            raise ValueError(f"Missing/changed original: {path}. Restore manually; source will not be overwritten.")
    LOG.info("Verified %d original files", len(sums))
    return {"verified_files": len(sums)}
