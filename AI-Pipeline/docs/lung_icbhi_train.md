# ICBHI 2017 TRAIN preparation

This Lung research source supports the PRD wheeze and crackle acoustic findings.
ICBHI annotations mark whether each respiratory cycle contains wheeze and crackle.
The adapter keeps cycle-level labels and leaves rhonchi unknown. The cycle bounds
identify the audio to pool for the weak label. They do not locate the sound inside
the cycle. The adapter does not enter the existing frame cache, training runs,
validation sets, or application interfaces.

The [ICBHI challenge organizers](https://bhichallenge.med.auth.gr/ICBHI_2017_Challenge)
make the recordings available for research and request citation of [Rocha et al.
(2019)](https://doi.org/10.1088/1361-6579/ab03ea) in resulting publications. Keep the
source files in a local research directory and outside Git. The staging script
reads the corrected archive mirrored by the authors of [this study](https://doi.org/10.1186/s13634-024-01148-w)
on [Harvard Dataverse](https://doi.org/10.7910/DVN/HT6PKI).

From `AI-Pipeline` in Linux or WSL, supply the [official recording split
file](https://bhichallenge.med.auth.gr/sites/default/files/ICBHI_final_database/ICBHI_challenge_train_test.txt).
The organizer's certificate had expired when this manifest was retrieved. Its
recording roles were cross-checked against the [BTS research implementation's
split](https://github.com/kaen2891/bts/blob/main/data/icbhi_dataset/official_split.txt);
the two copies differ only in one TRAIN recording's device suffix. Use the
corrected official file with SHA-256
`5afa11096c3988d8aaefa5164c053c873f718e730fbb286d482f516b01f05c52`.
Archive transfers use verified HTTPS. The mirror has that recording under its
old device suffix. The staging script maps it to the corrected official name
before applying the TRAIN allowlist.

```bash
PYTHONPATH=src python3 scripts/stage_lung_icbhi_train.py \
  /path/to/official-split.txt /path/to/ignored/icbhi-train-media
```

The official 539/381 recording split includes two subject IDs on both sides.
The adapter excludes their 13 TRAIN recordings, leaving 526 eligible recordings
from 77 subjects. The script reads the archive directory and streams only the
allowlisted WAV/TXT payloads. The test role is used only as split metadata to
exclude shared subjects. Keep `icbhi2017:<patient>` intact when assigning data
roles. Before a source addition experiment, audit duplicate content against
AurisCore's development splits and record verified cycle counts and coverage.
Use the source only for fitting in that experiment and score the frozen
comparison on the existing target-domain validation population.
