# Dataset report

Selected: CirCor DigiScope 1.0.3 public release. [Source](https://physionet.org/content/circor-heart-sound/1.0.3/). Citation: Oliveira et al. (2022), doi:10.13026/tshs-mw03; Oliveira et al., doi:10.1109/JBHI.2021.3137048. License: ODC-By-1.0; original LICENSE.txt preserved with data.

The following counts are measured locally, not inferred from the full cohort description.

```json
{
  "recordings": 7,
  "original_subject_ids": 5,
  "linked_subjects": 5,
  "class_distribution_recordings": {
    "Present": 7
  },
  "class_distribution_subject_ids": {
    "Present": 5
  },
  "sampling_rates": {
    "48000": 7
  },
  "duration_sec": {
    "count": 7.0,
    "mean": 780.4834285714286,
    "std": 497.10219493609736,
    "min": 465.048,
    "25%": 472.44,
    "50%": 519.288,
    "75%": 1013.364,
    "max": 1507.44
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
    "notes": 0,
    "additional_id": 7,
    "subject_group": 0,
    "sha256": 0,
    "quality_flag": 0
  },
  "duplicate_recordings": 0,
  "quality_flags": {
    "ok": 7
  },
  "channels": {
    "1": 3163
  },
  "splits": {
    "test": {
      "subjects": 1,
      "original_subject_ids": 1,
      "recordings": 1,
      "recording_class_counts": {
        "Present": 1
      },
      "subject_class_counts": {
        "Present": 1
      }
    },
    "train": {
      "subjects": 3,
      "original_subject_ids": 3,
      "recordings": 5,
      "recording_class_counts": {
        "Present": 5
      },
      "subject_class_counts": {
        "Present": 3
      }
    },
    "validation": {
      "subjects": 1,
      "original_subject_ids": 1,
      "recordings": 1,
      "recording_class_counts": {
        "Present": 1
      },
      "subject_class_counts": {
        "Present": 1
      }
    }
  }
}
```

## Interpretation and limitations

Murmur labels are participant/visit annotations, not window-local annotations. Unknown annotations remain in the manifest and are excluded from training. Outcome is a separate clinical assessment and is never used as a feature or target. Repeat participants are linked transitively using Additional ID before splitting. Excluded-group counts can overlap active-group counts when one visit has an unknown label and another has a known label; excluded recordings never enter the model. Combined class names in excluded subject counts denote conflicting visit labels. Blank notes and Additional ID fields are optional, not missing required annotations. Conflicting labels across linked visits are excluded. Exact file hashes crossing splits cause failure; perceptually similar recordings are not detected by file hashing. Clipping and low energy are engineering quality flags, not validated quality scores. Data primarily represent young participants from Brazilian screening campaigns and a different recording device than AurisCore. Resampling 4 kHz recordings to 8 kHz does not restore information above 2 kHz. Public-release holdouts are local research splits, not the official hidden Challenge test set. No clinical validity is established.
