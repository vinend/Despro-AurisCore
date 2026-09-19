# DECISIONS.md — AurisCore

Log keputusan prototipe web app pekan 3. Keputusan besar diambil manusia;
agent hanya mencatat keputusan implementasi cara-paling-sederhana (seksi 14
rencana eksekusi) dan dilarang memutuskan pertanyaan terbuka.

## 1. Keputusan terkunci (tim, dicatat saat F0)

| Tanggal | Keputusan | Rujukan |
|---|---|---|
| 2026-09-08 | Komunikasi perangkat memakai WiFi (WebSocket), tanpa BLE | catatan kajian v2 skenario B, `docs/kajian-opsi-aplikasi-seluler.md` |
| 2026-09-08 | Platform aplikasi: web app (browser desktop & ponsel, responsif) | catatan kajian v2 skenario B, `docs/kajian-opsi-aplikasi-seluler.md` |

## 2. Pertanyaan terbuka (TIDAK diputuskan agent)

- Jumlah kanal: draf 1 kanal (`channels: 1` pada protokol).
- Sampling rate final: draf 2000 Hz.
- Bentuk pesan produksi: JSON untuk prototipe; bingkai biner kandidat produksi
  (perlu pengukuran ukuran pesan — stretch seksi 11.4).
- `set_mode` / `set_bpm` adalah kontrol demo, bukan bagian kontrak klinis final.
- Risiko untuk pemilik tugas (tidak bisa diselesaikan agent): penerimaan web
  app sebagai "aplikasi seluler" oleh dosen belum dikonfirmasi — pemilik tugas
  wajib mengajukan klarifikasi sebelum laporan berikutnya.

Pemetaan draft kontrak data kelompok yang sudah terwakili protokol:
samplingRate, durasi window (50 ms implisit dari 100 sampel per paket),
timestamp epoch milidetik, label mode organ, quality flag, jumlah kanal,
format PCM int16 signed.

## 3. Keputusan implementasi agent (cara paling sederhana)

Lingkungan eksekusi sandbox ini berbeda dari rencana (Vite + dua proses npm +
port 5173/8081 langsung). Adaptasi dipilih seminimal mungkin tanpa mengubah
protokol WebSocket seksi 5:

1. **Frontend**: Next.js 16 App Router yang sudah tersedia di sandbox, hanya
   route `/`. Struktur `app/src/...` pada rencana dipetakan ke
   `src/lib/auriscore/` (logika murni: protokol, transport, ring buffer) dan
   `src/components/auriscore/` (UI). Tidak ada Vite dan tidak ada port 5173.
2. **mock-device**: berjalan sebagai mini-service bun mandiri di
   `mini-services/mock-device/` (port 8081 tetap, `bun --hot`). Karena sandbox
   hanya mengekspos satu port lewat gateway Caddy, browser menyambung ke
   `ws(s)://<host>/ws?XTransformPort=8081` — relatif terhadap origin halaman,
   tanpa alamat/port absolut di kode klien. Parameter URL `?device=ws://...`
   tetap didukung untuk menukar ke perangkat ESP32 sungguhan nanti tanpa
   perubahan kode.
3. **Tanpa unit test**: kebijakan lingkungan melarang penulisan kode test.
   Logika `ring_buffer` dan `pcg_connection` tetap dipisah dari React dan
   WebSocket agar mudah diuji saat dipindah ke repo kelompok; verifikasi
   digantikan uji manual browser (skrip seksi 15) yang dijalankan agent.
4. Rekam dihentikan manual sebelum 10 detik → tetap diproses dengan durasi
   aktual, tidak dibatalkan (riwayat menampilkan durasi sesi aktual).
5. Toggle hasil klasifikasi tiruan: konstanta `FORCE_ABNORMAL_RESULT` di
   `src/lib/auriscore/fake-classifier.ts` (default `false` → Normal).
6. Slider BPM mengirim `set_bpm` saat commit (pointer dilepas / komit
   keyboard), bukan pada setiap geseran, agar tidak membanjiri perangkat.
7. Grid gelombang digambar berjangkar tepi kanan kanvas (garis statis tiap
   1 detik); jendela data selalu 5 detik terakhir sehingga fast-forward
   setelah tab tersembunyi terjadi otomatis.
8. Tombol Rekam dan slider BPM dinonaktifkan saat koneksi terputus.
9. Badge koneksi menambah state "Menyambung…" untuk fase `connecting`
   (spesifikasi hanya mendefinisikan tiga label akhir).
10. Kartu status mempertahankan nilai `device_status` terakhir yang diketahui
    saat koneksi terputus (badge merah tetap menandai keadaan terputus).

## 4. Sinkronisasi tipe protokol

Sumber kebenaran: `mini-services/mock-device/protocol.ts`.
Salinan aplikasi: `src/lib/auriscore/protocol.ts`.
Aturan: setiap perubahan tipe wajib diedit di kedua file pada waktu yang sama
dan dicatat di bagian ini. Jangan membuat monorepo atau paket bersama.

| Tanggal | Perubahan | Penyebab |
|---|---|---|
| 2026-09-08 | Protokol versi 1: `hello`, `pcg_packet`, `device_status`, `mode_ack` (server→klien); `set_mode`, `set_bpm` (klien→server) | implementasi awal F1–F2 |

## 5. Peluang perbaikan (belum diimplementasikan — seksi 14)

- Manifes PWA + ikon agar dapat dipasang di home screen (stretch 11.1).
- Pemutaran audio stream via Web Audio API, buffer 2000 Hz (stretch 11.2).
- Pengukuran ukuran pesan JSON vs bingkai biner sebagai bahan keputusan
  kontrak data produksi (stretch 11.4). Flag `--chaos` (11.3) sudah tersedia
  di mock-device.
- Timer sintesis terkunci wall-clock (bukan `setInterval` murni) agar bebas
  drift jam jangka panjang.
- Persistensi riwayat rekaman (non-goal pekan ini, cukup dalam memori).
