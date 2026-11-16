# L020 Lung interval and data comparison

This research serves the PRD Lung acoustic findings for wheeze, rhonchi and
crackle. The inputs are existing audited log-mel caches. Outputs are frozen
development checkpoints, clip and frame predictions, and a paired comparison.
This experiment does not change the application interface or deployment eligibility.

| Arm | Fitting population | Positive supervision |
| --- | --- | --- |
| frame_hf | HF training fit groups | L017 frame BCE |
| interval_hf | same HF groups | best frame per contiguous known-positive run |
| interval_hf_spr | same HF groups plus audited SPRSound 2022 TRAIN | same interval loss |

Each positive run retains its original frame mass. Known negatives use frame
BCE and unknown frames split runs and carry no loss. All arms reuse the L017
backbone, seed, optimizer and preprocessing. Fitting statistics and class weights
are recomputed for each fitting population. The SPR arm therefore tests the
complete effect of adding that source, including the resulting statistics,
weights and training steps.

Shifted-date HF groups are split with seed 42 into fitting and 20% inner
development groups drawn solely from original TRAIN. HF date groups are not
verified patient identifiers. The inner split selects the checkpoint by macro
clip average precision with patience five, maximum 20 epochs, and thresholds
by per-class maximum F1 from a fixed grid. Record optimizer steps with epoch
metrics. Evaluate the original HF development set after all arms have selected
their thresholds. It has historical research exposure and is not a sealed test.

Evaluation pools maximum scores over complete blocks of 62 consecutive physical
frames (0.992 s score grid). A positive needs a known positive frame, and a
negative needs supervision across the entire block. Overlapping model windows
can contribute overlapping clips. Results apply to the annotated subset and
exclude unknown clip/class combinations. Compare macro F1 and both ordinary and
balanced accuracy, plus precision, recall, specificity and PR-AUC per class.
The engineering targets are 0.70 macro F1 and 0.70 macro accuracy, with 0.70
macro balanced accuracy to verify performance across both label outcomes.

Historical L017 diagnostic on this clip geometry gives macro F1 0.784, ordinary
macro accuracy 0.755 and balanced accuracy 0.626. Crackle specificity is only
0.019. The historical frame thresholds and incomplete annotations limit this
diagnostic. Use the newly trained paired control to estimate the L020 effect.

The authorized standalone WSL run writes status, log and results under
`AI-Pipeline/artifacts/lung-launch/EXP-L020-20261114/`. The execution snapshot
is `~/auriscore-lung-runs/EXP-L020-20261114/`. No official test data enter
this experiment.
