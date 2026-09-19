# Heart murmur screening baseline

> Historical result only (2026-09-16). This test partition has been inspected and is no longer considered an untouched final holdout. Current training code selects its threshold on validation data and does not evaluate a final holdout automatically.

Evaluation ran on real CirCor recordings. Research results; no clinical validity claimed.

Target: participant murmur Absent versus Present; Unknown excluded, outcome not used. Linked Additional IDs stay together in deterministic stratified train/validation/test splits. Preprocessing: mono, 8 kHz polyphase resampling, DC removal, optional filter (see config), peak normalization, 5-second windows at 50% overlap by default. MFCC/delta/log-mel/RMS/centroid/ZCR/statistics are averaged over windows per recording. StandardScaler is fitted on training recordings only, followed by a fixed balanced RBF SVM. This archived run used threshold zero; it predates validation-selected threshold locking.

```json
{
  "status": "real_data_evaluation",
  "target": "subject-level murmur Absent=0 vs Present=1; Unknown excluded",
  "dataset": [
    "CirCor DigiScope 1.0.3"
  ],
  "feature_count": 349,
  "segment_count": 22819,
  "seed": 42,
  "configuration": {
    "seed": 42,
    "dataset_dir": "data/external/circor-heart-sound/1.0.3",
    "sample_rate": 8000,
    "window_seconds": 5.0,
    "overlap": 0.5,
    "filter_enabled": false,
    "filter_low_hz": 20,
    "filter_high_hz": 1000,
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
    "class_weight": "balanced"
  },
  "split_counts": {
    "test": {
      "subjects": 122,
      "original_subject_ids": 133,
      "recordings": 458,
      "recording_class_counts": {
        "Absent": 367,
        "Present": 91
      },
      "subject_class_counts": {
        "Absent": 99,
        "Present": 23
      }
    },
    "train": {
      "subjects": 568,
      "original_subject_ids": 601,
      "recordings": 2070,
      "recording_class_counts": {
        "Absent": 1654,
        "Present": 416
      },
      "subject_class_counts": {
        "Absent": 458,
        "Present": 110
      }
    },
    "validation": {
      "subjects": 122,
      "original_subject_ids": 132,
      "recordings": 448,
      "recording_class_counts": {
        "Absent": 357,
        "Present": 91
      },
      "subject_class_counts": {
        "Absent": 98,
        "Present": 24
      }
    }
  },
  "python": "3.12.10",
  "sklearn": "1.6.1",
  "feature_table_sha256": "ddb86a81d4bc31d6d11489bfe73ca494d7e05e4dc9c5ae114a0f2aca2f11d257",
  "confidence": "Uncalibrated decision margin; not a probability",
  "validation": {
    "recording": {
      "accuracy": 0.796875,
      "precision": 0.5,
      "recall_sensitivity": 0.46153846153846156,
      "macro_f1": 0.6768932038834952,
      "confusion_matrix": [
        [
          315,
          42
        ],
        [
          49,
          42
        ]
      ],
      "class_counts": {
        "Absent": 357,
        "Present": 91
      }
    },
    "subject": {
      "accuracy": 0.8770491803278688,
      "precision": 0.8,
      "recall_sensitivity": 0.5,
      "macro_f1": 0.7711069418386491,
      "confusion_matrix": [
        [
          95,
          3
        ],
        [
          12,
          12
        ]
      ],
      "class_counts": {
        "Absent": 98,
        "Present": 24
      }
    },
    "recording_count": 448,
    "subject_count": 122
  },
  "test": {
    "recording": {
      "accuracy": 0.8471615720524017,
      "precision": 0.6153846153846154,
      "recall_sensitivity": 0.6153846153846154,
      "macro_f1": 0.7600083839865857,
      "confusion_matrix": [
        [
          332,
          35
        ],
        [
          35,
          56
        ]
      ],
      "class_counts": {
        "Absent": 367,
        "Present": 91
      }
    },
    "subject": {
      "accuracy": 0.9016393442622951,
      "precision": 0.8235294117647058,
      "recall_sensitivity": 0.6086956521739131,
      "macro_f1": 0.8205882352941176,
      "confusion_matrix": [
        [
          96,
          3
        ],
        [
          9,
          14
        ]
      ],
      "class_counts": {
        "Absent": 99,
        "Present": 23
      }
    },
    "recording_count": 458,
    "subject_count": 122
  }
}
```

Limitations: labels are weak at recording/window level; some sites may have no audible murmur despite a positive participant label. Recordings contribute equally during training, so participants with more sites contribute more. These local holdouts are not the official Challenge hidden test. No external, prospective, device-transfer or adult-cohort validation. Decision margins are not calibrated confidence. Quality checks do not establish clinical interpretability. Any screening result requires clinician review.
