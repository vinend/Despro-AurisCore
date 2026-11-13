# H021 versus H022 paired TRAIN OOF uncertainty — 2026-10-28

## Question and provenance

H021 has the best observed FP/F1 point estimate among these two aligned 568-participant CirCor TRAIN development experiments, while H022 has one fewer FN and its five Stage-1 checkpoints remain available. This read-only audit asks how many **same-participant** errors changed, and how uncertain their observed metric differences are. It does not select a new threshold, fit a model, infer temporal Murmur boundaries, open external validation or sealed test, or alter the demo. Human audio review is `CLOSED_UNAVAILABLE`.

The [frozen config](../configs/h021_h022_paired_uncertainty_v1.json) preceded outcome calculation. The [runner](../scripts/audit_h021_h022_paired_uncertainty.py) verifies H021's LF-normalized OOF SHA-256 `9b41bc0258d763902f311369348612c7177adac28f5e1fe77ef21540c72a16f1` and H022's native OOF SHA-256 `109b39a45032a68be80b94d629e13e2c04323d8c85bdb996a983feb4264127a9`, plus each protocol SHA-256, exact participant IDs, fold IDs, official labels, original thresholds and reported confusion counts. H021's file has Windows-style CRLF bytes in the accessible WSL checkout, so the runner normalizes line endings only for its historical freeze-hash check; it never changes values. All 568 identities and original counts matched.

The output is immutable and Git-ignored at `AI-Pipeline/data/processed/h021_h022_paired_uncertainty_v1/`. Its `summary.json` SHA-256 is `dca118ea78ae94acdcfc561084d5a4f43f49b7fb4c6feff0b967d5d9f76f574b`; runner SHA-256 is `07a14f7ef1adbb5ef4fa7353cd9538ba79263db7bc6c23d02c84f07db2a0cd5c`. The participant-stratified paired bootstrap uses seed 20261028 and 10,000 resamples, preserving each participant's paired H021/H022 decisions and the 458 Absent / 110 Present class counts. Percentile intervals describe sampling uncertainty on this inspected TRAIN cohort; they are not external validation or a multiplicity-adjusted superiority test.

## Frozen decision comparison

| Model | Participants | Threshold | TN | FP | FN | TP | Sensitivity | Specificity | Precision | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H021 | 568 | 0.1922534565 | 341 | 117 | 11 | 99 | 0.9000 | 0.7445 | 0.4583 | 0.6074 |
| H022 | 568 | 0.1680918156 | 335 | 123 | 10 | 100 | 0.9091 | 0.7314 | 0.4484 | 0.6006 |

Among the 458 officially Absent participants, **16** were FP only under H021 and **22** were FP only under H022. Among the 110 Present participants, **3** were FN only under H021 and **2** only under H022. These discordances explain the net six-FP reduction and one-FN increase under H021; they do not identify which model is clinically right on any individual case.

| Metric, H021 minus H022 | Point difference | Paired bootstrap 95% interval |
| --- | ---: | ---: |
| Sensitivity | -0.0091 | [-0.0455, 0.0273] |
| Specificity | 0.0131 | [-0.0131, 0.0393] |
| Precision | 0.0099 | [-0.0183, 0.0376] |
| F1 | 0.0068 | [-0.0234, 0.0357] |

All intervals include zero. H021 has the better observed FP, specificity, precision and F1 point estimates, but this paired cohort does **not** establish a robust improvement over H022. H022's one-FN advantage likewise has substantial uncertainty. H021's missing five checkpoints prevent replay/deployment; H022's available fold models are research artifacts, not a separately trained final model. Neither is deployment ready, and neither was trained or validated for exact Murmur onset/offset.

The next autonomous action remains independent source/target/participant provenance verification. No new training, ensemble, model promotion or threshold revision is justified by this already inspected paired comparison. To reproduce, use WSL Python 3 on the Windows-mounted repository with a fresh audit ID/output path; the runner refuses to overwrite the completed result.
