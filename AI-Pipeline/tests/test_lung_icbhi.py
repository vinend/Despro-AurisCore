import hashlib

import pytest

from auriscore.lung_icbhi import CycleBag, read_cycles, train_recordings


TRAIN = "101_1b1_Al_sc_Meditron"
TEST = "102_1b1_Al_sc_Meditron"
MIXED_TRAIN = "103_1b1_Al_sc_Meditron"
MIXED_TEST = "103_1b2_Al_sc_Meditron"


def train_manifest():
    split = f"{TRAIN}\ttrain\n{TEST}\ttest\n{MIXED_TRAIN}\ttrain\n{MIXED_TEST}\ttest\n".encode()
    return train_recordings(split, expected_sha256=hashlib.sha256(split).hexdigest())


def test_train_manifest_excludes_any_patient_in_test(tmp_path):
    train = train_manifest()
    assert train == {TRAIN: "icbhi2017:101"}
    # No TEST file exists, so a file-open attempt would produce FileNotFoundError.
    with pytest.raises(ValueError, match="Only ICBHI TRAIN"):
        read_cycles(tmp_path, TEST, train, 3)


def test_cycle_labels_remain_weak_and_rhonchi_unknown(tmp_path):
    (tmp_path / f"{TRAIN}.txt").write_text("0.25 1.50 1 0\n1.50 3.0001 0 1\n")
    assert read_cycles(tmp_path, TRAIN, train_manifest(), 3) == [
        CycleBag(TRAIN, "icbhi2017:101", .25, 1.5, (0, None, 1)),
        CycleBag(TRAIN, "icbhi2017:101", 1.5, 3, (1, None, 0)),
    ]


def test_invalid_split_or_cycle_cannot_pass(tmp_path):
    with pytest.raises(ValueError, match="SHA-256"):
        train_recordings(b"unverified")
    (tmp_path / f"{TRAIN}.txt").write_text("0.25 3.5 1 0\n")
    with pytest.raises(ValueError, match="bounds or labels"):
        read_cycles(tmp_path, TRAIN, train_manifest(), 3)
