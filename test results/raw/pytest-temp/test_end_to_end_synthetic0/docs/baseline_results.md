# Heart murmur screening baseline

SYNTHETIC SMOKE TEST ONLY. These numbers are not model performance evidence.

Target: participant murmur Absent versus Present; Unknown excluded, outcome not used. Linked Additional IDs stay together in deterministic stratified train/validation/test splits. Preprocessing: mono, 8 kHz polyphase resampling, DC removal, optional filter (see config), peak normalization, 5-second windows at 50% overlap by default. MFCC/delta/log-mel/RMS/centroid/ZCR/statistics are averaged over windows per recording. StandardScaler is fitted on training recordings only, followed by a fixed balanced RBF SVM. The decision threshold is selected once from linked validation participants, targeting sensitivity >= 0.90 with minimum specificity 0.50. The training command does not evaluate or reveal a final holdout.

```json
{
  "status": "synthetic_smoke_only",
  "target": "subject-level murmur Absent=0 vs Present=1; Unknown excluded",
  "dataset": [
    "CirCor DigiScope 1.0.3"
  ],
  "feature_count": 349,
  "development_segment_count": 20,
  "seed": 42,
  "configuration": {
    "seed": 42,
    "model_type": "svm",
    "dataset_dir": "data/external/circor-heart-sound/1.0.3",
    "sample_rate": 8000,
    "signal_band_max_hz": 2000,
    "window_seconds": 5.0,
    "overlap": 0.5,
    "filter_enabled": false,
    "filter_low_hz": 20,
    "filter_high_hz": 2000,
    "filter_order": 2,
    "n_fft": 512,
    "hop_length": 128,
    "n_mels": 40,
    "n_mfcc": 13,
    "feature_fmax": 2000,
    "train_fraction": 0.7,
    "validation_fraction": 0.15,
    "test_fraction": 0.15,
    "svm_c": 1.0,
    "svm_gamma": "scale",
    "class_weight": "balanced",
    "threshold_target_sensitivity": 0.9,
    "threshold_min_specificity": 0.5,
    "holdout_status": "legacy_exposed"
  },
  "development_split_counts": {
    "train": {
      "subjects": 16,
      "original_subject_ids": 16,
      "recordings": 16,
      "recording_class_counts": {
        "Absent": 8,
        "Present": 8
      },
      "subject_class_counts": {
        "Absent": 8,
        "Present": 8
      }
    },
    "validation": {
      "subjects": 4,
      "original_subject_ids": 4,
      "recordings": 4,
      "recording_class_counts": {
        "Present": 2,
        "Absent": 2
      },
      "subject_class_counts": {
        "Present": 2,
        "Absent": 2
      }
    }
  },
  "python": "3.13.7",
  "sklearn": "1.6.1",
  "development_feature_table_sha256": "892306a34c2aa15053ad4bd1485a555117639455b58045b066662063d7eab5e7",
  "confidence": "Uncalibrated decision margin; not a probability",
  "holdout": {
    "evaluated": false,
    "status": "legacy_exposed",
    "note": "Training does not read holdout labels or scores. Use a new locked external/device holdout for final evaluation."
  },
  "threshold_selection": {
    "threshold": -0.0417265129017787,
    "target_sensitivity": 0.9,
    "minimum_specificity": 0.5,
    "constraints_met": false,
    "selection_unit": "linked participant mean recording score",
    "validation_subject_metrics": {
      "accuracy": 0.5,
      "precision": 0.5,
      "recall_sensitivity": 1.0,
      "specificity": 0.0,
      "negative_predictive_value": 0.0,
      "macro_f1": 0.3333333333333333,
      "confusion_matrix": [
        [
          0,
          2
        ],
        [
          0,
          2
        ]
      ],
      "class_counts": {
        "Absent": 2,
        "Present": 2
      }
    },
    "candidate_count": 4
  },
  "validation": {
    "threshold": -0.0417265129017787,
    "recording": {
      "accuracy": 0.5,
      "precision": 0.5,
      "recall_sensitivity": 1.0,
      "specificity": 0.0,
      "negative_predictive_value": 0.0,
      "macro_f1": 0.3333333333333333,
      "confusion_matrix": [
        [
          0,
          2
        ],
        [
          0,
          2
        ]
      ],
      "class_counts": {
        "Absent": 2,
        "Present": 2
      }
    },
    "subject": {
      "accuracy": 0.5,
      "precision": 0.5,
      "recall_sensitivity": 1.0,
      "specificity": 0.0,
      "negative_predictive_value": 0.0,
      "macro_f1": 0.3333333333333333,
      "confusion_matrix": [
        [
          0,
          2
        ],
        [
          0,
          2
        ]
      ],
      "class_counts": {
        "Absent": 2,
        "Present": 2
      }
    },
    "recording_count": 4,
    "subject_count": 4
  }
}
```

Limitations: labels are weak at recording/window level; some sites may have no audible murmur despite a positive participant label. Recordings contribute equally during training, so participants with more sites contribute more. The historical local test result was already inspected and is not a fresh holdout. A newly collected or external locked dataset is required. No external, prospective, device-transfer or adult-cohort validation. Decision margins are not calibrated confidence. Quality checks do not establish clinical interpretability. Any screening result requires clinician review.
