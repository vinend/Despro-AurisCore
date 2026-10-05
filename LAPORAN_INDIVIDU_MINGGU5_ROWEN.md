# LAPORAN KEMAJUAN PEKANAN INDIVIDU

DESAIN PROYEK TEKNIK ELEKTRO, KOMPUTER, BIOMEDIK 2

| Identitas | Keterangan |
|---|---|
| Judul proyek | AurisCore: Digital Stethoscope |
| Kelompok | 1 |
| Nama | Rowen Rodotua Harahap |
| NPM | 2306250604 |
| Program studi | Teknik Komputer |
| Pekan | 5 |
| Periode | 21–26 September 2026 |
| Dosen pembimbing | Dr. Basari, S.T., M.Eng. |

## 1. Ringkasan Kemajuan Pekanan

Pada pekan kelima, saya melanjutkan pekerjaan perangkat lunak AurisCore dengan meninjau pipeline pengolahan suara jantung (PCG) dan baseline SVM yang telah saya implementasikan sebelumnya. Saya melakukan penyiapan lingkungan lokal, verifikasi WebApp dan simulator perangkat, serta peninjauan alur konversi WAV menjadi log-mel spectrogram sebagai masukan CNN sesuai arahan dosen. Saya juga menyiapkan perapian antarmuka agar pemantauan sinyal dan kontrol rekaman lebih mudah digunakan.

Kontribusi SVM awal telah tercatat pada commit 16 September 2026. Oleh karena itu, laporan pekan ini mencatat peninjauan dan tindak lanjut terhadap baseline tersebut, bukan mengklaim pelatihan awal SVM sebagai pekerjaan baru pekan kelima. Performa CNN pada dataset asli belum dievaluasi pada pekan ini.

## 2. Target dan Realisasi Kegiatan

| Kegiatan individu | Realisasi pekan ini | Status |
|---|---|---|
| Menyiapkan dan menjalankan aplikasi lokal | Memasang dependensi WebApp dan mock-device; memverifikasi respons HTTP 200 dan handshake WebSocket. Menyiapkan penggunaan npm.cmd untuk mengatasi pembatasan npm.ps1 pada PowerShell. | Terverifikasi pada sesi lokal |
| Meninjau pipeline PCG dan baseline SVM | Meninjau validasi CirCor, preprocessing 8 kHz, segmentasi, 349 fitur, pembagian data per peserta, training, evaluasi, dan inference WAV yang telah tersedia. | Selesai ditinjau |
| Menindaklanjuti masukan WAV ke spektrogram | Memeriksa implementasi CNN log-mel yang sudah ada; menambahkan ekspor tensor .npy, preview PNG, dan metadata serta penolakan masukan hening. | Implementasi lokal; konversi diuji |
| Merapikan frontend sesuai koordinasi tim | Menyiapkan tata letak panel sinyal dan kontrol rekaman, menyederhanakan elemen visual, serta menghapus tampilan persentase keyakinan acak. | Draf lokal; verifikasi UI belum tuntas |
| Memetakan mode pemeriksaan | Membandingkan laporan desain dengan kode; mengidentifikasi bahwa Mitral, Aortik, Pulmonik, dan Trikuspid adalah lokasi pemeriksaan jantung. Mode paru dan abdomen belum tersedia. | Selesai ditinjau |

<!-- PAGEBREAK -->

## 3. Hasil Pekerjaan Individu

Saya menyiapkan ekspor spektrogram dari audio WAV dengan preprocessing yang sama seperti pipeline CNN. Hasil ekspor berupa tensor numerik float32, preview gambar, dan metadata sumber serta konfigurasi. Preview PNG digunakan untuk inspeksi; masukan training tetap berupa tensor log-mel, bukan gambar yang memuat judul, sumbu, atau legenda.

Pada konfigurasi saat ini, satu window lima detik menghasilkan tensor berukuran 40 × 313 × 1. Saya menambahkan pengujian kesesuaian tensor ekspor dengan fungsi masukan training, penanganan rekaman pendek melalui padding, pemeriksaan rentang normalisasi, serta penolakan audio hening. Prosedur training CNN juga diperbarui agar setiap epoch mempunyai batas dataset yang jelas dan riwayat training dapat disimpan. Perubahan training tersebut belum diverifikasi melalui eksekusi TensorFlow.

Untuk frontend, saya menyiapkan draf tampilan dengan warna netral, aksen hijau, panel fonokardiogram sebagai fokus utama, kontrol rekaman di samping, dan riwayat sesi berbentuk tabel. Koneksi lokal diarahkan ke simulator port 8081. Hasil yang ditampilkan tetap diberi label simulasi karena model Python belum terintegrasi ke WebApp.

## 4. Pengujian dan Status Verifikasi

| Pemeriksaan | Hasil | Batas hasil |
|---|---|---|
| WebApp dan mock-device sebelum perapian UI | Halaman merespons HTTP 200; server mengirim hello dengan sampling rate 8 kHz dan satu kanal. | Membuktikan aplikasi dan transport simulasi dapat berjalan; bukan hasil model AI. |
| Test suite Python terbaru | 30 test lulus, 2 test dilewati, dengan peringatan deprecation nonfatal. | Test memakai data sintetis/fixture. Test CNN yang memerlukan TensorFlow dilewati. |
| Draf frontend setelah perubahan | Pemeriksaan lint komponen selesai; pemeriksaan TypeScript keseluruhan masih terkendala PrismaClient yang belum dihasilkan. | Build dan pengujian interaksi/visual draf belum dinyatakan selesai. |
| Training dan evaluasi pada data asli pekan ini | Belum dijalankan. Dataset sumber dan model terlatih belum tersedia di checkout lokal saat pemeriksaan. | Belum ada angka performa CNN baru atau bukti peningkatan terhadap SVM. |

## 5. Kendala dan Tindak Lanjut

| Kendala | Tindak lanjut |
|---|---|
| PowerShell memblokir npm.ps1 | Menyiapkan perintah npm.cmd untuk instalasi dan menjalankan dev server. |
| Dataset dan artefak model tidak ikut tersedia di checkout | Menyiapkan pemulihan dataset serta model sebelum eksperimen training berikutnya. |
| TensorFlow belum tersedia untuk verifikasi CNN | Menuntaskan lingkungan dependensi CNN sebelum menguji training dan inference. |
| Verifikasi frontend belum lengkap dan tim juga melakukan perapian repository | Meninjau perubahan terbaru tim sebelum menggabungkan draf UI dan menjalankan build serta uji interaksi. |

<!-- PAGEBREAK -->

## 6. Rencana Kerja Pekan Berikutnya

| Rencana kegiatan Rowen | Target keluaran | Waktu |
|---|---|---|
| Menyelaraskan draf frontend dengan perubahan Andi dan anggota tim | Antarmuka yang konsisten dengan repository terbaru; tidak menimpa pekerjaan anggota lain. | Pekan 6 |
| Menuntaskan verifikasi frontend | Build, pemeriksaan TypeScript, serta uji koneksi, pemilihan lokasi, rekam/berhenti, dan tampilan desktop/mobile. | Pekan 6 |
| Menuntaskan lingkungan CNN dan persiapan data | TensorFlow siap digunakan; dataset, manifest, dan split peserta diperiksa kembali. | Pekan 6 |
| Menindaklanjuti rancangan CNN tim dengan masukan log-mel | Uji training dan inference CNN, dilanjutkan eksperimen data asli jika lingkungan dan data siap. | Pekan 6 |
| Membandingkan CNN dengan baseline SVM | Evaluasi pada peserta validasi yang sama menggunakan sensitivitas, spesifisitas, macro F1, balanced accuracy, dan confusion matrix. | Pekan 6 |

Pengembangan paru dan abdomen memerlukan dataset, definisi label, preprocessing, dan evaluasi tersendiri. Pekan berikutnya dapat dimulai dengan pemetaan kebutuhannya; penyelesaian model untuk kedua organ tersebut belum dijadikan capaian pekan ini. Kuantisasi INT8 dan deployment ke smartphone juga masih berada pada tahap lanjutan.

## 7. Kesimpulan

Pekerjaan individu pekan kelima menghasilkan peninjauan baseline SVM, verifikasi awal aplikasi dan simulator, implementasi ekspor spektrogram yang telah diuji secara sintetis, serta draf perapian UI. Konversi WAV ke log-mel dapat digunakan dalam alur CNN, tetapi peningkatan performa harus dibuktikan melalui evaluasi pada data yang terpisah per peserta. Target pekan berikutnya adalah menuntaskan verifikasi UI, menyiapkan lingkungan CNN, dan memulai perbandingan dengan SVM setelah data tersedia.

## 8. Bukti dan Rujukan Pekerjaan

- Commit ee0975d, 16 September 2026, atas nama Rowen Rodotua Harahap: Implement reproducible heart PCG pipeline and SVM baseline. Ini merupakan bukti kontribusi sebelumnya yang ditinjau kembali pekan ini.
- AI-Pipeline/docs/engineering_summary.md dan docs/baseline_results.md: catatan implementasi dan hasil historis SVM.
- AI-Pipeline/scripts/export_spectrogram.py, src/auriscore/spectrogram.py, dan tests/test_spectrogram.py: implementasi lokal ekspor dan pengujian spektrogram.
- WebApp/src/components/auriscore/ dan src/app/globals.css: draf perapian antarmuka lokal yang masih memerlukan verifikasi akhir.
- Laporan Despro_UAS_Crystaly.pdf, halaman 41–43 dan 56–57: rancangan mode Heart, Lung, dan Abdomen serta rencana evaluasi per mode.

Depok, 26 September 2026

Rowen Rodotua Harahap

NPM 2306250604
