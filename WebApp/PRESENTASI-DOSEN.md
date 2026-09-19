# Skrip Presentasi Progress AurisCore ke Dosen (Pekan 3)

> Durasi ideal: 10–15 menit (5 menit penjelasan + 5 menit demo + Q&A).
> Bahan pendukung: aplikasi berjalan (2 proses), DevTools terbuka, riwayat commit Git.

---

## 1. Pembukaan — Konteks (±1 menit)

**Yang dikatakan:**

> "Minggu ini saya menyelesaikan prototipe aplikasi web untuk AurisCore. Dua keputusan
> besar yang sudah dikunci tim: komunikasi perangkat memakai **WiFi melalui WebSocket**
> (bukan BLE), dan platform aplikasinya adalah **web app** yang responsif di desktop
> maupun ponsel.
>
> Karena hardware ESP32-S3 belum tersedia, saya membangun **perangkat tiruan
> (mock-device)** — sebuah server WebSocket yang mensimulasikan firmware ESP32.
> Jadi yang didemokan hari ini adalah **rantai komunikasi sungguhan**:
> browser terhubung lewat WebSocket, menerima data, dan menampilkannya.
> Nanti firmware ESP32 hanya perlu meniru protokol yang sama, dan aplikasi
> langsung bisa dipakai tanpa perubahan kode."

**Poin kuncinya:** yang dibangun bukan "mockup UI", tapi arsitektur komunikasi
nyata dengan sumber data yang disimulasikan.

---

## 2. Arsitektur (±2 menit)

**Yang dikatakan:**

> "Ada dua komponen yang berjalan terpisah:
>
> 1. **Aplikasi web** — React/TypeScript, satu layar utama.
> 2. **Mock-device** — server WebSocket yang mensimulasikan sensor stetoskop:
>    mengirim paket data fonokardiogram (PCG) setiap 50 milidetik.
>
> Penting: **frontend tidak punya logika simulasi apa pun**. Semua data —
> gelombang, BPM, baterai, kualitas sinyal — datang dari WebSocket.
> Simulasi hanya ada di sisi perangkat, persis seperti nanti di firmware.
>
> Untuk berpindah ke ESP32 sungguhan nanti, cukup tambahkan parameter URL
> `?device=ws://alamat-perangkat` — tanpa mengubah kode."

**Skema yang bisa digambar di papan/slide:**

```
[Browser]                         [Sekarang]              [Masa depan]
 React (Next.js) ──WebSocket──►  mock-device (port 8081) ──diganti──► firmware ESP32-S3
                 protokol JSON v1  (PCG sintetis)           (protokol sama)
```

---

## 3. Protokol Komunikasi (±2 menit) — *nilai jual utama*

**Yang dikatakan:**

> "Saya mendefinisikan kontrak data versi 1 dalam bentuk JSON. Ada enam jenis pesan:
>
> **Dari perangkat ke aplikasi:**
> - `hello` — dikirim sekali saat koneksi: nama perangkat, versi firmware, sampling rate.
> - `pcg_packet` — paket data gelombang: 100 sampel PCM int16 setiap 50 ms
>   (= sampling rate 2000 Hz), lengkap dengan nomor urut, timestamp, mode auskultasi,
>   dan flag kualitas sinyal.
> - `device_status` — tiap 1 detik: BPM, baterai, kualitas sinyal.
> - `mode_ack` — konfirmasi pergantian mode.
>
> **Dari aplikasi ke perangkat:**
> - `set_mode` — memilih titik auskultasi (mitral, aortik, pulmonal, trikuspidal).
> - `set_bpm` — mengatur laju jantung simulasi 60–100 BPM.
>
> Dua aturan penting untuk masa depan:
> 1. **Forward compatibility** — pesan dengan tipe yang tidak dikenal diabaikan,
>     tidak crash. Jadi firmware nanti bisa menambah fitur tanpa merusak aplikasi lama.
> 2. **Nomor urut (seq)** — aplikasi mendeteksi paket hilang dan mengisinya dengan
>     hening; paket duplikat atau telat dibuang. Jaringan WiFi tidak sempurna,
>     jadi ini dirancang sejak awal.
>
> Dokumentasi lengkap protokol ada di `mini-services/mock-device/README.md` —
> ini yang nanti jadi referensi tim firmware (Crystaly dan Christian)."

**Jika ditanya kenapa JSON:** "JSON untuk prototipe agar mudah di-debug di DevTools.
Untuk produksi masih pertanyaan terbuka — frame biner lebih kecil, dan rencananya
akan diukur perbandingannya sebelum diputuskan."

---

## 4. Demo Langsung (±5 menit)

Urutan demo yang disarankan (siapkan sebelum presentasi):

1. **Koneksi** — buka aplikasi. Tunjukkan badge **"Terhubung, simulasi"** (kuning,
   karena nama perangkat mengandung "Mock" — nanti ESP32 asli akan tampil hijau
   "Perangkat"). Kartu status: BPM 75, baterai 87%, kualitas sinyal.
2. **Gelombang real-time** — biarkan 10–15 detik. Jelaskan: jendela tampil 5 detik
   terakhir, digambar di canvas dengan teknik *peak envelope* (tiap kolom piksel
   menggambar nilai min–maks), target 60 fps. Tunjukkan puncak S1 (lebih besar)
   dan S2 — dari sintesis Gaussian di mock-device.
3. **Kontrol BPM** — geser slider ke 100, lepaskan. Tunjukkan laju denyut berubah
   dan kartu status ikut melaporkan 100. *"Kontrol dua arah — aplikasi bisa
   mengirim perintah ke perangkat."*
4. **Ganti mode organ** — klik "Aortik". Jelaskan: aplikasi mengirim `set_mode`,
   perangkat membalas `mode_ack`, buffer gelombang direset, label berubah.
5. **Rekam** — klik tombol Rekam. Timer berjalan → berhenti otomatis di 10 detik →
   "Memproses…" 1,5 detik → kartu hasil muncul. **Tegaskan label "hasil simulasi"**
   dan disclaimer bukan alat medis. Riwayat sesi bertambah satu baris.
6. **Ketahanan koneksi** *(demo paling kuat)* — matikan proses mock-device
   (Ctrl+C di terminal). Badge berubah merah "Terputus". Nyalakan lagi →
   aplikasi menyambung ulang otomatis (backoff 1→2→maks 5 detik) dan gelombang
   lanjut bergulir. *"Aplikasi tidak perlu di-refresh."*
7. **Bukti data nyata** *(opsional, jika ada waktu)* — DevTools → Network →
   filter WS → tab Messages: frame `pcg_packet` terlihat sebagai JSON mentah.
   *"Ini bukti data benar-benar lewat WebSocket, bukan animasi CSS."*
8. **Responsif** — kecilkan window / buka DevTools mobile view. Layout menyesuaikan.

---

## 5. Hal Teknis yang Layak Disorot (bila dosen bertanya)

- **Ring buffer** — buffer melingkar 20.000 sampel (10 detik) tanpa alokasi memori
  per frame; penanganan seq untuk gap/duplikat/telat.
- **Reconnect otomatis dengan exponential backoff** (1s → 2s → maks 5s, tanpa batas percobaan).
- **Canvas berperforma** — hanya menggambar saat ada data/resize baru; sadar
  devicePixelRatio untuk layar retina; ResizeObserver untuk responsif.
- **Pemisahan tanggung jawab** — logika transport & buffer terpisah murni dari React,
  mudah dipindah/diuji di repo kelompok nanti.
- **Mode uji chaos** — mock-device punya flag `--chaos` yang menjatuhkan ±1% paket
  secara acak untuk menguji penanganan gap.
- **Riwayat commit per fase** (`feat(mock-device)`, `feat(app)`, `docs`) sebagai
  bukti proses pengerjaan bertahap.

---

## 6. Pertanyaan Terbuka untuk Dosen (WAJIB diajukan!)

Bagian ini penting — jangan lupa, karena sudah tercatat di DECISIONS.md sebagai
risiko yang butuh klarifikasi:

> "Ada beberapa hal yang ingin saya konfirmasi:
>
> 1. **Apakah web app diterima sebagai 'aplikasi seluler'?** Kami memilih web app
>    karena satu basis kode untuk semua platform dan bisa di-install sebagai PWA.
>    Apakah ini sesuai ekspektasi untuk tugas/konteks mata kuliah ini?"
> 2. **Jumlah kanal mikrofon** — draf saat ini 1 kanal. Apakah perlu stereo?
> 3. **Sampling rate final** — draf 2000 Hz. Cukup untuk PCG (frekuensi jantung
>    dominan di bawah 500 Hz), tapi ingin konfirmasi.
> 4. **Format pesan produksi** — JSON vs biner. Rencananya akan diukur perbandingan
>    ukurannya sebelum memutuskan."

---

## 7. Rencana Berikutnya (penutup)

> "Rencana selanjutnya: mengintegrasikan dengan hardware ESP32-S3 saat sudah
> tersedia (protokol sudah siap, tinggal ditiru di firmware), lalu stretch goals:
> pemutaran audio real-time via Web Audio API, manifes PWA agar bisa dipasang di
> home screen, dan pengukuran JSON vs biner untuk keputusan format produksi."

---

## 8. Antisipasi Pertanyaan Dosen (persiapan Q&A)

| Kemungkinan pertanyaan | Jawaban singkat |
|---|---|
| "Ini cuma simulasi, apa gunanya?" | Yang diuji adalah **rantai komunikasi dan UI** — komponen yang tidak bergantung hardware. Saat ESP32 datang, firmware hanya meniru protokol; aplikasi tidak berubah. Ini memparalelkan kerja software & hardware. |
| "Kenapa WebSocket, bukan HTTP/REST atau BLE?" | Streaming data kontinu 50 ms/paket butuh koneksi dua arah persisten — WebSocket cocok; HTTP terlalu boros (overhead header per request), BLE dibahas di kajian dan diputuskan tim memakai WiFi (catatan di DECISIONS.md). |
| "Kenapa hasil klasifikasi bisa muncul padahal model AI belum ada?" | Itu placeholder yang **berlabel jelas "hasil simulasi"** — confidence 87–97% acak. Alur UI-nya (rekam → proses → tampilkan) sudah siap diisi model asli nanti. |
| "Bagaimana kalau WiFi putus di tengah pemeriksaan?" | Sudah ditangani: reconnect otomatis, gap diisi hening (bukan data palsu), badge status jelas merah. Rekaman berhenti karena tombol dinonaktifkan saat terputus. |
| "Mana unit test-nya?" | Logika inti (buffer, transport) sengaja dipisah murni dari React/WebSocket agar mudah diuji; di lingkungan pengembangan saat ini verifikasi dilakukan lewat uji manual terstruktur (skrip 7 langkah di README), termasuk uji chaos 1% paket hilang. Test formal akan ditulis saat dipindah ke repo kelompok. *(Jujur saja sesuai DECISIONS.md.)* |
| "Kenapa 10 detik untuk rekam?" | Durasi standar potongan PCG untuk analisis — cukup menangkap ±12 denyut pada 75 BPM. |
| "Data pasien disimpan di mana?" | Tidak ada penyimpanan — riwayat hanya di memori sesi. Penyimpanan memang **non-goal** minggu ini; pertimbangan privasi data akan dibahas saat merancang produksi. |
| "Bisa dipakai di HP?" | Ya, responsif dan bisa dijadikan PWA (di home screen seperti aplikasi native) — manifes PWA ada di daftar stretch. |

---

## Checklist Sebelum Presentasi

- [ ] Jalankan mock-device: `cd mini-services/mock-device && bun run dev`
- [ ] Jalankan aplikasi web: `bun run dev` (root)
- [ ] Buka aplikasi, pastikan badge "Terhubung, simulasi" dan gelombang bergulir
- [ ] DevTools terbuka di tab Network (filter WS) sebagai bukti frame JSON
- [ ] Terminal mock-device terlihat — untuk demo mati/nyala koneksi
- [ ] Siapkan screenshot cadangan (desktop + mobile) kalau koneksi gagal
- [ ] `git log --oneline` siap ditunjukkan sebagai bukti commit per fase
