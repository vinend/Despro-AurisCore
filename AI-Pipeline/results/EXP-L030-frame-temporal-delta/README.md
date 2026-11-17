# Lung L030 research checkpoint

This is the L030 checkpoint with the highest macro-F1 among the compared
L020–L031 runs on the same HF development clips. Epoch 11 was selected by
inner validation from 16 completed epochs. The official test remains sealed.

| Label | Accuracy | F1 |
| --- | ---: | ---: |
| Wheeze | 75.4% | 83.2% |
| Rhonchi | 68.4% | 62.3% |
| Crackle | 64.9% | 76.6% |
| Macro | 69.5% | 74.0% |

Load `best_model.keras` with `compile=False`. Use the Lung feature extraction
settings in `config.json` and apply the saved frequency normalization with
clipping to [-5, 5]. The model computes its temporal delta channel internally.
The thresholds in the config apply to maximum scores over complete 62-frame
clips and were selected on inner validation. See `metrics.json` for class
support, recall, specificity and balanced accuracy.

This package covers wheeze, rhonchi and crackle for research. The current
engineering integration uses L006 for its six-class coverage.
