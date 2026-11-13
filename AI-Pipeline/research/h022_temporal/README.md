# H022 + Temporal MIL di komputer tujuan

**RD-H022-TMIL-P1** menguji apakah pelatihan Temporal MIL dari encoder H022 meningkatkan precision Murmur Present pada tingkat peserta. Hasilnya belum diketahui.

## Instalasi dan transfer

Gunakan Linux x86-64 atau WSL2, filesystem Linux asli dan GPU NVIDIA dengan driver CUDA yang kompatibel. Salin **AurisCore-H022T1-TRAIN-private.tar** dari Downloads laptop ke home Linux komputer tujuan melalui media privat. Ukuran 1.548.247.040 byte. Arsip berisi 4.170 input, termasuk waveform TRAIN terproses, anotasi fase yang tersedia, supervisi, split, inventaris mining, lima model akustik H022 dan normalisasi masing-masing. Semua tensor bobot model akustik dibandingkan identik saat ekspor dari checkpoint asli. Sumber data [CirCor DigiScope 1.0.3](https://physionet.org/content/circor-heart-sound/1.0.3/), dengan [lisensi dan atribusi](../../docs/licenses/CirCor-ODC-By-1.0.txt).

Gunakan Python 3.13 (versi lokal yang diuji 3.13.16). Pastikan nvidia-smi dapat melihat GPU. Sediakan minimal 12 GiB kosong untuk hasil, di luar arsip, data dan environment. Instalasi membutuhkan indeks paket atau wheel yang sesuai.

~~~bash
git clone --single-branch --branch progress_heart https://github.com/vinend/Despro-AurisCore.git
cd Despro-AurisCore/AI-Pipeline
python3.13 -m venv ~/venvs/auriscore-h022t1
source ~/venvs/auriscore-h022t1/bin/activate
python -m pip install --require-hashes -r configs/temporal_mil_runtime_linux_py313.lock
python -m pip check
echo '7dc369867026b7531f4e43115e77666a76de76ebaf9b8f4b91808cc6f5c55e09  AurisCore-H022T1-TRAIN-private.tar' | (cd ~ && sha256sum -c -)
# Lanjut hanya jika checksum OK. Ekstrak sekali ke direktori baru.
mkdir -p ~/auriscore-runs
mkdir ~/auriscore-h022t1-input && tar -xf ~/AurisCore-H022T1-TRAIN-private.tar -C ~/auriscore-h022t1-input
export HEART_INPUT=~/auriscore-h022t1-input/heart-train
export HEART_RUNS=~/auriscore-runs
export PYTHONPATH="$PWD/src"
python research/h022_temporal/test_handoff.py
python research/h022_temporal/launch.py check --inputs "$HEART_INPUT" --runs "$HEART_RUNS"
~~~

Preflight memeriksa hash privat, kelas/role, grup B1, transfer fitur kelima encoder, operasi GPU nyata, serta inferensi temporal tanpa update optimizer. Launcher memeriksa ulang sebelum training. Jika hash atau GPU gagal, perbaiki penyebabnya di komputer tujuan. Durasi dan kapasitas memori GPU tujuan belum diukur.

## Menjalankan satu eksperimen

Setelah preflight PASS, jalankan dari direktori dan environment di atas:

~~~bash
nohup python -u research/h022_temporal/launch.py train --inputs "$HEART_INPUT" --runs "$HEART_RUNS" > "$HEART_RUNS/h022t1-launch.log" 2>&1 &
echo $!
~~~

Pada terminal kedua, pantau fold, epoch, train loss, validation loss, patience dan sisa waktu. GPU dapat dipantau memakai nvidia-smi.

~~~bash
tail -F ~/auriscore-runs/RD-H022-TMIL-P1-watchdog/worker.log
~~~

Dari PowerShell Windows dengan lokasi WSL default:

~~~powershell
wsl -d Ubuntu -- bash -lc 'tail -F ~/auriscore-runs/RD-H022-TMIL-P1-watchdog/worker.log'
~~~

Exit code ada di RD-H022-TMIL-P1-watchdog/exit.json. Setelah exit code 0 dan lima fold selesai, jalankan replay dalam proses baru pada komputer tujuan:

~~~bash
python research/h022_temporal/launch.py verify-results --inputs "$HEART_INPUT" --runs "$HEART_RUNS"
~~~

RD-H022-TMIL-P1/results.json memuat confusion matrix, accuracy, sensitivity, specificity, precision, F1, balanced accuracy, ROC-AUC dan PR-AUC. Folder evaluasi saudara berisi verifikasi checkpoint, macro-F1 fase, recall empat state, coverage dan CSV kandidat waktu. Replay memakai GPU dan memerlukan waktu tambahan setelah training. Pertahankan keluaran parsial bila proses gagal.

## Keputusan ilmiah yang dibekukan

- **Arsitektur.** Gunakan lima encoder H022 sesuai fold sebelum global pooling. Dua blok awal dan semua BatchNorm dibekukan. Konvolusi terakhir dan head temporal dilatih. Urutan fitur 39 × 64 memasok MIL murmur dan head empat fase. Head logistik historis dipisahkan dari kandidat baru.
- **Kontrol.** Embedding H022 beku, StandardScaler dan balanced L2 logistic regression dengan C=0,1 yang ditetapkan sebelum run. Fit hanya pada peserta fit. Head historis memakai fit dan early-stop untuk final logistic fit. Kedua lengan baru memakai peserta dan prosedur pemilihan ambang yang sama.
- **Supervisi.** 568 peserta (458 Absent dan 110 Present), 2.070 rekaman, 15.954 window dari TRAIN. B1 menggabungkan logit frame dengan log-mean-exp, merata-ratakan skor window per rekaman, lalu memakai BCE berbobot per rekaman. Faktor kelas dihitung dari peserta fit, share rekaman mengikuti hitungan window, dan multiplier mining memakai inventaris asli. Skor peserta adalah rata-rata antarrekaman. Fase memakai cross-entropy pada frame resmi yang valid. Fase tak tersedia tidak menghapus rekaman dari supervisi presence yang berlaku.
- **Optimisasi.** Lima fold berurutan, seed 43–47, 32 rekaman lengkap per update Adam, maksimum 32 window per microbatch, LR 0,0001, per-variable clipnorm 1, koefisien fase 0,2. Maksimum 50 epoch, patience 8 berdasarkan validation loss. Tidak ada pencarian parameter atau retry.
- **Ambang.** Pilih per model per fold pada peserta early-stop. Di antara ambang dengan sensitivitas minimal 90%, maksimalkan precision, lalu minimalkan FP, maksimalkan sensitivitas, lalu ambil ambang terbesar jika seri. Bekukan sebelum prediksi outer. Setiap peserta dinilai tepat sekali. AUC pooled dapat dipengaruhi skala antar-fold.
- **Gate pengembangan.** Precision kandidat harus lebih tinggi dibanding kontrol, sensitivitas pooled minimal 90%, dan FP maksimal 120. Sensitivitas di bawah 85% adalah hard failure. Target rekayasa precision 65% dilaporkan terpisah. Hasil historis H022 (precision 44,84%, sensitivitas 90,91%, FP 123) dan B1 (29,43%, 89,09%, FP 235) memakai aturan ambang berbeda. Gate memakai matched control pada run baru. Satu run tidak menentukan kontribusi kausal setiap komponen atau membuktikan keunggulan klinis.
- **Temporal.** Rentang pada grid valid dengan skor minimal 0,5 merupakan kandidat eksploratif. Belum ada referensi interval murmur independen untuk mengukur akurasi onset/offset. Anotasi fase outer baru digunakan ketika evaluasi fase setelah prediksi terkunci.
- **Provenance.** Baca [audit H021/H022](../../docs/h021_h022_paired_uncertainty_2026-10-28.md) dan [hasil Temporal MIL B1](../../docs/rd_ltmil_b1_final_experiment_result_2026-10-29.md). H021 asli kehilangan lima checkpoint. Sepuluh rekaman alat dengan dua filter per rekaman mempunyai status rujukan Unknown. Uji alat tersebut tidak memberikan akurasi, tidak masuk training, dan tidak menentukan threshold.
