"""Stage patient-disjoint ICBHI TRAIN audio through ZIP byte ranges."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
from urllib.parse import urlsplit
import zlib
from zipfile import ZipFile

from auriscore.lung_icbhi import train_recordings


ARCHIVE_SIZE = 1_978_998_275
ARCHIVE_MIRROR_URL = "https://dataverse.harvard.edu/api/access/datafile/7127117"
# The mirror keeps the pre-correction device suffix on this TRAIN recording.
_CORRECTED_STEM = {"226_1b1_Pl_sc_LittC2SE": "226_1b1_Pl_sc_Meditron"}


def _curl(*args: str, url: str) -> bytes:
    # Do not include curl's command/redirect credentials in an exception.
    proc = subprocess.run(["curl", "--fail", "--silent", "--show-error",
                           "--retry", "2", "--max-time", "30", *args, url],
                          capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"ICBHI range request failed (curl exit {proc.returncode})")
    return proc.stdout


def _mirror_archive_url() -> str:
    # Harvard Dataverse sends a short-lived, signed HTTPS download location.
    headers = _curl("--location", "--proto-redir", "=https", "--dump-header", "-",
                    "--range", "-32", "--output", "/dev/null",
                    url=f"{ARCHIVE_MIRROR_URL}?stage={time.time_ns()}")
    if not any(line.startswith(b"HTTP/") and b" 303 " in line
               for line in headers.splitlines()):
        raise ValueError("Expected signed redirect from the ICBHI archive mirror")
    locations = [line.partition(b":")[2].strip().decode("ascii") for line in headers.splitlines()
                 if line.lower().startswith(b"location:")]
    if len(locations) != 1 or urlsplit(locations[0]).scheme != "https":
        raise ValueError("Expected exactly one HTTPS ICBHI archive location")
    return locations[0]


class _RemoteZip(io.RawIOBase):
    """Read exact byte ranges. ZIP metadata is used to select payloads."""
    def __init__(self, url: str):
        self.url = url
        self.position = 0

    def seek(self, offset: int, whence: int = 0) -> int:
        self.position = (0, self.position, ARCHIVE_SIZE)[whence] + offset
        return self.position

    def tell(self) -> int:
        return self.position

    def seekable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        start = self.position
        end = ARCHIVE_SIZE if size == -1 else min(ARCHIVE_SIZE, start + size)
        if start == end:
            return b""
        result = _curl("--max-filesize", str(end - start), "--dump-header", "-",
                       "--range", f"{start}-{end - 1}", url=self.url)
        headers, data = result.split(b"\r\n\r\n", 1)
        expected = f"content-range: bytes {start}-{end - 1}/{ARCHIVE_SIZE}".encode()
        if expected not in headers.lower().splitlines() or len(data) != end - start:
            raise RuntimeError("ICBHI archive served an inexact byte range")
        self.position = end
        return data


def stage(split: Path, destination: Path, limit: int | None = None) -> None:
    train = train_recordings(split.read_bytes())
    if limit is not None and not 0 < limit <= len(train):
        raise ValueError("ICBHI recording limit out of range")
    archive_url = _mirror_archive_url()
    with ZipFile(_RemoteZip(archive_url)) as archive:
        files = {}
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            stem = _CORRECTED_STEM.get(relative.stem, relative.stem)
            if stem not in train or relative.suffix not in {".wav", ".txt"}:
                continue
            name = stem + relative.suffix
            if name in files:
                raise ValueError("Duplicate allowlisted ICBHI archive member")
            files[name] = info
        stems = sorted(train)[:limit]
        names = [f"{stem}{suffix}" for stem in stems for suffix in (".wav", ".txt")]
        missing = set(names) - files.keys()
        if missing:
            raise ValueError(f"ICBHI archive is missing {len(missing)} allowlisted TRAIN members")
        items = [(name, files[name]) for name in names]
    destination.mkdir(exist_ok=True, parents=True)

    def extract_chunk(chunk):
        with ZipFile(_RemoteZip(archive_url)) as archive:
            for name, info in chunk:
                path = destination / name
                if path.exists() and path.stat().st_size == info.file_size:
                    crc = 0
                    with path.open("rb") as existing:
                        for data in iter(lambda: existing.read(1024 * 1024), b""):
                            crc = zlib.crc32(data, crc)
                    if crc == info.CRC:
                        continue
                temporary = path.with_suffix(path.suffix + ".staging")
                with archive.open(info) as member, temporary.open("wb") as output:
                    shutil.copyfileobj(member, output, length=1024 * 1024)
                temporary.replace(path)
        return len(chunk)

    finished = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(extract_chunk, items[i:i + 20]) for i in range(0, len(items), 20)]
        for job in as_completed(jobs):
            finished += job.result()
            print(f"{finished}/{len(items)} TRAIN members staged", flush=True)
    print(f"Staged {len(stems)} eligible TRAIN recordings", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", type=Path, help="Official split metadata with pinned SHA-256")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--limit", type=int, help="Stage only this many TRAIN recordings for a smoke test")
    args = parser.parse_args()
    stage(args.split, args.destination, args.limit)
