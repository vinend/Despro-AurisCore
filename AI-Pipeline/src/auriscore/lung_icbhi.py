"""Prepare ICBHI official TRAIN cycle bags for Lung research."""
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path


SPLIT_SHA256 = "5afa11096c3988d8aaefa5164c053c873f718e730fbb286d482f516b01f05c52"
_STEM = re.compile(r"(?P<patient>\d{3})_[A-Za-z0-9]+_[A-Za-z]+_(?:sc|mc)_[A-Za-z0-9]+")


@dataclass(frozen=True)
class CycleBag:
    recording: str
    patient_group: str
    start_seconds: float
    end_seconds: float
    # Order is wheeze, rhonchi, crackle. Rhonchi is unannotated.
    labels: tuple[int, None, int]


def train_recordings(split_bytes: bytes, *, expected_sha256: str = SPLIT_SHA256) -> dict[str, str]:
    """Bind the official split and remove subjects shared by its two roles."""
    if hashlib.sha256(split_bytes).hexdigest() != expected_sha256:
        raise ValueError("Unexpected ICBHI split manifest SHA-256")
    assignments = {}
    test_patients = set()
    for line in split_bytes.decode("ascii").splitlines():
        parts = line.split()
        if len(parts) != 2:
            raise ValueError("Malformed ICBHI split row")
        stem, role = parts
        match = _STEM.fullmatch(stem)
        if match is None or role not in {"train", "test"} or stem in assignments:
            raise ValueError("Invalid or duplicate ICBHI assignment")
        patient = match["patient"]
        assignments[stem] = (patient, role)
        if role == "test":
            test_patients.add(patient)
    train = {stem: f"icbhi2017:{patient}" for stem, (patient, role) in assignments.items()
             if role == "train" and patient not in test_patients}
    if not train or not test_patients:
        raise ValueError("ICBHI split requires TRAIN and TEST metadata")
    return train


def read_cycles(
    directory: Path, recording: str, train: dict[str, str], duration_seconds: float
) -> list[CycleBag]:
    """Read weak labels after checking TRAIN assignment and physical bounds."""
    if recording not in train or _STEM.fullmatch(recording) is None:
        raise ValueError("Only ICBHI TRAIN annotations may be opened")
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Invalid ICBHI recording duration")
    bags = []
    # Official annotations use milliseconds. Allow a sub-millisecond rounding
    # difference at the physical end of the WAV.
    previous_end = 0.0
    for line in (directory / f"{recording}.txt").read_text(encoding="ascii").splitlines():
        parts = line.split()
        if len(parts) != 4:
            raise ValueError("Malformed ICBHI cycle row")
        start, end = map(float, parts[:2])
        crackle, wheeze = parts[2:]
        if (not math.isfinite(start) or not math.isfinite(end)
                or not previous_end <= start < end <= duration_seconds + .001
                or crackle not in {"0", "1"} or wheeze not in {"0", "1"}):
            raise ValueError("Invalid ICBHI cycle bounds or labels")
        bags.append(CycleBag(recording, train[recording], start, min(end, duration_seconds),
                             (int(wheeze), None, int(crackle))))
        previous_end = end
    if not bags:
        raise ValueError("ICBHI TRAIN recording has no cycle annotations")
    return bags
