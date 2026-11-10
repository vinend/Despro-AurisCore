"""Fail-closed pre-training guards; full training remains unavailable."""
import hashlib
import time
from pathlib import Path

LIMIT = 43200


def verify_hash(path: Path, expected: str) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('Input hash mismatch: '+str(path))


def verify_roles(rows: list[dict]) -> None:
    universe = {r['participant_id'] for r in rows if int(r['fold']) == 1}
    held = []
    if len(universe) != 568:
        raise ValueError('R1 population mismatch')
    for fold in range(1,6):
        part = [r for r in rows if int(r['fold']) == fold]
        if len(part) != 568 or {r['participant_id'] for r in part} != universe or any(r['role'] not in ('fit','early_stop','outer_eval') for r in part):
            raise ValueError('Participant role leakage/omission')
        held += [r['participant_id'] for r in part if r['role']=='outer_eval']
    if len(held)!=568 or set(held)!=universe:
        raise ValueError('Outer overlap/omission')


def claim_output(path: Path) -> None:
    path.mkdir(parents=True,exist_ok=False)


def check_budget(start: float, limit: int = LIMIT) -> None:
    if limit != LIMIT or time.monotonic()-start >= limit:
        raise TimeoutError('Frozen 12 GPU-hour budget exhausted/changed')
