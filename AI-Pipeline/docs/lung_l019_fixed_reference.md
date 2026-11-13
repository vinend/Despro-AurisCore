# L019 fixed-reference training — 2026-11-10

Explicit user-authorized GPU launch after implementation/full-cache verification.
Research scope serves the PRD Lung acoustic findings, not a deployed model or a
removal of phase/respiratory requirements. Official test stays sealed.

ID: `EXP-L019-fixed-reference`. Control: `EXP-L017-window-objective`.
The material change is the verified Lung-only fixed log-mel reference/floor and
its necessarily refitted TRAIN normalization. Per-epoch trajectory evidence is
observational: it saves weights/predictions and does not advance the optimizer.
No learning-rate, architecture, objective, class-weight estimator or split change
is combined with this comparison.

Frozen settings: wheeze/rhonchi/crackle, seed42, 269,315 parameters, dilation16,
dropout .2, Adam LR .001, zero weight decay, no feature augmentation, batch8,
maximum50 epochs, val_loss patience8 with best restoration, all 28,620 fitting
windows and 17,688 held-out development windows. Date groups remain 94/24;
patient independence is unverified. All-class original supervised TRAIN scope
is retained for normalization. The class weights match L017.

`configs/lung_fixed_reference_experiment.json` predeclares the factor, single-run
limit, maximum-F1 threshold grid/rule, stopping and research review gate against
L017. No automatic promotion or further adaptive run. Epoch probe thresholds
.5 are frozen diagnostic constants; they do not replace final threshold selection
or affect the stop metric. At most16 recordings/device/fitting partition supply
fixed probes; their metrics are diagnostic samples, not full population results.

Before fitting, the standalone supervisor checks the completed L017 control,
policy equality apart from v7 telemetry, config equality apart from feature policy,
verification/index/config/audit hashes and held-out window order. It freezes
code/config/launcher/package/control hashes and runtime inventory in protocol.json.
After fitting it runs diagnostics, localization, strict deterministic GPU reload
parity, pipeline/source analysis, exact label/mask population verification and
per-class comparison/research-gate review. Any failure is preserved in status/logs;
there is no fallback run or automatic deployment.

Fresh paths:

- Snapshot: `/home/vinend/auriscore-lung-runs/EXP-L019-20261110`.
- Cache: `/home/vinend/auriscore-lung-fixed-reference-20261110/cache/5548481b0d3e371c65f20f6790b6c958b049890cfbf528dc43e310c33967e9c7`.
- Results: `results/EXP-L019-fixed-reference/`.
- Protocol/status/logs: `artifacts/lung-launch/EXP-L019-20261110/`.
- Training log: `training.log` under that evidence directory.
- Per-epoch evidence: `results/EXP-L019-fixed-reference/fold-0/trajectory/`.

Prelaunch evidence remains `artifacts/lung-launch/fixed-reference-checks-20261110/`:
all46,308 non-feature payloads match the old cache, 38,590 overlap pairs have zero
feature disagreement, preflight and actual GPU finite-gradient/trajectory smoke
checks pass. Focused checks pass; broader checks retain a known pre-existing
Abdomen validator failure reproduced on Git HEAD. It is outside this fitting path.

No new performance result is available at launch. The fixed-reference feature
inconsistency is corrected, but improved generalization and later best epochs
are not guaranteed. Old checkpoints/caches and Heart/Abdomen paths are preserved.
After startup verification, stop active agent polling and inspect only on later
status requests through saved artifacts.

Startup observed: supervisor WSL PID **26483**, trainer PID **26498**. Frozen
protocol exists; status is `running`, stage `training`. Real-cache preflight
passes 46,308 windows and trainer runtime explicitly reports RTX 5060 / GPU:0,
deterministic operations enabled, TF32 disabled. Initial startup reached TRAIN
statistics; there are no epoch/performance results claimed in this launch note.
