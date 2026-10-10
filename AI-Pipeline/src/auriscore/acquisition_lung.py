"""Pinned HF_Lung_V1 acquisition; no training or test-label inspection."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import urllib.parse
import urllib.request
import urllib.error
import time
import warnings

REVISION = "2a77d37230b1673d332645e6c6afeea29900bcf9"
API = "https://gitlab.com/api/v4/projects/techsupportHF%2FHF_Lung_V1"


def request(url, *, method="GET", headers=None):
    for attempt in range(5):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, method=method,
                headers={"User-Agent": "AurisCore-Lung/1", **(headers or {})}), timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 502, 503, 504} or attempt == 4:
                raise
            time.sleep(min(60, max(2 ** attempt, int(exc.headers.get("Retry-After", "60")))))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git_blob_digest(path):
    path = Path(path)
    result = hashlib.sha1(b"blob " + str(path.stat().st_size).encode() + b"\0")
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def verify_download(path, entry):
    if path.stat().st_size != entry["bytes"]:
        raise ValueError(f"Downloaded size mismatch: {path.name}")
    actual = digest(path)
    if actual != entry["sha256"]:
        # GitLab's content-SHA256 header is inconsistent for train.7z.005 at
        # this revision. Independently verify the pinned repository tree blob.
        if not entry.get("blob_id") or git_blob_digest(path) != entry["blob_id"]:
            raise ValueError(f"Downloaded checksum mismatch: {path.name}")
        warnings.warn(f"{entry['name']}: GitLab SHA256 header differs; pinned Git blob verified", RuntimeWarning)
        entry["api_sha256"] = entry["sha256"]
        entry["sha256"] = actual
        entry["integrity_basis"] = "pinned_git_blob_and_local_sha256"


def metadata(name):
    with request(f"{API}/repository/files/{urllib.parse.quote(name, safe='')}?ref={REVISION}", method="HEAD") as response:
        return {"name": name, "bytes": int(response.headers["X-Gitlab-Size"]),
                "sha256": response.headers["X-Gitlab-Content-Sha256"], "revision": REVISION}


def download(entry, destination):
    """Resume a partial transfer, verifying the published content digest."""
    target = Path(destination) / entry["name"]
    if target.exists():
        if target.stat().st_size != entry["bytes"] or digest(target) != entry["sha256"]:
            raise ValueError(f"Existing file checksum mismatch: {target.name}")
        return target
    partial = target.with_name(target.name + ".part")
    if partial.exists() and partial.stat().st_size == entry["bytes"]:
        verify_download(partial, entry)
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > entry["bytes"]:
        raise ValueError("Oversized partial transfer")
    if offset < entry["bytes"]:
        url = f"https://gitlab.com/techsupportHF/HF_Lung_V1/-/raw/{REVISION}/{urllib.parse.quote(entry['name'], safe='')}"
        with request(url, headers={"Range": f"bytes={offset}-"} if offset else {}) as response:
            if offset and response.status != 206:
                offset = 0
            if offset and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                raise ValueError("Invalid resume response")
            with partial.open("ab" if offset else "wb") as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
    verify_download(partial, entry)
    (Path(destination) / (entry["name"] + ".metadata.json")).write_text(json.dumps(entry), encoding="utf-8")
    partial.replace(target)
    return target


def safe_member(name):
    """Reject traversal and platform-specific absolute archive paths."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in name or not path.parts:
        raise ValueError("Unsafe archive member")


def acquire(destination, *, split="train", extract=True, workers=3):
    """Download selected official split; test defaults to remaining untouched."""
    if split not in {"train", "test"}:
        raise ValueError("Choose an official split")
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with request(f"{API}/repository/tree?ref={REVISION}&per_page=100") as response:
        tree = json.load(response)
    names = sorted(item["name"] for item in tree if re.fullmatch(fr"{split}\.7z\.\d{{3}}", item["name"]))
    if not names or names != [f"{split}.7z.{i:03}" for i in range(1, len(names) + 1)]:
        raise ValueError("Missing archive volume")
    # Persist headers so retries do not repeatedly hit the large-file metadata limit.
    entries = []
    for name in names + ["README.md", "LICENSE", "Disclaimer"]:
        cache = destination / (name + ".metadata.json")
        entry = json.loads(cache.read_text()) if cache.exists() else metadata(name)
        if entry.get("revision") != REVISION or entry.get("name") != name:
            raise ValueError("Metadata revision mismatch")
        entry["blob_id"] = next(item["id"] for item in tree if item["name"] == name)
        cache.write_text(json.dumps(entry), encoding="utf-8")
        entries.append(entry)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda entry: download(entry, destination), entries))
    receipt = {"schema_version": "hf-lung-source-v1", "source": API, "revision": REVISION,
               "split": split, "files": entries, "license": "CC-BY-4.0"}
    (destination / f"{split}-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if extract:
        import py7zr
        joined = destination / f"{split}.7z"
        with joined.open("wb") as output:
            for name in names:
                with (destination / name).open("rb") as stream:
                    shutil.copyfileobj(stream, output, 1024 * 1024)
        extracted = destination / "extracted"
        extracted.mkdir(exist_ok=True)
        # Use a new split staging directory so partial extraction cannot appear complete.
        staging = destination / f"extract-{split}.partial"
        if staging.exists() or (extracted / split).exists():
            raise ValueError("Extraction target already exists; inspect it before retrying")
        with py7zr.SevenZipFile(joined, mode="r") as archive:
            for entry in archive.list():
                safe_member(entry.filename)
                if entry.is_symlink or not (entry.is_file or entry.is_directory):
                    raise ValueError("Archive links are not allowed")
            archive.extractall(staging)
        staging.replace(extracted / split)
        joined.unlink()
    return receipt
