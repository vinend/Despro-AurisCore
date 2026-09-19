# mock-device — Simulator Perangkat AurisCore (WebSocket PCG)

**Dokumen ini adalah referensi protokol bagi tim firmware.**
Tujuannya agar tim firmware (Crystaly dan Christian) dapat meniru protokol ini
pada ESP32-S3, sehingga aplikasi web dapat menukar mock-device dengan
perangkat sungguhan tanpa perubahan kode klien.

Sumber kebenaran tipe pesan: `mini-services/mock-device/protocol.ts`
(salinan aplikasi web: `src/lib/auriscore/protocol.ts`; keduanya wajib diedit
bersamaan setiap kali tipe berubah — lihat DECISIONS.md seksi 4).

Ringkasan singkat:

- Mini-service bun yang menyimulasikan stetoskop digital AurisCore.
- Server WebSocket di **port 8081** (hardcoded, tidak pernah dibaca dari
  environment).
- Mengirim PCG sintetis 8000 Hz, 1 kanal, 400 sampel int16 per paket
  (400 / 8000 Hz = 50 ms audio).
- Protokol versi 1: setiap pesan adalah SATU objek JSON dengan field `type`;
  semua timestamp adalah epoch milidetik.
- Nilai sinyal PCG hanya untuk visual demo, bukan model fisiologis akurat.

## Cara menjalankan

```bash
cd mini-services/mock-device
npm install        # sekali saja
npm run dev        # mode pengembangan (tsx watch, auto reload)
# atau
npm run start      # mode start biasa
```

Flag chaos (menjatuhkan ~1% `pcg_packet` secara acak, lihat bagian Aturan):

```bash
npx tsx index.ts --chaos
# atau jika menggunakan bun: bun index.ts --chaos
```

Akses dari browser: sandbox hanya mengekspos gateway Caddy, jadi klien TIDAK
menyambung langsung ke `localhost:8081`, melainkan lewat forwarding query:

```
ws(s)://<host>/ws?XTransformPort=8081
```

Gateway meneruskan koneksi (termasuk path `/ws`) ke `localhost:8081`. Karena
path diteruskan apa adanya, server ini menerima koneksi di path APA PUN dan
tidak memeriksa header Origin — firmware ESP32 tidak perlu meniru aturan
path/Origin ini, cukup protokol pesannya.

Catatan: aplikasi web juga mendukung override URL `?device=ws://...` untuk
menyambung ke perangkat ESP32 sungguhan di masa depan tanpa perubahan kode.

## Diagram alur (handshake dan loop)

```
Klien (browser)                                  mock-device (:8081)
      |                                                |
      |  sambungkan ws(s)://<host>/ws?XTransformPort=8081
      |----------------------------------------------->|
      |                                                |
      |          hello (sekali, saat koneksi terbuka)  |
      |<-----------------------------------------------|
      |                                                |
      |          pcg_packet (setiap 50 ms realtime)    |
      |<-----------------------------------------------|  400 sampel int16
      |          pcg_packet ...                        |
      |          device_status (setiap 1000 ms)        |
      |<-----------------------------------------------|  bpm, baterai, mutu
      |                                                |
      |  set_mode {"organMode":"aortic"}               |
      |----------------------------------------------->|
      |          mode_ack {"organMode":"aortic"}       |
      |<-----------------------------------------------|  paket berikutnya
      |                                                |  memakai mode baru
      |  set_bpm {"bpm":90}                            |
      |----------------------------------------------->|  TANPA balasan;
      |            (berlaku mulai beat berikutnya)     |  beat berjalan tetap
      |                                                |
      |  tipe tak dikenal / JSON rusak / frame biner   |
      |----------------------------------------------->|  diabaikan (log
      |                                                |  singkat), koneksi
      |                                                |  tetap terbuka
      |  putus                                          |
      |----------------------------------------------->|  timer klien
      |                                                |  dibersihkan
```

## Referensi pesan (lengkap, 6 jenis)

### 1. `hello` — server ke klien (sekali, saat koneksi terbuka)

```json
{"type":"hello","protocol":1,"device":"AurisCore-Mock","fw":"0.1.0-mock","samplingRate":8000,"channels":1}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `type` | string | `"hello"`; pembeda jenis pesan (semua pesan punya `type`) |
| `protocol` | number | versi protokol; saat ini `1` |
| `device` | string | nama perangkat; mock: `"AurisCore-Mock"` |
| `fw` | string | versi firmware; mock: `"0.1.0-mock"` |
| `samplingRate` | number | laju sampling PCG dalam Hz (`8000`) |
| `channels` | number | jumlah kanal audio (`1`) |

### 2. `pcg_packet` — server ke klien (setiap 50 ms realtime, per koneksi)

```json
{"type":"pcg_packet","seq":42,"ts":1762541234567,"samplingRate":8000,"organMode":"mitral","qualityFlag":"good","channels":1,"samples":[12,-34,56,"(tepat 400 nilai)"]}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `type` | string | `"pcg_packet"` |
| `seq` | number | nomor urut paket; mulai `0` per koneksi; bertambah tepat `1` per paket |
| `ts` | number | epoch milidetik saat paket dibuat |
| `samplingRate` | number | `8000` |
| `organMode` | string | `"mitral"` / `"aortic"` / `"pulmonic"` / `"tricuspid"` (awal: `"mitral"`) |
| `qualityFlag` | string | `"good"` / `"fair"` / `"poor"` (aturan lihat bagian Aturan) |
| `channels` | number | `1` |
| `samples` | number[] | TEPAT 400 nilai int16 (-32768..32767) sebagai angka JSON; 50 ms audio |

### 3. `device_status` — server ke klien (setiap 1000 ms)

```json
{"type":"device_status","ts":1762541234567,"bpm":75,"batteryPercent":87,"signalQuality":"good"}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `type` | string | `"device_status"` |
| `ts` | number | epoch milidetik |
| `bpm` | number | bpm yang berlaku saat ini |
| `batteryPercent` | number | persentase baterai; mock selalu `87` |
| `signalQuality` | string | = `qualityFlag` dari `pcg_packet` TERAKHIR |

### 4. `mode_ack` — server ke klien (balasan atas `set_mode` yang valid)

```json
{"type":"mode_ack","organMode":"aortic"}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `type` | string | `"mode_ack"` |
| `organMode` | string | mode organ baru yang barusan diterapkan |

### 5. `set_mode` — klien ke server

```json
{"type":"set_mode","organMode":"aortic"}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `type` | string | `"set_mode"` |
| `organMode` | string | salah satu dari 4 nilai valid di atas |

Perilaku: bila `organMode` valid, server menerapkannya pada paket-paket
berikutnya lalu membalas `mode_ack`. Bila tidak valid: diabaikan (log singkat),
TANPA balasan, koneksi tetap terbuka.

### 6. `set_bpm` — klien ke server

```json
{"type":"set_bpm","bpm":90}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `type` | string | `"set_bpm"` |
| `bpm` | number | bpm yang diminta |

Perilaku: nilai diklem ke rentang [60, 100]; bpm baru berlaku mulai BEAT
BERIKUTNYA (panjang beat yang sedang berjalan tidak berubah; RR dihitung ulang
saat beat berganti). TIDAK ada pesan balasan.

## Aturan protokol yang wajib ditiru firmware

1. **Abaikan tipe tak dikenal (forward-compatibility).** Pesan dengan `type`
   yang tidak dikenal diabaikan (log satu baris singkat), koneksi TIDAK
   diputus. Firmware ESP32 nanti WAJIB melakukan hal yang sama supaya protokol
   bisa berkembang tanpa mematahkan perangkat lama.
2. **Masukan yang rusak tidak mematikan koneksi.** JSON rusak / non-JSON /
   frame biner: cukup peringatan singkat lalu diabaikan; koneksi tetap
   terbuka; server tidak pernah melempar error ke luar.
3. **Semantik `seq`.** `seq` berurutan mulai 0 per koneksi, +1 tepat satu per
   paket. Lompatan `seq` berarti ada paket hilang; klien menyisipkan keheningan
   sepanjang `selisih_seq * 400` sampel (gap-fill).
4. **Clamp bpm 60-100.** `set_bpm` di luar rentang diklem; hasil clamp
   terlihat di `device_status.bpm`. Berlaku mulai beat berikutnya (aturan di
   atas).
5. **Aturan `qualityFlag`.** `"poor"` bila noiseLevel > 0.05; selain itu acak
   seragam antara `"good"` dan `"fair"`. Mock memakai noiseLevel konstan 0.02
   sehingga praktis tidak pernah `"poor"` — firmware menghitung dari noise
   perangkat sungguhan, bukan meniru nilai acaknya.
6. **Flag `--chaos` (hanya mock).** Menjalankan mock dengan `--chaos`
   menjatuhkan ~1% `pcg_packet` secara acak; `seq` dan posisi synthesizer
   TETAP maju sehingga klien melihat lompatan `seq` dan dapat menguji logika
   gap-fill-nya. Setiap paket yang dijatuhkan dicatat di log server.
7. **State per koneksi.** Setiap koneksi punya `seq`, posisi synthesizer,
   bpm, mode organ, dan timer sendiri; semua timer dibersihkan saat klien
   putus. Beberapa klien paralel mendapat stream independen.

## Catatan format pesan

JSON adalah format PROTOTIPE (mudah didebug di browser). Bingkai biner adalah
kandidat format produksi dan masih PERTANYAAN TERBUKA yang harus diukur dulu
(ukuran pesan, lihat DECISIONS.md) — jangan dianggap sudah diputuskan. Selama
prototipe, firmware cukup meniru format JSON di atas.
