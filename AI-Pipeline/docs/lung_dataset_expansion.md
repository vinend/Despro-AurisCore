# Lung dataset expansion assessment — 2026-11-10

Scope: PRD section 7 acoustic events and respiratory phases. This is a source
assessment, not authorization to change disease targets, open official test or
mix datasets without auditing their labels and independent groups.

## Why investigate data as well as the model?

The current cache has 28,620 fitting and 17,688 validation windows, but these are
overlapping windows, not independent people. TRAIN stridor prevalence is 1.67%
of supervised frames; validation prevalence is 1.07%. Date groups do not prove
patient independence. Device/source composition differs between partitions.

L006 saved-score inspection reports 94.2% positive inhalation predictions and
97.0% positive crackle predictions on their respective supervised populations.
Both phases are predicted on 1,014,662 / 1,710,259 jointly valid frames (59.3%)
against 18,486 target-overlap frames (1.08%). Crackle ROC-AUC is 0.526 and its F1
gain over always-positive is only 0.00063. These indicate poor discrimination and
decision behavior, but do not establish whether the cause is sample size, labels,
supervision, architecture, optimization or domain shift.

The HF_Lung_V1 authors explicitly discuss single-labeler annotation noise and
environmental interference. See the [original study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8248710/).
This supports annotation review and diversity analysis; it does not prove that
arbitrarily adding files will resolve L006's errors.

## Primary-source shortlist

| Source | Relevant supervision | Proposed role and boundary |
| --- | --- | --- |
| [SPRSound official repository](https://github.com/SJTU-YONGFU-RESEARCH-GRP/SPRSound) | Event start/end in milliseconds; normal, rhonchi, wheeze, stridor, coarse/fine crackle and wheeze+crackle. Filenames include patient ID. Repository identifies CC BY 4.0. | First candidate for sound diversity, especially rhonchi/stridor. Pediatric population and device differences require stratification. This ontology does not provide separate I/E phase labels. |
| [ICBHI official challenge](https://bhichallenge.med.auth.gr/) | 920 recordings / 126 subjects, 6,898 respiratory cycles; crackle/wheeze presence per cycle, plus explicit patient identifiers and split information. Site states research availability. | Useful for wheeze/crackle and cross-device robustness. A cycle-level positive is weak temporal supervision; do not label its entire duration as precise event onset/offset. No rhonchi/stridor or separate I/E targets from these annotations. Retain and review the release terms. |
| [HF_Lung_V1 incremental package / HF_Lung_V2 study](https://www.mdpi.com/2076-3417/12/15/7623) | Expansion of the existing HF source; same broad phase/acoustic purpose. | Authors state incremental labels are proprietary and must be requested. Access and reuse terms remain unresolved. V2 includes V1: deduplicate before use and prevent original validation/test contamination. |

## Integration protocol before any multi-source fitting

1. Pin source revision, training archive identities, checksums, license/attribution
   and released split roles. Inspect public documentation and training annotations
   only; do not open reserved test annotations during development.
2. Audit exact available subtype counts, recording quality, event coverage and
   unique patient/source support. Check cross-version and cross-dataset audio
   duplication before assigning any split. More windows alone is not more subjects.
3. Normalize annotation units explicitly (SPRSound milliseconds -> seconds).
   Propose coarse/fine crackle -> crackle-containing interval and combined
   wheeze+crackle -> both positives only after reviewing the actual release.
   Preserve original labels and mapping version in the manifest.
4. Missing classes remain masked, including I/E on sources without phase labels.
   A missing stridor label is not automatically stridor-negative. Poor-quality
   recordings are not normal examples. Freeze negative-coverage assumptions.
5. Keep `(source_id, patient_id)` groups intact. Audit repeated patients across
   challenge years and preserve official roles, quarantining conflicts rather
   than moving test patients into training. Do not claim independence from IDs alone.
6. Compare HF-only control versus addition of one source's permitted TRAIN data.
   Keep the evaluation population and declared metrics fixed. Reserve a separate
   source/group evaluation before using its results for selection. Do not mix
   cycle-level and event-level boundary metrics.
7. Report per-source/device/population and per-class sensitivity, specificity,
   precision, F1, ROC/PR-AUC, confusion counts, thresholds and localization with
   group-level uncertainty. Use collected, labeled ESP32 audio as a separate
   later robustness evaluation, not an unreviewed training feed.

## Current action

L007–L011 remain controlled HF-only probes. Following explicit authorization,
SPRSound 2022 TRAIN acquisition/mapping is implemented in a separate L012 pilot:
585 quality-eligible recordings / 85 test-disjoint patient IDs add 2,181 windows.
HF validation remains fixed. Acoustic coverage and I/E masking are explicit;
only one added stridor event survives the patient-disjoint selection, so this
does not resolve rare-class scarcity. See [source-addition run](lung_sprsound_training.md).
Existing Heart/Abdomen code, product schema, official tests and model activation
remain unchanged; final candidate adoption is not authorized by training alone.

The HF-only serial probe queue was launched as WSL PID 384 on 2026-11-10;
L007 was active at that startup check. L012 was subsequently launched as WSL
PID 3621 with a bounded GPU allocation; no completed L012 metrics exist at launch.
