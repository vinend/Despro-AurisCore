# Worklog AurisCore (berkas bersama semua agent)

Setiap agent WAJIB membaca berkas ini sebelum bekerja dan MENAMBAHKAN (append,
jangan menimpa) catatan kerjanya di akhir berkas setelah selesai.

---
Task ID: 1
Agent: lead (Z.ai Code)
Task: Rekognisi lingkungan sandbox + F0 DECISIONS.md + rencana eksekusi prototipe AurisCore

Work Log:
- Membaca Caddyfile: gateway mendengarkan di :81, meneruskan query `XTransformPort=*` ke `localhost:{port}` (path URI dipertahankan), default ke Next.js :3000.
- Memastikan dev server Next.js 16 sudah berjalan di port 3000 (dev.log sehat, `GET / 200`), dan port 8081 bebas untuk mock-device.
- Membaca examples/websocket (server.ts + frontend.tsx) sebagai referensi pola koneksi lewat gateway.
- Membuat DECISIONS.md di root: keputusan terkunci (WiFi/WebSocket + web app), pertanyaan terbuka (kanal, sampling rate, JSON vs biner, status set_mode/set_bpm), adaptasi lingkungan, aturan sinkronisasi tipe protokol.
- Menugaskan Task 2 (mock-device, subagent) dan Task 3 (frontend Next.js, dikerjakan lead).

Stage Summary:
- Arsitektur adaptif tanpa mengubah protokol seksi 5: frontend = Next.js 16 route `/`; mock-device = mini-service bun di `mini-services/mock-device/` port 8081; klien WS menyambung `ws(s)://<host>/ws?XTransformPort=8081`; override `?device=` tetap didukung.
- Unit test seksi 12 tidak ditulis (kebijakan lingkungan melarang kode test); digantikan verifikasi manual via browser dan dicatat di DECISIONS.md.

---
Task ID: 2
Agent: general-purpose
Task: Implement mock-device WebSocket mini-service (AurisCore PCG simulator, port 8081)

Work Log:
- Membaca worklog.md, DECISIONS.md, Caddyfile, dan examples/websocket sebagai konteks (gateway meneruskan `?XTransformPort=8081` dengan path dipertahankan).
- Membuat `mini-services/mock-device/package.json` (bun, type module, script dev `bun --hot index.ts` + start `bun index.ts`, deps ws ^8, devDeps @types/ws ^8 + typescript ^5) lalu `bun install` (ws 8.21.3, @types/ws 8.18.1, typescript 5.9.3).
- Membuat `protocol.ts`: sumber kebenaran kontrak — konstanta (protocol 1, 2000 Hz, 1 kanal, 100 sampel/paket, interval 50/1000 ms, ORGAN_MODES, QUALITY_FLAGS, clamp 60-100, baterai 87), tipe HelloMessage/PcgPacketMessage/DeviceStatusMessage/ModeAckMessage/SetModeMessage/SetBpmMessage, helper validasi kecil (isOrganMode, isQualityFlag, clampBpm, isSetModeMessage, isSetBpmMessage, messageTypeName).
- Membuat `pcg.ts`: kelas murni PcgSynthesizer(fs, bpm) — S1 Gaussian 55 Hz (sigma 0.0175), S2 pada tS1+0.30 Gaussian 70 Hz (sigma 0.0125), noise ambient 0.02, final `clampToInt16((s1+s2+noise)*0.8*32767)`; pelacakan beat di domain sampel (beat berganti saat melewati `beatStartSample + round(RR*fs)`, panjang beat dihitung ulang dari bpm TERKINI sehingga set_bpm berlaku beat berikutnya); komentar wajib "Nilai sintetis ini hanya untuk visual demo, bukan model fisiologis akurat." disertakan.
- Membuat `index.ts`: WebSocketServer `ws` port 8081 hardcoded tanpa pembatasan path dan tanpa cek Origin; guard hot-reload `globalThis.__mockDeviceCleanup` (terminate klien, clear timer, close server, lepas handler SIGINT/SIGTERM) dipanggil sebelum membuat server baru; hello sekali saat connect; setInterval per koneksi 50 ms (pcg_packet, seq mulai 0 +1 per paket, 100 sampel, qualityFlag sesuai aturan noiseLevel) dan 1000 ms (device_status, baterai 87, signalQuality = qualityFlag terakhir); handler set_mode (mode_ack hanya bila valid) dan set_bpm (clamp, tanpa balasan); pesan tak dikenal/JSON rusak/frame biner diabaikan + log satu baris tanpa memutus koneksi; flag `--chaos` menjatuhkan ~1% paket dengan seq & synthesizer tetap maju; shutdown rapi SIGINT/SIGTERM.
- Smoke test: `timeout 4 bun index.ts` → baris listening + SIGTERM rapi, exit 124; uji end-to-end dengan klien WS sekali-pakai (file sementara, dihapus): hello persis kontrak, 2 klien paralel dengan seq masing-masing mulai 0, paket 100 sampel int16 mode awal mitral, set_mode→mode_ack aortic dan paket berikutnya ikut berubah, set_bpm 120 diklem ke 100 dan terlihat di device_status (bpm 100, batteryPercent 87), tipe tak dikenal & non-JSON diabaikan tanpa putus; uji `--chaos` 5 klien 6 detik → 587 paket, 8 celah seq (log drop per paket); verifikasi hot-reload `bun --hot` (edit file saat berjalan → dua baris listening, tanpa EADDRINUSE); sanity pcg: bpm 60 tepat 2 puncak S1 dalam 2 detik (sampel ~9 & ~2009) dan set_bpm tengah beat tetap mengakhiri beat lama pada 1600 sampel.
- Membuat `README.md` bahasa Indonesia sebagai referensi protokol tim firmware (Crystaly dan Christian): cara menjalankan, URL gateway `ws(s)://<host>/ws?XTransformPort=8081`, override `?device=`, referensi 6 pesan lengkap dengan contoh JSON + penjelasan per field, diagram ASCII alur, aturan forward-compat/seq/clamp bpm/qualityFlag/--chaos, catatan JSON-vs-biner (pertanyaan terbuka, lihat DECISIONS.md).
- Membersihkan semua proses & file sementara; memastikan tidak ada listener tersisa di 8081 (ss) dan dev server Next.js di 3000 tidak tersentuh.

Stage Summary:
- File dibuat: `mini-services/mock-device/{package.json, protocol.ts, pcg.ts, index.ts, README.md}` + `bun.lock`/`node_modules` hasil install. Tidak ada file lain yang diubah selain worklog.md ini.
- Cara menjalankan: `cd mini-services/mock-device && bun run dev` (port 8081); browser menyambung `ws(s)://<host>/ws?XTransformPort=8081`; flag chaos: `bun run start --chaos`.
- Keputusan: port 8081 hardcoded sesuai spesifikasi; WebSocketServer tanpa pembatasan path (path `/ws` diteruskan gateway); cleanup hot-reload juga melepas handler sinyal agar `bun --hot` tidak menumpuk listener; qualityFlag "poor" tidak pernah muncul di mock (noiseLevel konstan 0.02) tapi aturan lengkapnya diimplementasikan dan didokumentasikan agar firmware meniru aturannya. Tidak ada deviasi dari spesifikasi Task 2.

---
Task ID: 3
Agent: lead (Z.ai Code)
Task: Frontend lengkap — libs murni (protokol, transport, ring buffer), canvas gelombang, layar utama, hooks, token CSS

Work Log:
- Menulis `src/lib/auriscore/protocol.ts` (salinan tipe + parseServerMessage: pesan tak dikenal diabaikan diam-diam, pesan tidak valid diwarn tanpa exception), `ring-buffer.ts` (kapasitas 20.000 sampel, pushPacket dengan gap fill hening & buang duplikat/telat, readWindow tanpa alokasi per frame, clear vs resetSequence terpisah), `pcg-connection.ts` (PcgConnection: reconnect 1→2→maks 5 dtk, resolveDeviceUrl relatif origin + override ?device=, validasi semua pesan), `fake-classifier.ts` (FORCE_ABNORMAL_RESULT default false, confidence 87–97), `format.ts` (label Indonesia, waktu Asia/Jakarta).
- Menulis hooks `use-pcg-stream.ts` (pakets tidak memicu render — hanya versionRef untuk rAF; mode sinkron dari paket + mode_ack → ring.clear; reconnect → resetSequence) dan `use-recording.ts` (10 dtk auto-stop → 1,5 dtk memproses → hasil + riwayat dalam memori).
- Menulis komponen: `pcg-waveform.tsx` (canvas dpr + ResizeObserver, rAF hanya menggambar saat data/resize baru, peak envelope right-aligned per kolom, grid 1 dtk + 1/4 tinggi, skala tetap int16→90% tinggi, warna dari CSS vars .pcg-scope), `connection-badge.tsx` (Terputus merah / Terhubung, simulasi kuning / Perangkat hijau / Menyambung…), `device-status-card.tsx`, `organ-mode-selector.tsx` (ToggleGroup 4 mode), `recording-controls.tsx` (Rekam/Berhenti + timer + progress + slider commit), `result-card.tsx` (fade-in framer-motion, label "hasil simulasi"), `history-list.tsx` (scrollbar tipis), `main-screen.tsx` (header sticky, footer mt-auto).
- Mengubah `page.tsx` (merender MainScreen), `layout.tsx` (metadata AurisCore, lang id), `globals.css` (token .pcg-scope TODO-FIGMA + scrollbar tipis).
- Perbaikan saat integrasi: name collision `setOrganMode` (HTTP 500) → state setter diubah nama; lint react-hooks/refs → RingBuffer dibuat lewat useState lazy initializer; lint setState-dalam-effect → sinkronisasi slider dipindah ke event handler onValueCommit.

Stage Summary:
- Frontend berjalan di route `/` (Next.js 16 App Router), tanpa logika tiruan di klien: seluruh data dari WebSocket ke mock-device.
- Semua target seksi 7–9 terimplementasi; lint bersih; halaman HTTP 200.

---
Task ID: 4
Agent: lead (Z.ai Code)
Task: Integrasi dua proses + uji rantai WebSocket lewat gateway

Work Log:
- Menjalankan mock-device di background: `cd mini-services/mock-device && nohup bun run dev > mock-device.log 2>&1 &` (port 8081 listening).
- Memverifikasi rantai penuh dengan klien WS sekali-pakai ke `ws://localhost:81/ws?XTransformPort=8081`: hello sesuai kontrak, pcg_packet 100 sampel, seq 0→2 berurutan.
- `bun run lint` bersih; dev.log hanya GET / 200.

Stage Summary:
- Kedua proses hidup; Caddy meneruskan WS dengan path /ws tanpa masalah.

---
Task ID: 5
Agent: lead (Z.ai Code)
Task: Verifikasi E2E dengan agent-browser (skrip seksi 15 yang diadaptasi)

Work Log:
- Membuka http://localhost:81 (jalur gateway, sama seperti Preview Panel): badge "Terhubung, simulasi", kartu status (BPM 75, baterai 87%, kualitas sinyal), info perangkat di footer.
- Gelombang terverifikasi bergulir: piksel teal terdeteksi di canvas dan checksum piksel berubah antar-waktu (3 sampel berbeda); halaman dibiarkan berjalan menit lamanya tanpa error.
- Mode organ: klik "Aortik" → log mock-device "set_mode: organMode=aortic (mode_ack terkirim)", label kartu status + header gelombang berubah ke Aortik.
- BPM: fokus slider + tekan End → 100 BPM; kartu status ikut melaporkan 100 (kontrol dua arah bekerja).
- Rekam: klik Rekam → timer "0:02,0 / 0:10,0" → auto-stop tepat 10 dtk → memproses 1,5 dtk → kartu hasil "Normal, Keyakinan 88% (nilai acak, simulasi)", mode Mitral, durasi 10,0 dtk, waktu WIB, disclaimer bukan alat medis → riwayat bertambah 1 entri.
- Reconnect: pkill mock-device → badge "Terputus"; restart → badge kembali "Terhubung, simulasi" (backoff 1→2→5 dtk), status kembali default 75, gelombang lanjut bergulir (checksum piksel berubah lagi).
- Responsif: viewport 390×844 tanpa scroll horizontal, gelombang tergambar (kanvas 356×280, piksel teal), footer menempel akhir dokumen; verifikasi visual tambahan via VLM atas screenshot desktop (semua sehat) dan mobile.
- Console & page errors bersih; tidak ada hydration error di dev.log. Catatan: klien kedua di mock-device berasal dari Preview Panel (jalur publik gateway) — bukan bug.

Stage Summary:
- Seluruh langkah skrip verifikasi manual lulus (kecuali `npm test` yang digantikan kebijakan lingkungan; bukti WS JSON: langkah DevTools untuk laporan pekanan).

---
Task ID: 6
Agent: lead (Z.ai Code)
Task: F6 — README aplikasi, commit per fase, penutupan

Work Log:
- Menulis README.md root: arsitektur, cara menjalankan dua proses, status fitur (DoD), verifikasi manual, struktur kode.
- Commit per fase: `feat(mock-device)` 42eb771, `feat(app)` 659436d, `docs` 2e25bed (DECISIONS.md + README.md).

Stage Summary:
- Prototipe pekan 3 selesai dan terverifikasi di browser; keputusan/penyimpangan tercatat di DECISIONS.md; riwayat commit siap dipakai sebagai bukti laporan pekanan.
