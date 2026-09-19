# Original datasets

CirCor 1.0.3 belongs in `circor-heart-sound/1.0.3/` here. Run `python scripts/download_dataset.py` from the repository root. The downloader uses the official PhysioNet public S3 distribution, preserves the license and all metadata, and verifies every published SHA256 digest. Existing originals are never overwritten. Resume by rerunning the command; verified files are reused.

If automatic download is unavailable, download the ZIP from https://physionet.org/content/circor-heart-sound/1.0.3/, extract its contents so that `training_data/`, `training_data.csv`, `SHA256SUMS.txt`, and `LICENSE.txt` are directly under the version directory, then run the pipeline. Do not move only the WAVs: participant TXT files are essential for identity and labels.

Data files are ignored by Git. Their file license is ODC Attribution 1.0; see the original LICENSE.txt and `docs/datasets.md`. All processing writes outside this directory.
