# H022 pretrain checklist

- [x] Research checkout branch: `reconcile/research-master-20261009`.
- [x] H021 protocol hash, H015 assignments, H014 supervised recording map checked.
- [x] All five H021 fold inventories match fold result hashes and inner-held score files.
- [x] Outer evaluation participants excluded from selected hard negatives and Stage-1 fit.
- [x] Exact top-20% fit-role Absent selections: 211 / 215 / 215 / 212 / 208.
- [x] No H021 global OOF false-positive list is imported by the H022 worker.
- [x] One synthetic tiny-batch gradient/save/load smoke test passed on CPU.
- [x] Focused H022 tests passed; TensorFlow 2.20.0 and CUDA GPU detected by preflight.
- [x] `./scripts/start_h022.sh --check` passed; no training started.
- [ ] Tomorrow: human explicitly runs `./scripts/start_h022.sh`.
- [ ] After completion: review genuine OOF metrics and do not open validation automatically.

Protocol source hashes include the worker, preflight, launcher, representation module, and unchanged classifier/preprocessing code. Any source change invalidates the lock and requires an explicit protocol revision before training.
