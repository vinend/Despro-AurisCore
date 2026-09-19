# Dataset selection

Sources checked on 2026-09-16. No Kaggle mirrors or mixed-dataset training are used.

| Property | Primary: CirCor DigiScope 1.0.3 | Candidate: PhysioNet/CinC Challenge 2016 1.0.0 |
|---|---|---|
| Authoritative source | [PhysioNet](https://physionet.org/content/circor-heart-sound/1.0.3/) | [PhysioNet](https://physionet.org/content/challenge-2016/1.0.0/) |
| Citation | Oliveira et al. (2022), dataset DOI [10.13026/tshs-mw03](https://doi.org/10.13026/tshs-mw03); article [10.1109/JBHI.2021.3137048](https://doi.org/10.1109/JBHI.2021.3137048) | Liu et al. (2016), *An open access database for the evaluation of heart sound algorithms*, [10.1088/0967-3334/37/12/2181](https://doi.org/10.1088/0967-3334/37/12/2181) |
| File license | ODC Attribution 1.0 | ODC Attribution 1.0 |
| Usage | Public access subject to attribution/license terms; preserve LICENSE.txt | Same; individual software/papers can have separate licenses |
| Subjects/recordings | Public training release: 942 subject IDs, 3,163 recordings; full Challenge cohort: 1,568 participants | Final organizers' paper: 764 training subjects / 3,153 recordings; hidden test 308 / 1,277. Not downloaded or recounted locally |
| Labels | Murmur: Absent/Present/Unknown; separate Normal/Abnormal outcome; murmur descriptors | Normal/abnormal and updated signal-quality annotations |
| Subject identity | Explicit subject ID and Additional ID for repeat visits | No complete patient-ID mapping verified; recording IDs must not be assumed to identify patients |
| Locations | AV, PV, TV, MV, Phc | Multiple collection sites described; uniform per-record location metadata not verified |
| Sampling | Distributed WAVs at 4,000 Hz; verify local files | Distributed WAVs resampled to 2,000 Hz; original acquisition rates vary/not established here |
| Formats/metadata | WAV, WFDB HEA, segmentation TSV, participant TXT, summary CSV | Mono WAV plus reference/quality annotations; heterogeneous source cohorts |
| Approximate size | 558.9 MB uncompressed; ZIP 449.5 MB | Full project 1.1 GB; training.zip listing 181.3 MB |
| Limitations | Pediatric/young population, environmental noise, weak recording labels, repeat visits, hardware shift | Heterogeneous sources, imbalanced labels, uncertain subject linkage; provided validation duplicates training records |

The [2022 Challenge documentation](https://moody-challenge.physionet.org/2022/) establishes the public 942-ID/3,163-recording subset. Counts of linked independent participants are measured by this repository and can be lower than the number of original IDs. The larger full-cohort description must not be reported as the locally evaluated dataset. The 2016 landing page still describes 3,126 recordings in A–E, whereas the [final organizers' paper, Table 1](https://www.cinc.org/archives/2016/pdf/179-154.pdf) reports 3,153 in A–F from 764 subjects. We use that final published description, not a guessed reconciliation. Citation: Clifford et al. (2016), DOI 10.22489/CinC.2016.179-154. It is a possible future external-validation source only after identity and annotation auditing.

CirCor is selected because original audio, murmur annotations, explicit identity links, location and metadata support reproducible participant-wise evaluation. The first task is **murmur absent versus present**, not normal versus abnormal clinical outcome. Unknown labels are retained for future work but excluded from this baseline. Known binary labels that conflict across linked visits are also excluded. Participant labels supervise all their recordings; this is weak supervision because some sites of a positive participant may not contain an audible murmur.

The code downloads directly from the public S3 endpoint advertised by PhysioNet, using the official SHA256SUMS.txt to verify every file. No authentication or license restriction is bypassed. Keep attribution with any derived database, redistribution or publication and read the original license before reuse. This is a research baseline, not evidence of clinical validity.

Additional citations: Reyna et al., *Heart murmur detection from phonocardiogram recordings: The George B. Moody PhysioNet Challenge 2022*, PLOS Digital Health (2023), [10.1371/journal.pdig.0000324](https://doi.org/10.1371/journal.pdig.0000324). PhysioNet platform citation: Goldberger et al. (2000), [10.1161/01.CIR.101.23.e215](https://doi.org/10.1161/01.CIR.101.23.e215); the current PhysioNet page also requests Pollard et al. (2026), [10.1038/s44360-026-00096-z](https://doi.org/10.1038/s44360-026-00096-z).
