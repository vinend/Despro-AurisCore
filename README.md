# AurisCore Digital Stethoscope

AurisCore is a university capstone cyber-physical stethoscope research prototype. The intended acquisition path is body sound → MEMS microphone/analog front-end → ESP32-S3 (mono ADC near 8 kHz) → BLE → smartphone → offline signal processing and AI → clinical decision support. Heavy AI processing belongs on the phone for the current design. Optional backend/tele-auscultation comes later.

The repository combines an executable **heart-sound/PCG dataset pipeline and SVM murmur-screening baseline in Python** with a **Next.js web prototype and WebSocket mock device**. The web prototype currently displays simulated PCG data and simulated classifications; it is not yet connected to the Python model. Heart-only model scope allows us to verify provenance, signal processing and participant separation before adding other modalities. Lung and abdomen classifiers, CNNs, embedded firmware, and production mobile integration are not implemented here.

Verified run (2026-09-16): **21 tests passed**; full real CirCor pipeline completed with 22,819 windows and 349 features. Participant test sensitivity was **60.87%** (9 of 23 positive participants missed), despite 90.16% accuracy. See the [engineering handoff](docs/engineering_summary.md) and [complete baseline results](docs/baseline_results.md). These results establish an executable baseline, not clinical readiness.

Research screening only. Outputs are not confirmed diagnoses. Neither a murmur-absent screening result nor a decision margin rules out disease. Every screening result requires clinician review; no clinical validity is claimed.

## Existing work and structure

Earlier proposals and the architecture document generator are preserved. Some historical documents discuss Wi-Fi/TinyML alternatives; the architecture above governs this milestone. See [initial inspection](docs/repository_inspection.md).

```text
configs/heart_baseline.yaml       Fixed, versioned baseline settings
src/auriscore/                    Acquisition, validation, DSP, features, splits, SVM, inference
scripts/                         Executable stages and offline WAV screening
tests/                           Unit, leakage and synthetic end-to-end tests
data/external/                    Unchanged original release and license (ignored)
data/raw/                        Reserved for future device captures (ignored)
data/interim/                    Reserved for intermediate data (ignored)
data/processed/                  Arrays, window index and feature table (ignored)
metadata/                       Manifest, quality checks and error logs
artifacts/dataset_analysis/      Measured statistics, duplicates and plots
artifacts/models/               Saved sklearn pipeline (ignored)
artifacts/metrics/              Metrics and held-out predictions
artifacts/figures/              Participant confusion matrix
docs/                          Reports, dataset research and existing architecture documents
tools/, terbaru/, *.pdf, *.docx  Preserved previous work
```

## Environment

Use Python 3.12 (tested); 3.11–3.13 are allowed by package metadata.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

On Linux/macOS activate with `source .venv/bin/activate`. Source-tree scripts work without package installation; `python -m pip install -e .` is optional. Direct dependencies are pinned in `requirements.txt`; `requirements-lock.txt` records the complete tested environment. To reproduce transitive versions, install with `python -m pip install -r requirements-lock.txt`.

On this Windows workspace, an ignored local Python runtime is also available: replace `python` with `.runtime\python\python.exe`. This avoids requiring a system-wide installation. It is a local convenience, not a tracked dependency.

## Dataset and target

The sole primary dataset is [CirCor DigiScope 1.0.3 on PhysioNet](https://physionet.org/content/circor-heart-sound/1.0.3/), licensed under **Open Data Commons Attribution 1.0**. Cite Oliveira et al. (2022), DOI `10.13026/tshs-mw03`, and the source article DOI `10.1109/JBHI.2021.3137048`. Keep the original license and attribution with derived data. See [dataset comparison, terms and citations](docs/datasets.md).

The public release contains 3,163 recordings and 942 original subject IDs. The pipeline measures independent participant groups using Additional ID links; these counts must not be confused with the full research cohort. PhysioNet 2016 was investigated but is not combined with CirCor.

Target: **murmur Absent (0) versus Present (1)**. Unknown labels are retained in the manifest and excluded from training/evaluation. Clinical outcome is a separate preserved field, never a feature or target. Positive participant labels can include recordings at sites without audible murmur; this baseline explicitly uses weak recording-level supervision.

```powershell
python scripts/download_dataset.py
python scripts/run_pipeline.py
# Or acquire and run together:
python scripts/run_pipeline.py --download
```

Download uses PhysioNet's officially advertised public S3 endpoint, bounded concurrent connections, retries and published SHA-256 verification. Roughly 559 MB of source data is downloaded; allow several GB for runtime, processed audio and features. Interrupted downloads can be resumed by rerunning. Existing source files are never replaced; changed originals cause a clear failure. Manual download instructions are in [data/external/README.md](data/external/README.md). Missing data produces an actionable message and exit code 2; it does not generate invented metrics.

## Stages and manifest

```powershell
python scripts/build_manifest.py
python scripts/analyze_dataset.py
python scripts/preprocess_dataset.py
python scripts/extract_features.py
python scripts/train_baseline.py
```

All commands accept `--config configs/heart_baseline.yaml` and `--root <repository>`. Paths in configuration and manifests are relative to the repository root. The manifest records:

| Fields | Meaning |
|---|---|
| dataset_source, subject_id, recording_id, file_path | Original provenance and repository-relative audio path |
| label, murmur_label, outcome_label | Explicit murmur target, original murmur label and separate outcome |
| auscultation_location, original_sampling_rate, duration_sec | Source site and measured audio properties |
| split, license, notes | Assigned partition, usage attribution and exclusions/errors |
| additional_id, subject_group | Original repeat-visit link and canonical transitive participant group |
| sha256, quality_flag | Original file digest and engineering quality warnings |

Missing metadata stays blank. Missing identities are flagged; splitting fails rather than assuming independence. Decoding failures, empty audio, NaN/Inf, channels, duration, sampling rate, RMS and clipping ratio are logged per file. Duplicate hashes are reported. Invalid/silent files and unknown labels are excluded; other quality flags remain available for review. The clipping threshold is absolute amplitude ≥0.999, flagged when more than 1% of samples reach it; silence RMS <1e-7. These are engineering defaults.

## Signal processing and leakage prevention

Audio is converted to mono, polyphase-resampled to 8 kHz, DC-centered, optionally filtered, peak-normalized and segmented into 5-second windows with 50% overlap. Filtering is **off** by default; optional 20–1000 Hz second-order Butterworth cutoffs are engineering choices, not medically validated constants. A recording shorter than five seconds gets one zero-padded window with its valid sample count retained. Incomplete tails of longer recordings are discarded.

Features include 13 MFCCs, 13 delta MFCCs, 40 log-mel bands, RMS, spectral centroid and zero-crossing rate, summarized by mean/std/median/min/max, plus four amplitude/temporal statistics: **349 features** per window. Mel features stop at 2 kHz because upsampling the 4 kHz source cannot create higher-frequency information. Windows are averaged into one feature vector per recording before training.

Before segmentation, subject IDs and Additional IDs are linked transitively. Seed 42 creates stratified 70/15/15 train/validation/test participant splits. All recordings from a linked participant stay together; inconsistent linked-visit binary labels are excluded. Automated checks fail on overlap of subjects, linked groups, recording IDs or exact file hashes across splits. Feature provenance binds each stage to the manifest and configuration; rerun upstream stages if either changes.

The model is an sklearn `Pipeline(StandardScaler, SVC)` with RBF kernel, C=1, gamma=`scale`, class weights=`balanced`. Scaling is fitted only on training recordings. No hyperparameter tuning is performed. Validation is evaluated first; test is used only for the final fixed-model evaluation. The main metrics use one decision per linked participant (mean recording margin, threshold zero); recording metrics are secondary. Repeatedly inspecting this test split while changing the model would invalidate its role as an untouched holdout.

## Outputs and offline screening

- [Dataset report](docs/dataset_report.md): measured counts, distributions, quality, missing values, duplicates and split statistics.
- [Baseline results](docs/baseline_results.md): real evaluation status, model settings, metrics and limitations.
- `metadata/dataset_manifest.csv`, `metadata/audio_validation.csv`, `metadata/*_errors.csv`.
- `data/processed/audio/*.npy`, `segments.csv`, `features.csv`, stage provenance JSON.
- `artifacts/dataset_analysis/`: distribution PNGs, statistics JSON and duplicates CSV.
- `artifacts/models/heart_svm.joblib`, `artifacts/metrics/baseline_metrics.json`, validation/test predictions and `artifacts/figures/confusion_matrix.png`.

```powershell
python scripts/predict.py path/to/recording.wav
```

Inference returns a murmur screening result, quality flags and an **uncalibrated decision margin**, not a probability or diagnosis. Invalid/silent audio yields “unable to screen.” Only load trusted locally generated joblib models. Model inference runs offline once dependencies and the model are available.

## Tests and limitations

`python -m pytest -q` covers audio loading, mono conversion, resampling, segmentation, feature shape, deterministic splitting, leakage, repeat identities, unknown exclusion, corrupt/empty/nonfinite audio, manifest validation and a synthetic end-to-end smoke run. Synthetic test artifacts stay in temporary directories, are explicitly labeled, and provide no evidence of screening performance.

CirCor's cohort/device/environment may differ substantially from future AurisCore recordings. Participant labels are not precise window labels. No heart-cycle segmentation, learned quality gate, calibrated confidence, external validation, prospective evaluation or clinical validation is implemented. File hashes detect exact byte duplicates, not acoustically similar recordings. The internal held-out test is not the official Challenge hidden test. Longer windows do not increase independent participant count. This milestone provides a desktop Python reference, not a deployed smartphone model.

## Roadmap

1. Heart PCG dataset pipeline.
2. SVM baseline.
3. CNN baseline.
4. CNN INT8 quantization.
5. TensorFlow Lite smartphone inference.
6. ESP32-S3 BLE integration.
7. Flutter application integration.
8. Lung mode.
9. Abdomen mode.

Before phase 3, review the baseline errors and quality exclusions with the project team and preserve a fresh evaluation strategy for future model comparisons.
## Web app prototype (Pekan 3)

Prototipe layar utama untuk stetoskop digital AurisCore (ESP32-S3).
Seluruh data PCG dan hasil klasifikasi pada prototipe ini adalah **simulasi**
dari `mock-device` — bukan perangkat keras sungguhan dan bukan model AI.

## Arsitektur

```
[Browser]                        [Komputer dev]                 [Masa depan]
 React (Next.js)  ──WebSocket──►  mock-device   ──diganti──►  firmware ESP32-S3
 route / (port 3000)  JSON        (port 8081)                memakai protokol sama
        │                                ▲
        └── ws(s)://<host>/ws?XTransformPort=8081 ──┘
            (gateway Caddy meneruskan ke port 8081)
```

- Frontend tidak memuat logika tiruan apa pun: ia terhubung lewat WebSocket
  sungguhan ke `mock-device` dengan protokol (seksi 5 rencana) yang kelak
  ditiru firmware ESP32.
- Saat ESP32 asli tersedia, arahkan aplikasi ke alamat perangkat lewat
  parameter URL `?device=ws://...` tanpa perubahan kode.
- Kontrak data: JSON, timestamp epoch milidetik, PCM int16 signed, 1 kanal,
  2000 Hz, paket 100 sampel tiap 50 ms. Detail lengkap:
  `mini-services/mock-device/README.md` (referensi tim firmware).

## Menjalankan (dua proses)

Pastikan dependensi sudah terinstal (`npm install` di root dan di `mini-services/mock-device`).

```bash
# Terminal 1 — perangkat tiruan (port 8081)
cd mini-services/mock-device
npm run dev            # atau dengan chaos test: npx tsx index.ts --chaos

# Terminal 2 — aplikasi web (port 3000)
cd ../..               # kembali ke root proyek jika dari mock-device
npm run dev
```

Buka aplikasi di browser:
- Akses lokal langsung: `http://localhost:3000/?device=ws://localhost:8081`
- Atau lewat gateway Caddy/preview jika di sandbox: `http://<host>:3000` (otomatis menyambung ke `ws(s)://<host>/ws?XTransformPort=8081`).
- Indikator koneksi ada di header. Uji koneksi langsung ke ESP32 fisik: `.../?device=ws://<alamat-perangkat>/ws`.

## Status fitur (DoD pekan 3)

| Fitur | Status |
|---|---|
| Responsif desktop & ponsel | selesai |
| Koneksi WebSocket + validasi pesan | selesai |
| Gelombang PCG bergulir real-time (canvas, jendela 5 dtk) | selesai |
| Kontrol dua arah: mode organ + BPM 60–100 | selesai |
| Alur rekam 10 dtk → memproses 1,5 dtk → kartu hasil (tiruan) | selesai |
| Riwayat sesi dalam memori | selesai |
| Reconnect otomatis (1 dtk → 2 dtk → maks 5 dtk) + gap fill hening | selesai |
| Badge koneksi: Terputus / Terhubung, simulasi / Perangkat | selesai |
| Unit test (seksi 12) | **tidak ditulis** — kebijakan lingkungan tanpa kode test; digantikan verifikasi manual browser, lihat DECISIONS.md |
| Stretch: PWA, pemutaran audio, JSON vs biner | belum (stretch, seksi 11) |

## Verifikasi manual (ringkas)

1. Jalankan dua proses di atas, buka aplikasi.
2. Badge "Terhubung, simulasi" muncul; gelombang bergulir mulus.
3. Geser slider BPM → laju denyut berubah (status perangkat ikut).
4. Ganti mode organ → buffer reset setelah `mode_ack`, label berubah.
5. Rekam → 10 detik → "Memproses…" → kartu hasil berlabel "hasil simulasi".
6. Matikan mock-device (Ctrl+C) → badge "Terputus"; nyalakan lagi → koneksi
   pulih otomatis dan gelombang lanjut.
7. DevTools → Network → filter WS → frame `pcg_packet` terlihat sebagai JSON
   (bukti untuk laporan pekanan).

## Struktur kode

```
src/
  lib/auriscore/
    protocol.ts        # salinan tipe protokol (sumber kebenaran: mock-device)
    pcg-connection.ts  # transport: validasi, reconnect, gap fill, ?device=
    ring-buffer.ts     # buffer melingkar 10 dtk + penanganan seq
    fake-classifier.ts # klasifikasi tiruan (FORCE_ABNORMAL_RESULT)
    format.ts          # label & format waktu (Asia/Jakarta)
  hooks/
    use-pcg-stream.ts  # memiliki PcgConnection + RingBuffer
    use-recording.ts   # alur rekam 10 dtk → memproses → hasil
  components/auriscore/ # MainScreen, PcgWaveform, kartu status/hasil/riwayat
mini-services/mock-device/ # perangkat tiruan (lihat README.md di dalamnya)
DECISIONS.md               # log keputusan & pertanyaan terbuka
```

Token desain: `src/app/globals.css` (`.pcg-scope`) — nilai default sementara,
bertanda TODO-FIGMA sampai token Figma tersedia.

Penting: prototipe ini bukan alat medis; semua keluaran diberi label simulasi.
