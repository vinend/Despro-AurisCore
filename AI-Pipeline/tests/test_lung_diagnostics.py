"""Fictional development diagnostics; no fitting or official-test label reads."""
import json

import numpy as np
import pandas as pd
import pytest

from auriscore.acquisition_lung import digest
from auriscore.lung_diagnostics import diagnose, score_summary


def test_scores_expose_always_positive_baseline_and_phase_conflicts():
    truth = np.array([[1, 0], [1, 0], [0, 1], [0, 0]], dtype=float)
    mask = np.array([[1, 1], [1, 1], [1, 1], [0, 0]], dtype=float)
    scores = np.array([[.8, .7], [.7, .8], [.6, .9], [1, 1]])
    report = score_summary(truth, scores, mask, ["inhalation", "exhalation"], [.5, .5])
    assert report["inhalation"]["always_positive_f1"] == .8
    assert report["inhalation"]["f1_gain_over_always_positive"] == 0
    assert report["inhalation"]["score_distributions"]["negative"]["count"] == 1
    assert report["inhalation"]["score_distributions"]["positive"]["mean"] == pytest.approx(.75)
    assert report["phase_joint"]["predicted_both_positive"] == 3
    assert report["phase_joint"]["truth_both_positive"] == 0


def test_scores_reject_invalid_shapes_masks_and_thresholds():
    y = np.zeros((2, 1))
    for scores, mask, thresholds in ((y + np.nan, y, [.5]), (y, y + .5, [.5]), (y, y, [2]), (y[:, :0], y, [.5])):
        with pytest.raises(ValueError, match="Invalid development"):
            score_summary(y, scores, mask, ["crackle"], thresholds)


@pytest.fixture
def development(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    classes = ["inhalation", "exhalation"]
    config = {"classes": classes, "n_fft": 4, "sample_rate": 100}
    rows, recordings = [], []
    for i, split in enumerate(("train", "validation")):
        np.savez(cache / f"{i}.npz", targets=np.array([[1, 0], [0, 1], [1, 0]]),
                 mask=np.array([[1, 1], [1, 1], [0, 0]]), times_s=np.array([.02, .04, .06]))
        rows.append({"file": f"{i}.npz", "recording_id": str(i), "split": split, "group": str(i)})
        recordings.append({"recording_id": str(i), "split": split, "group": str(i), "device": "fictional", "valid_end_s": .06})
    # Not in the development index. These files must never be parsed.
    (cache / "sealed-test.npz").write_bytes(b"not a cache")
    (tmp_path / "test_label.txt").write_bytes(b"not labels")
    pd.DataFrame(rows).to_csv(cache / "index.csv", index=False)
    pd.DataFrame(recordings).to_csv(tmp_path / "recordings.csv", index=False)
    pd.DataFrame([{"recording_id": str(i), "label": label, "start_s": .01, "end_s": .05}
                  for i in range(2) for label in classes]).to_csv(tmp_path / "events.csv", index=False)
    audit = tmp_path / "audit.json"
    audit.write_text("{}")
    monkeypatch.setattr("auriscore.lung_diagnostics.preflight", lambda *_: (config, pd.DataFrame(rows)))
    # Keep numeric-looking IDs consistent with the real string identities.
    frame = pd.read_csv(tmp_path / "recordings.csv", dtype={"recording_id": str, "group": str})
    frame.recording_id = "r" + frame.recording_id
    frame.to_csv(tmp_path / "recordings.csv", index=False)
    events = pd.read_csv(tmp_path / "events.csv", dtype={"recording_id": str})
    events.recording_id = "r" + events.recording_id
    events.to_csv(tmp_path / "events.csv", index=False)
    for row in rows:
        row["recording_id"] = "r" + row["recording_id"]
    return cache, audit, config


def test_complete_cache_audit_and_bound_saved_scores(development, tmp_path):
    cache, audit, config = development
    exp = tmp_path / "experiment"
    fold = exp / "fold-0"
    fold.mkdir(parents=True)
    source = {"evaluation_role": "development_only", "config": config,
              "index_sha256": digest(cache / "index.csv"), "audit_sha256": digest(audit)}
    (exp / "source.json").write_text(json.dumps(source))
    (fold / "evaluation.json").write_text(json.dumps({"role": "development_only", "classes": config["classes"], "thresholds": [.5, .5]}))
    np.savez(fold / "development_predictions.npz", truth=np.array([[1, 0], [0, 1]]), scores=np.full((2, 2), .7), mask=np.ones((2, 2)))
    result = diagnose(cache, audit, experiment=exp)
    assert result["train_positive_weights"] == {"inhalation": 1., "exhalation": 1.}
    assert result["splits"]["train"]["classes"]["inhalation"]["masked"] == 1
    assert result["mask_checks"]["supervised_tail_frames"] == 0
    assert result["mask_checks"]["masked_positive_cells"] == 2
    assert result["saved_predictions"]["fold-0"]["summary"]["phase_joint"]["predicted_both_positive"] == 2
    assert result["training_started"] is result["official_test_labels_opened"] is False
    source["evaluation_role"] = "final_deployment_candidate"
    (exp / "source.json").write_text(json.dumps(source))
    with pytest.raises(ValueError, match="not a development run"):
        diagnose(cache, audit, experiment=exp)
    source["evaluation_role"] = "development_only"
    source["index_sha256"] = "stale"
    (exp / "source.json").write_text(json.dumps(source))
    with pytest.raises(ValueError, match="not a development run"):
        diagnose(cache, audit, experiment=exp)
