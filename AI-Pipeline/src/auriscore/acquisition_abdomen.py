"""Download the open-access Figshare Bowel Sounds dataset with checksum verification."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .validation import sha256

FIGSHARE_ARTICLE_ID = "28595741"
FIGSHARE_API_URL = f"https://api.figshare.com/v2/articles/{FIGSHARE_ARTICLE_ID}"
LOG = logging.getLogger(__name__)


def md5_file(path: Path) -> str:
    """Calculate MD5 digest of a file in chunks."""
    digest = hashlib.md5()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path, timeout: int = 60) -> None:
    """Download atomically with retry, never overwrite complete files."""
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "AurisCore-Research/0.1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            partial.replace(destination)
            return
        except (OSError, TimeoutError) as exc:
            if partial.exists():
                partial.unlink(missing_ok=True)
            if attempt == 2:
                raise RuntimeError(f"Failed to download {url} after 3 attempts: {exc}") from exc
            time.sleep(2 ** attempt)


def fetch_figshare_metadata(api_url: str = FIGSHARE_API_URL) -> list[dict[str, Any]]:
    """Fetch article file list from Figshare API."""
    req = urllib.request.Request(api_url, headers={"User-Agent": "AurisCore-Research/0.1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    files = payload.get("files", [])
    if not files:
        raise ValueError(f"No files returned by Figshare API: {api_url}")
    return files


def acquire_abdomen(destination: Path, workers: int = 4, api_url: str = FIGSHARE_API_URL) -> dict[str, int]:
    """Acquire all public Bowel Sounds WAV and annotation files (~750 MB); validate checksums."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    files = fetch_figshare_metadata(api_url)
    md5_sums: dict[str, str] = {f["name"]: f["computed_md5"] for f in files}

    # Save manifest of expected MD5 checksums
    md5_manifest = destination / "MD5SUMS.txt"
    lines = [f"{md5}  {name}" for name, md5 in sorted(md5_sums.items())]
    md5_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    missing = [f for f in files if not (destination / f["name"]).exists()]

    if missing:
        LOG.info("Downloading %d public Abdomen files (%d connections)", len(missing), workers)
        failures = []

        def fetch(item: dict[str, Any]) -> None:
            name = item["name"]
            output = destination / name
            if not output.resolve().is_relative_to(destination):
                raise ValueError("Unsafe target path detected")
            download_file(item["download_url"], output)
            calculated = md5_file(output)
            expected = item.get("computed_md5")
            if expected and calculated.lower() != expected.lower():
                output.unlink(missing_ok=True)
                raise ValueError(f"MD5 mismatch for {name}: got {calculated}, expected {expected}")

        if workers > 1 and len(missing) > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(fetch, item): item["name"] for item in missing}
                for index, future in enumerate(as_completed(futures), start=1):
                    try:
                        future.result()
                        LOG.info("Downloaded %d/%d: %s", index, len(missing), futures[future])
                    except Exception as exc:  # noqa: BLE001
                        LOG.error("Download failed for %s: %s", futures[future], exc)
                        failures.append(str(exc))
        else:
            for index, item in enumerate(missing, start=1):
                try:
                    fetch(item)
                    LOG.info("Downloaded %d/%d: %s", index, len(missing), item["name"])
                except Exception as exc:  # noqa: BLE001
                    LOG.error("Download failed for %s: %s", item["name"], exc)
                    failures.append(str(exc))

        if failures:
            raise RuntimeError(f"{len(failures)} files failed to download. Re-run to resume. Error: {failures[0]}")

    # Generate SHA256 sums for consistency with CirCor pipeline
    sha256_lines = []
    for f in sorted(files, key=lambda x: x["name"]):
        file_path = destination / f["name"]
        if file_path.exists():
            sha256_lines.append(f"{sha256(file_path)}  {f['name']}")
    (destination / "SHA256SUMS.txt").write_text("\n".join(sha256_lines) + "\n", encoding="utf-8")

    LOG.info("Acquisition complete: %d verified Abdomen files in %s", len(files), destination)
    return {"verified_files": len(files)}
