# Lung research models

The [GitHub prerelease](https://github.com/vinend/Despro-AurisCore/releases/tag/lung-research-models) contains one ZIP for each of the 14 completed Lung runs from L006 through L019. The [manifest](manifest.json) lists the classes, files, SHA-256 checksums, and download URL for each run.

Use each `fold-0/model.keras` with that archive's `fold-0/normalization.npz` and the preprocessing configuration in `source.json`. Load the model for inference with `tf.keras.models.load_model(path, compile=False)`. The archives also include best weights, training history, and aggregate development metrics. L019 includes all nine saved epoch weight snapshots.

These are research checkpoints for acoustic findings. Evaluation is development-only and deployment eligibility is false. L001 has no saved model. Model files for L002–L005 were unavailable in the local inventory.

Training used [HF Lung V1](https://gitlab.com/techsupportHF/HF_Lung_V1), documented in [the training guide](../lung_training.md), under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). L012 additionally used the TRAIN partition of [SPRSound 2022](https://github.com/SJTU-YONGFU-RESEARCH-GRP/SPRSound) under CC BY 4.0, as described in [the source audit](../lung_sprsound_training.md). The archives contain model outputs derived from these sources and aggregate metrics. Evaluation group identifiers were replaced with counts.
