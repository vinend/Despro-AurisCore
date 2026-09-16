"""Metadata correctness and subject leakage regression tests."""
import pandas as pd
import pytest
from auriscore.dataset import link_subjects, build_manifest
from auriscore.splitting import assign_splits, assert_no_leakage, split_summary
from auriscore.validation import MANIFEST_COLUMNS, validate_manifest


def manifest_fixture():
    rows = []
    for i in range(40):
        for site in ("AV", "MV"):
            row = dict.fromkeys(MANIFEST_COLUMNS, "")
            label = "Present" if i % 2 else "Absent"
            row.update(subject_id=str(i), subject_group=str(i), recording_id=f"{i}_{site}",
                       sha256=f"hash_{i}_{site}", label=label, murmur_label=label, quality_flag="ok")
            rows.append(row)
    return pd.DataFrame(rows)


def test_deterministic_split_no_leakage(config):
    frame = manifest_fixture()
    split = assign_splits(frame, config)
    other = assign_splits(frame.sample(frac=1, random_state=9), config)
    assert split.set_index("recording_id").split.to_dict() == other.set_index("recording_id").split.to_dict()
    assert_no_leakage(split)
    assert set(split.split) == {"train", "validation", "test"}
    broken = split.copy()
    broken.loc[0, "split"] = "test" if broken.loc[1, "split"] != "test" else "train"
    with pytest.raises(ValueError, match="Leakage"):
        assert_no_leakage(broken)


def test_repeat_subject_ids_and_conflicting_labels(config):
    frame = manifest_fixture()
    frame.loc[frame.subject_id == "0", "additional_id"] = "2"
    frame.loc[frame.subject_id == "2", "additional_id"] = "4"
    linked = link_subjects(frame)
    assert linked[linked.subject_id.isin(["0", "2", "4"])].subject_group.nunique() == 1
    result = assign_splits(linked, config)
    assert result[result.subject_id.isin(["0", "2", "4"])].split.nunique() == 1
    frame.loc[frame.subject_id == "0", "additional_id"] = "1"
    result = assign_splits(link_subjects(frame), config)
    assert result[result.subject_id.isin(["0", "1"])].split.eq("excluded").all()
    assert split_summary(result)["excluded"]["subject_class_counts"]["Absent+Present"] == 1


def test_manifest_validation(config):
    frame = manifest_fixture()
    validate_manifest(frame, require_subjects=True)
    with pytest.raises(ValueError, match="columns"):
        validate_manifest(frame.drop(columns="license"))
    frame.loc[0, "subject_id"] = ""
    with pytest.raises(ValueError, match="Missing subject ID"):
        assign_splits(frame, config)
    frame = manifest_fixture()
    frame.loc[0, "label"] = "Normal"
    with pytest.raises(ValueError, match="label"):
        validate_manifest(frame)


def test_unknown_exclusion(config):
    frame = manifest_fixture()
    frame.loc[frame.subject_id == "0", ["label", "murmur_label"]] = "Unknown"
    split = assign_splits(frame, config)
    assert split[split.subject_id == "0"].split.eq("excluded").all()


def test_duplicate_hash_leakage(config):
    frame = assign_splits(manifest_fixture(), config)
    train = frame[frame.split == "train"].index[0]
    test = frame[frame.split == "test"].index[0]
    frame.loc[test, "sha256"] = frame.loc[train, "sha256"]
    with pytest.raises(ValueError, match="sha256"):
        assert_no_leakage(frame)


def test_bad_file_logged_manifest(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "1_AV.wav").write_bytes(b"broken")
    frame = build_manifest(tmp_path, folder)
    assert len(frame) == 1
    assert frame.iloc[0].subject_id == ""
    assert frame.iloc[0].quality_flag == "invalid"
    assert "Missing subject" in frame.iloc[0].notes


def test_invalid_orphan_does_not_block_valid_dataset(config):
    frame = manifest_fixture()
    orphan = dict.fromkeys(MANIFEST_COLUMNS, "")
    orphan.update(recording_id="bad_orphan", quality_flag="invalid")
    frame = pd.concat([frame, pd.DataFrame([orphan])], ignore_index=True)
    result = assign_splits(frame, config)
    assert result.iloc[-1].split == "excluded"
    assert_no_leakage(result)


def test_combined_silent_quality_flags_excluded(config):
    frame = manifest_fixture()
    frame.loc[0, "quality_flag"] = "silent;short"
    assert assign_splits(frame, config).loc[0, "split"] == "excluded"
