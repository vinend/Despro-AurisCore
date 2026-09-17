# AurisCore — Prototipe Web App (Pekan 3)

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

```bash
# Terminal 1 — perangkat tiruan (port 8081)
cd mini-services/mock-device
bun run dev            # tambahkan --chaos untuk uji gap: bun run start -- --chaos

# Terminal 2 — aplikasi web (port 3000)
cd .                   # root proyek ini
bun run dev
```

Buka aplikasi lewat gateway/preview (port eksternal). Browser otomatis
menyambung ke `ws(s)://<host>/ws?XTransformPort=8081`; indikator koneksi ada
di header. Uji koneksi langsung ke perangkat lain:
`.../?device=ws://<alamat-perangkat>/ws`.

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
