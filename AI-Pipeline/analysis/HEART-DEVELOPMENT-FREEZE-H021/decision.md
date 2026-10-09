# Development decision

H021 reduced H020 false positives from 179 to 117 (−62) with FN fixed at 11 and sensitivity 0.90. Specificity rose 0.6092→0.7445, precision 0.3561→0.4583, F1 0.5103→0.6074, ROC-AUC 0.8924→0.9028, and PR-AUC 0.8138→0.8302. It meets the protocol's minimum, strong, and very-strong development criteria; it does not meet breakthrough. The predefined final engineering gate still fails: specificity <0.85, precision <0.65, F1 <0.75, ROC-AUC <0.92, and PR-AUC <0.85. Freeze research; do not start H022 or open external validation/holdout.
