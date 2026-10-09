# Dataset report

Selected: CirCor DigiScope 1.0.3 public release. [Source](https://physionet.org/content/circor-heart-sound/1.0.3/). Citation: Oliveira et al. (2022), doi:10.13026/tshs-mw03; Oliveira et al., doi:10.1109/JBHI.2021.3137048. License: ODC-By-1.0; original LICENSE.txt preserved with data.

The following counts are measured locally, not inferred from the full cohort description.

```json
{
  "recordings": 3163,
  "original_subject_ids": 942,
  "linked_subjects": 872,
  "class_distribution_recordings": {
    "Absent": 2391,
    "Present": 616,
    "Unknown": 156
  },
  "class_distribution_subject_ids": {
    "Absent": 695,
    "Present": 179,
    "Unknown": 68
  },
  "sampling_rates": {
    "4000": 3163
  },
  "duration_sec": {
    "count": 3163.0,
    "mean": 22.87030121719886,
    "std": 7.282948441124063,
    "min": 5.152,
    "25%": 19.056,
    "50%": 21.456,
    "75%": 29.392,
    "max": 64.512
  },
  "missing_fields": {
    "dataset_source": 0,
    "subject_id": 0,
    "recording_id": 0,
    "file_path": 0,
    "label": 0,
    "murmur_label": 0,
    "outcome_label": 0,
    "auscultation_location": 0,
    "original_sampling_rate": 0,
    "duration_sec": 0,
    "split": 0,
    "license": 0,
    "notes": 2976,
    "additional_id": 2691,
    "subject_group": 0,
    "sha256": 0,
    "quality_flag": 0
  },
  "duplicate_recordings": 0,
  "quality_flags": {
    "ok": 3143,
    "clipping": 20
  },
  "channels": {
    "1": 3163
  },
  "splits": {
    "excluded": {
      "subjects": 71,
      "original_subject_ids": 76,
      "recordings": 187,
      "recording_class_counts": {
        "Unknown": 156,
        "Present": 18,
        "Absent": 13
      },
      "subject_class_counts": {
        "Unknown": 67,
        "Absent+Present": 4
      }
    },
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
  }
}
```

## Interpretation and limitations

Murmur labels are participant/visit annotations, not window-local annotations. Unknown annotations remain in the manifest and are excluded from training. Outcome is a separate clinical assessment and is never used as a feature or target. Repeat participants are linked transitively using Additional ID before splitting. Excluded-group counts can overlap active-group counts when one visit has an unknown label and another has a known label; excluded recordings never enter the model. Combined class names in excluded subject counts denote conflicting visit labels. Blank notes and Additional ID fields are optional, not missing required annotations. Conflicting labels across linked visits are excluded. Exact file hashes crossing splits cause failure; perceptually similar recordings are not detected by file hashing. Clipping and low energy are engineering quality flags, not validated quality scores. Data primarily represent young participants from Brazilian screening campaigns and a different recording device than AurisCore. Resampling 4 kHz recordings to 8 kHz does not restore information above 2 kHz. Public-release holdouts are local research splits, not the official hidden Challenge test set. No clinical validity is established.
