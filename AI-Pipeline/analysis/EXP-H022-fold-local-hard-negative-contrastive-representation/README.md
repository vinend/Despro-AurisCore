# H022 preparation (TRAIN only)

H022 tests one added factor on H021: a supervised representation loss at the existing 64-dimensional Stage-1 embedding. The H021 recording-level hard negatives and 2.0 sample weights are reused exactly for their respective outer training folds. No global H021 OOF false-positive identities are used as supervision.

The five H021 inventories were checked against their completed-result SHA-256 hashes, every persisted inner-held recording score, H015 fold roles, H014 declared-site supervision, and the deterministic top-20% rule. Selected counts are 211, 215, 215, 212, and 208. Expected main CNN jobs: five outer-fold Stage-1 fits; no inner mining CNN jobs.

The loss is defined in `protocol.json`. Only source-declared Present recordings enter Stage-1 positive supervision. The participant path remains uniform segment/recording means, StandardScaler, and nested-C balanced L2 LogisticRegression. The H021 OOF threshold is **not** reused; a new TRAIN OOF threshold is selected after all five H022 folds with sensitivity at least 0.90 and maximum F1.

`protocol_sha256.txt` is the lock. `./scripts/start_h022.sh --check` verifies it without training. Only a human may run `./scripts/start_h022.sh` tomorrow. External validation and sealed test remain closed. No H022 metrics exist yet.
