# H022 operations tomorrow

H022 is a TRAIN-only development experiment. External validation and sealed test stay closed. Do not use H021 OOF FP identities as training input.

Run from the research checkout on branch `reconcile/research-master-20261009`:

```bash
cd /home/rowen/projects/Despro-AurisCore/AI-Pipeline
./scripts/start_h022.sh --check
```

The precheck verifies branch/path, locked SHA-256, all five H021 mining inventories, TRAIN artifacts, Python/TensorFlow 2.20, CUDA GPU, systemd user manager, and duplicate service prevention. It does not train.

Start **only after deliberate human approval tomorrow**:

```bash
cd /home/rowen/projects/Despro-AurisCore/AI-Pipeline
./scripts/start_h022.sh
```

Status, a single log inspection, and optional GPU inspection:

```bash
systemctl --user status auriscore-h022-fold-local-hard-negative-contrastive-representation.service
tail -n 60 .runtime/h022-fold-local-hard-negative-contrastive-representation.stdout.log
nvidia-smi
```

If absolutely necessary, a human can stop safely with:

```bash
systemctl --user stop auriscore-h022-fold-local-hard-negative-contrastive-representation.service
```

Result directory: `results/EXP-H022-fold-local-hard-negative-contrastive-representation/`. TRAIN OOF metrics and protocol remain under `analysis/EXP-H022-fold-local-hard-negative-contrastive-representation/`. The process uses the existing resumable systemd convention. Expect a long GPU job measured in hours because five new Stage-1 CNNs train; inner mining CNNs are reused from H021 provenance and are not repeated.
