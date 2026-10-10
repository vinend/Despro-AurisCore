# Heart inference — step 3

The implementation extends the existing Python pipeline and Next.js backend.
`HeartInferenceBackend` combines existing rhythm/event DSP with a real Keras
Murmur model, using its frozen preprocessing, segmentation and spectrogram
configuration. No augmentation runs at inference. Window sigmoid scores are
averaged per recording, then compared against a recording-level threshold.
Scores are explicitly marked uncalibrated; they are not disease probabilities.
Short recordings do not receive padded Murmur decisions. Model failures leave
independent Heart DSP available and report Murmur as unavailable.

## Package requirements

`heart-murmur-deployment-v1` contains `model.keras`, `source_metadata.json`,
`evaluation.json`, `decision.json`, and a hash/size manifest. The loader checks
archive integrity, tensor shape, binary sigmoid output and preprocessing contract.
The evaluation must bind the exact model and canonical preprocessing hashes,
identify its participant-disjoint validation split, and evaluate the same
recording-level `mean_window_score` rule used at inference. Both classes,
confusion matrix, threshold, dataset/split provenance, model/preprocessing/threshold
versions, and the PRD engineering metrics are required. The decision must identify
an explicitly approved final deployment model. H021 research fold thresholds and
step-1 candidate packages cannot activate this backend.

These checks validate supplied evidence for consistency; they do not independently
prove the dataset provenance or establish clinical validity. No qualifying final
package has been produced from this checkout. Existing research model files are
not automatically promoted. No training or sealed-test evaluation was performed.

Package a final model only after its real evaluation and selection are available:

```powershell
& $analysisPython scripts\prepare_heart_deployment.py `
  --model final-heart.keras --metadata final-heart.json `
  --evaluation recording-validation.json --decision deployment-decision.json `
  --destination artifacts\deployment-packages\heart-v1
```

Packaging refuses existing destinations. No evaluation/approval files or trained
weights are fabricated by this command.

## Existing backend connection

The existing `/api/heart/analyze` endpoint still receives multipart WAV data.
Phase 5 now routes it through the shared retained JSONL worker; the older
`scripts/analyze_heart_wav.py` adapter remains available to one-shot tools. Set server-side
`AURISCORE_HEART_PACKAGE` to the absolute final package directory and
`AURISCORE_PYTHON` to the Python environment with the CNN dependencies installed.
Restart Next.js after changing its environment. The Python adapter reads that
package setting and returns the existing `heart-analysis-v1` response, including
rhythm, cardiac events and Murmur. No separate HTTP service is introduced.
An invalid configured package fails with HTTP 503. With no package configured,
the existing DSP route remains operational with Murmur unavailable.

Phase 5 retains model instances across WebApp requests through the step-2 JSONL
worker, which accepts `--heart-package`. Direct Python callers can register
`heart_backend_definition(package)` on a retained `AnalysisService`. See
`../../WebApp/docs/organ-analysis.md` for lifecycle, app integration and limits.

The WebApp parser preserves optional recording aggregation, window count and
uncalibrated-score fields while retaining compatibility with existing DSP results.

## Verification

Tests exercise frozen tensor parity, resampling, batch inference, one-time loading
per retained backend, all three Heart branches, cached model-load failure,
invalid predictions, short/invalid recordings, incompatible evidence, candidate
rejection, weight tampering and the existing WAV bridge with a configured model.
Deployment approval/evaluation test fixtures are fictional and exist only in
temporary test directories; they are not model performance evidence.
