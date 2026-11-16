# L021 frame loss with SPRSound

Research for the PRD Lung wheeze, rhonchi and crackle findings. The candidate
uses the L020 frame-loss control's training settings, adding 2,181 audited
SPRSound windows to 25,590 HF fitting windows. Fit normalization and positive
weights on this combined population. Retain seed 42, batch eight, Adam at
0.001, dropout 0.2, dilation 16, maximum 20 epochs and patience five.

Use the same HF inner groups to select the checkpoint by macro clip PR-AUC
and the three thresholds by maximum class F1. Compare to the saved L020
frame HF control on the same HF development clips. Since L020 results informed
the experiment, this comparison is development evidence. The official test
remains sealed. Findings are for research and do not alter the app interface.

| Label | Development targets |
| --- | --- |
| Wheeze | F1 ≥ 0.81, recall ≥ 0.81, false positive rate ≤ 0.40 |
| Rhonchi | F1 ≥ 0.65, precision ≥ 0.55, recall ≥ 0.75 |
| Crackle | F1 and recall at least as high as the exact L020 control, false positive rate ≤ 0.45 |

Macro targets are F1 at least the L020 control and both ordinary and balanced
accuracy at least 0.70. Threshold selection is kept identical to L020.
ICBHI stays outside this comparison. See the
[L020 protocol](lung_l020_interval_data.md) for masks and clip geometry.
