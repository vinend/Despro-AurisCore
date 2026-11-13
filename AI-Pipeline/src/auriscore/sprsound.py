"""Pinned SPRSound TRAIN acquisition and explicit acoustic-only supervision."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import time
from urllib.request import Request, urlopen

import numpy as np

REVISION = "bca1e51422a42a042441010081519610ef3845d0"
REPOSITORY = "SJTU-YONGFU-RESEARCH-GRP/SPRSound"
MAPPING = {"Normal": [], "Rhonchi": ["rhonchi"], "Wheeze": ["wheeze"],
           "Stridor": ["stridor"], "Coarse Crackle": ["crackle"],
           "Fine Crackle": ["crackle"], "Wheeze+Crackle": ["wheeze", "crackle"]}
SOUNDS = {"wheeze", "rhonchi", "stridor", "crackle"}


def request_bytes(url: str) -> bytes:
    """HTTPS with bounded retries, timeouts and response size."""
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent": "AurisCore-research-data-audit"}), timeout=45) as response:
                data = response.read(16 * 1024 * 1024 + 1)
            if len(data) > 16 * 1024 * 1024:
                raise ValueError("Source response exceeds size limit")
            return data
        except (OSError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def eligible_train(tree: list[dict]) -> tuple[list[dict], dict]:
    """Inspect test filenames only; never fetch test annotation/audio contents."""
    train = [e for e in tree if e["path"].startswith("BioCAS2022/train2022_wav/") and e["path"].endswith(".wav")]
    test_ids = {PurePosixPath(e["path"]).stem.split("_")[0] for e in tree
                if e["path"].startswith("BioCAS2022/test2022_wav/") and e["path"].endswith(".wav")}
    test_blobs = {e.get('sha') for e in tree if e['path'].startswith('BioCAS2022/test2022_wav/') and e['path'].endswith('.wav')}
    selected = [e for e in train if PurePosixPath(e["path"]).stem.split("_")[0] not in test_ids and e.get('sha') not in test_blobs]
    return selected, {"train_recordings": len(train), "test_patients_inventory_only": len(test_ids),
                      "eligible_train_recordings": len(selected),
                      "exact_test_blob_conflicts": sum(e.get('sha') in test_blobs for e in train),
                      "eligible_train_patients": len({PurePosixPath(e["path"]).stem.split("_")[0] for e in selected})}


def acquire_training(root: Path) -> dict:
    """Download only patient-disjoint BioCAS2022 TRAIN pairs and the pinned license."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    tree = json.loads(request_bytes(f"https://api.github.com/repos/{REPOSITORY}/git/trees/{REVISION}?recursive=1"))
    if tree.get("sha") != REVISION or tree.get("truncated"):
        raise ValueError("Unpinned or incomplete source tree")
    selected, counts = eligible_train(tree["tree"])
    entries = {e["path"]: e for e in tree["tree"] if e["type"] == "blob"}
    paths = ["LICENSE", "README.md", "BioCAS2022/README.md"]
    for entry in selected:
        identity = PurePosixPath(entry["path"]).stem
        if not identity.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Unsafe source name")
        paths.extend([entry["path"], f"BioCAS2022/train2022_json/{identity}.json"])

    def download(path):
        entry = entries[path]
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = destination.read_bytes() if destination.exists() else request_bytes(
            f"https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/{path}")
        checksum = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if checksum != entry["sha"] or len(data) != entry["size"]:
            raise ValueError("Source content identity mismatch")
        if not destination.exists():
            with destination.open("xb") as stream:
                stream.write(data)
        return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha1": checksum, "bytes": len(data)}

    receipts = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for position, receipt in enumerate(pool.map(download, paths), 1):
            receipts.append(receipt)
            if position % 100 == 0 or position == len(paths):
                print(f"Verified TRAIN acquisition: {position}/{len(paths)} files", flush=True)
    report = {"source": "SPRSound-BioCAS2022", "revision": REVISION, **counts,
              "official_test_labels_opened": False, "official_test_audio_downloaded": False,
              "selection": "official TRAIN excluding every patient present in official 2022 test filename inventory",
              "files": receipts}
    (root / "receipt.json").write_text(json.dumps(report, indent=2))
    return report


def parse_annotation(document: dict, duration: float) -> tuple[list[dict], list[dict]]:
    """Map released event categories; preserve Normal coverage and multi-label events."""
    if document.get("record_annotation") == "Poor Quality":
        raise ValueError("Poor Quality source must not become normal training data")
    if document.get("record_annotation") not in {"Normal", "CAS", "DAS", "CAS & DAS"}:
        raise ValueError("Unknown recording annotation")
    events, coverage = [], []
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid recording duration')
    for item in document.get("event_annotation", []):
        label = item["type"]
        if label not in MAPPING:
            raise ValueError("Unknown SPRSound event category")
        if isinstance(item['start'], bool) or isinstance(item['end'], bool):
            raise ValueError('Invalid event timestamps')
        start, end = float(item["start"]) / 1000, float(item["end"]) / 1000
        if not all(math.isfinite(x) for x in (start, end)) or not 0 <= start < end <= duration + 1e-6:
            raise ValueError("Invalid millisecond event bounds")
        coverage.append({"start_s": start, "end_s": end, "original_label": label})
        events.extend({"start_s": start, "end_s": end, "label": mapped, "original_label": label} for mapped in MAPPING[label])
    if not coverage:
        raise ValueError("No explicitly annotated event coverage")
    return events, coverage


def acoustic_mask(block: dict, coverage: list[dict], config: dict, duration: float) -> np.ndarray:
    """Supervise acoustic labels only inside explicit events; I/E stay unknown.

    Within an explicitly categorized SPRSound event the seven-class annotation
    is treated as exhaustive for its acoustic categories. Unannotated intervals
    remain unknown. Full-frame containment avoids inventing boundary negatives.
    """
    half = config["n_fft"] / (2 * config["sample_rate"])
    starts, ends = block["times_s"] - half, block["times_s"] + half
    covered = np.zeros(len(starts), dtype=bool)
    for interval in coverage:
        covered |= (starts >= interval["start_s"] - 1e-9) & (ends <= interval["end_s"] + 1e-9)
    mask = np.zeros_like(block["targets"], dtype=np.float32)
    for index, label in enumerate(config["classes"]):
        if label in SOUNDS:
            mask[:, index] = ((covered | (block["targets"][:, index] > 0)) & (ends <= duration + 1e-9)).astype(np.float32)
    return mask
