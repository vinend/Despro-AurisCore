# Dataset report

Selected: CirCor DigiScope 1.0.3 public release. [Source](https://physionet.org/content/circor-heart-sound/1.0.3/). Citation: Oliveira et al. (2022), doi:10.13026/tshs-mw03; Oliveira et al., doi:10.1109/JBHI.2021.3137048. License: ODC-By-1.0; original LICENSE.txt preserved with data.

The following counts are measured locally, not inferred from the full cohort description.

```json
{
  "recordings": 24,
  "original_subject_ids": 24,
  "linked_subjects": 24,
  "class_distribution_recordings": {
    "Absent": 12,
    "Present": 12
  },
  "class_distribution_subject_ids": {
    "Absent": 12,
    "Present": 12
  },
  "sampling_rates": {
    "4000": 24
  },
  "duration_sec": {
    "count": 24.0,
    "mean": 5.0,
    "std": 0.0,
    "min": 5.0,
    "25%": 5.0,
    "50%": 5.0,
    "75%": 5.0,
    "max": 5.0
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
    "notes": 24,
    "additional_id": 24,
    "subject_group": 0,
    "sha256": 0,
    "quality_flag": 0
  },
  "duplicate_recordings": 0,
  "quality_flags": {
    "ok": 24
  },
  "channels": {
    "1": 24
  },
  "splits": {
    "test": {
      "subjects": 4,
      "original_subject_ids": 4,
      "recordings": 4,
      "recording_class_counts": {
        "Absent": 2,
        "Present": 2
      },
      "subject_class_counts": {
        "Absent": 2,
        "Present": 2
      }
    },
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
  }
}
```

## Interpretation and limitations

Murmur labels are participant/visit annotations, not window-local annotations. Unknown annotations remain in the manifest and are excluded from training. Outcome is a separate clinical assessment and is never used as a feature or target. Repeat participants are linked transitively using Additional ID before splitting. Excluded-group counts can overlap active-group counts when one visit has an unknown label and another has a known label; excluded recordings never enter the model. Combined class names in excluded subject counts denote conflicting visit labels. Blank notes and Additional ID fields are optional, not missing required annotations. Conflicting labels across linked visits are excluded. Exact file hashes crossing splits cause failure; perceptually similar recordings are not detected by file hashing. Clipping and low energy are engineering quality flags, not validated quality scores. Data primarily represent young participants from Brazilian screening campaigns and a different recording device than AurisCore. Resampling 4 kHz recordings to 8 kHz does not restore information above 2 kHz. Public-release holdouts are local research splits, not the official hidden Challenge test set. No clinical validity is established.
