# Integrasi hardware di laptop Rowen

Jalur uji awal memakai ESP32 melalui Wi-Fi, gateway laptop, lalu WebApp di laptop atau ponsel. Analisis berjalan pada laptop. Tahap mobile mandiri dengan analisis lokal tetap membutuhkan implementasi dan verifikasi tersendiri sesuai PRD.

## Pertanyaan untuk tim hardware

Mohon isi informasi berikut dan kirim foto board, skema serta firmware perekam yang sudah dipakai.

| Kebutuhan | Jawaban yang dibutuhkan |
| --- | --- |
| Board | Nama persis board/modul ESP32, seri chip (S3 atau lainnya), kapasitas flash dan PSRAM, link board atau foto tulisan modul |
| Jalur USB | Port USB untuk upload, chip USB serial jika ada, kabel data, cara BOOT/RESET, apakah firmware lama perlu dibackup |
| Sensor | Tipe/part number mikrofon atau sensor, jumlah kanal (organ/noise), link datasheet |
| Rangkaian | Diagram koneksi, penguat/filter/ADC atau codec, catu daya, ground, gain, bias DC dan batas tegangan masuk ke ESP32 |
| Pin analog | Jika analog, GPIO dan ADC channel yang membaca masing-masing sensor, resolusi dan attenuation |
| Pin digital | Jika I2S/PDM, BCLK, WS/LRCLK, DIN, MCLK bila ada, format word 16/24/32 bit, kanal kiri/kanan dan alignment |
| Codec | Jika ada, I2C SDA/SCL, alamat codec, reset/enable serta urutan inisialisasi |
| Firmware berjalan | Kirim kode sumber beserta library/framework dan versinya, board setting, metode upload, serta contoh rekaman asli sebelum filter |
| Audio asli | Sample rate aktual, mono/stereo, signed/unsigned, bit depth, apakah hasil ADC sudah menjadi PCM; contoh metadata WAV |
| Koneksi | Pilih ESP32 membuat hotspot atau bergabung dengan router. Website/gateway ada pada laptop yang harus satu jaringan dengan board dan ponsel |
| Pengujian meja | Cara memberi daya, contoh sinyal/tone jika tersedia, level normal, masalah clipping/noise, dan siapa yang membawa board/sensor |

Prioritas untuk mulai driver adalah board, sensor, skema GPIO, kode perekam dan format audio. Sampel dari sensor yang mendukung 16 kHz perlu diproses dengan resampling yang benar sebelum dikirim ke kontrak saat ini. Kontrak gateway hanya menerima mono PCM16 little-endian 8 kHz dalam blok 400 sampel. Format asli harus dikonfirmasi sebelum konversi.

## Menjalankan laptop

Dari folder utama repo, buka dua PowerShell. Ganti IP sesuai IPv4 Wi-Fi laptop saat itu.

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_hardware_lan.ps1 -Service Gateway -LanAddress 192.168.0.193
~~~

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_hardware_lan.ps1 -Service Web -LanAddress 192.168.0.193
~~~

Buka http://192.168.0.193:3000 dari ponsel di jaringan yang sama. Pilih ESP32 melalui Wi-Fi. Masukkan ws://192.168.0.193:8082/browser serta kode pairing dari .runtime/hardware/pairing-token.txt. Di firmware masukkan endpoint /device dan token yang sama. Firmware bawaan membuat AP, sehingga ketika menggunakan AP tersebut IP laptop harus dicek ulang sesudah bergabung. Skrip tidak membuat aturan firewall. Jika ponsel/ESP32 tidak menjangkau laptop, izinkan port 3000 dan 8082 untuk jaringan uji privat melalui Windows Firewall.

Gateway saat ini mendukung satu browser pengendali. Untuk memindahkan kontrol ke iPhone, putuskan koneksi browser laptop dahulu. HTTP LAN dapat dipakai untuk uji waveform/capture. Mendengar langsung memakai AudioWorklet dan memerlukan secure context, sehingga penggunaan iPhone lengkap membutuhkan HTTPS dengan sertifikat yang dipercaya ponsel serta WSS untuk gateway. Jangan mengakses gateway WS dari halaman HTTPS. Sambungan sensor dan analisis fisik belum terverifikasi.

## Build dan upload firmware

ESP-IDF 5.4.2 dipilih untuk target ESP32-S3. Instalasi lokal melalui EIM resmi di C:/Espressif. Jalankan EIM list untuk memastikan status installed. Buka environment IDF yang dibuat installer, lalu ikuti Firmware/esp32-streaming/README.md. Board USB belum terpasang dan driver akuisisi belum tersedia. Build jaringan dapat dicek lebih dahulu, tetapi audio nyata memerlukan sambungan kode sensor ke auriscore_stream_push.

Proyek hanya memiliki komunikasi Wi-Fi dan pengirim paket. Koneksi gateway tanpa sampel audio belum membuktikan pembacaan stetoskop. Penerimaan fisik mencakup deteksi port USB, build berhasil, format PCM, kontinuitas sampel, koneksi ulang, recording dengan sampel asli dan hasil analisis yang sesuai kualitas sinyal.

## Verifikasi laptop 14 November 2026

Gateway dan browser berjalan pada port 8082 dan 3000 di IPv4 Wi-Fi 192.168.0.193. HTTP GET / memberi 200. Tiga tes gateway dan tiga tes device-streaming lulus, mencakup format binary, authentication/origin, timeout, preservasi 80.000 sampel WAV, resampling AudioWorklet dan watchdog. Pengujian tersebut memakai sumber engineering. Belum ada board USB atau sampel live hardware.

Profil Wi-Fi Windows saat pemeriksaan adalah Public. Akses ponsel dapat terhalang firewall. Sesuaikan izin masuk hanya untuk jaringan uji yang memang dipercaya. IP berubah ketika jaringan berpindah. Pairing token ada di penyimpanan lokal yang diabaikan Git, bukan di dokumen.

## Temuan dari kode perekam yang diberikan tim

Sumber yang diperiksa pada 14 November 2026:
- Downloads/auriscore_i2s_capture_2mic_ecg_v4.ino
- Downloads/record_from_esp32_v6_2mic_ecg.py

Kode menarget ESP32-S3 dalam framework Arduino, menggunakan legacy driver/i2s.h.
Nama board komersial, ukuran flash/PSRAM, model mikrofon, versi Arduino core,
setting USB dan wiring fisik masih harus dikonfirmasi. Python lolos pemeriksaan
sintaks. Firmware ini belum dikompilasi atau diuji pada board di sesi ini.

| Bagian | Konfigurasi dalam kode |
| --- | --- |
| Mikrofon | Dua kanal I2S, organ pada slot L dan noise pada slot R menurut komentar/decoder |
| I2S | BCLK GPIO16, WS GPIO18, DIN GPIO17 |
| Audio | 16.000 sampel/detik per kanal, I2S 32 bit, dikirim sebagai signed int16 dari 16 bit teratas |
| USB serial | 921600 baud, frame biner v4, magic A5 5A C3 4C, header 24 byte dan CRC16 |
| EKG | AD8232 OUTPUT GPIO4, LO+ GPIO5, LO- GPIO6, nominal 500 Hz, ADC 12 bit |
| Buzzer | GPIO7, perintah serial B untuk klik sinkron |
| Diagnostik | GPIO2 sebagai LED menurut kode, perlu dicocokkan dengan board |
| Transport | Wi-Fi dan Bluetooth dimatikan oleh setup firmware |

Recorder mengeluarkan WAV PCM16 mono terpisah untuk organ dan noise, CSV ADC EKG
dengan flag lead-off, CSV sinkronisasi, daftar gap serta backup biner. Format ini
menjelaskan sumber file hasil filter yang sebelumnya diberikan. Recorder memetakan
timestamp EKG ke waktu audio dan mencari onset klik buzzer. Kode ini belum
menghitung R-peak atau memberi diagnosis EKG, dan EKG tidak memberi label murmur.

Integrasi awal yang sesuai kode adalah USB serial ke laptop, lalu adapter laptop
ke gateway/WebApp. Parser v4 perlu menangani CRC, sequence, wrap timestamp dan
gap. Recorder offline mengisi kehilangan sampel dengan nol serta mencatat gap;
jangan menganggap WAV yang sudah diisi nol sebagai stream lengkap untuk analisis.
Gateway WebApp v2 memakai format berbeda, mono 8 kHz, sehingga adapter harus
memilih kanal organ dan melakukan resampling 16 kHz ke 8 kHz dengan filter anti-alias.
Kanal noise dan EKG perlu dipertahankan sebagai data pendamping dengan waktu aslinya.
Untuk tahap Wi-Fi langsung, sampling I2S perlu disambungkan ke transport jaringan
dan diuji ulang. Tambahan skema EKG pada UI memerlukan kontrak terpisah.

Toolchain ESP-IDF 5.4.2 kini tercatat installed/ok pada EIM, tetapi firmware
Arduino yang diberikan memerlukan toolchain Arduino dan versi core yang cocok.

## Konfirmasi tim dan persiapan Arduino 14 November 2026

Tim mengonfirmasi ESP32-S3-WROOM-1 N16R8 (flash 16 MB, PSRAM 8 MB), dua mic
INMP441 (organ dan noise), GPIO sesuai kode, Arduino IDE 2.3.10 dan paket
esp32 by Espressif Systems 3.3.12. Keterangan sebelumnya tentang satu mikrofon
sudah dikoreksi oleh tim menjadi satu cabang dengan dua mikrofon.

Salinan firmware asli ada di Firmware/serial-capture/ dan hash cocok dengan
berkas kiriman. Pemeriksaan build melalui scripts/build_serial_firmware.ps1
memakai ESP32S3 Dev Module, flash 16 MB dan OPI PSRAM. Sebelum upload masih
perlu screenshot setting Tools yang sudah berhasil (terutama USB CDC/USB Mode,
board dan partition), konektor USB untuk data, serta konfirmasi apakah AD8232
dan buzzer terpasang. Port COM dapat dideteksi setelah board dicolok.

Build asli dengan Arduino CLI 1.5.1 dan esp32:esp32 3.3.12 berhasil untuk
ESP32S3 Dev Module, flash 16 MB, OPI PSRAM, USBMode=hwcdc dan CDCOnBoot=default
(varian UART). Sketch 898.667 byte dan global variables 56.752 byte.
Log .runtime/hardware/firmware-build-uart.log dan hasil build-UART disimpan lokal.
Build Native USB belum diperiksa. Tidak ada board terdeteksi saat pemeriksaan.
Belum ada upload atau bukti capture fisik. Pilihan partition masih default untuk
pemeriksaan build dan harus dicocokkan dengan setting tim sebelum upload.

## Local engineering run 14 November 2026

Heart H022 fold 1 and Abdomen A005 are now configured for explicit local testing
via WebApp/.env.local and the hash manifest in data/processed/engineering-models.
Lung is unavailable because Git master 3184256 contains its code/reports but no
EXP-L model weights. Expected transfer is the selected EXP-L experiment folder,
including source.json/config, fold model.keras, normalization.npz and evaluation
thresholds. Do not replace missing weights with another organ model.

Start the gateway as documented, then run in another terminal:

~~~powershell
./AI-Pipeline/.runtime/python/python.exe scripts/serial_to_gateway.py --port COM3
~~~

Browser source must be ESP32 melalui Wi-Fi with ws://localhost:8082/browser and
the local pairing token. The physical publisher reaches that gateway through
USB and the laptop adapter. Press Prediksi langsung for the selected organ.
First windows require 10 s Heart or 5 s Abdomen. Lung would need 30 s after its
model is configured. Only one controlling browser can connect at a time.

Physical checks completed with the attached CH343 COM3 device. Five-second probe
decoded 158 v4 blocks, 80,896 samples per channel, 2,528 EKG samples, zero CRC
failures and zero sequence gaps. Both channels touched full scale in the initial
probe. A later 10-second gateway test reported zero organ clipping and preserved
200 frames / 80,000 samples without sequence gaps. Both Heart and Abdomen live
HTTP requests using that physical capture returned 200/completed with their
explicit engineering model versions. These are transport/inference checks;
signal labeling, clinical accuracy and ECG validity are unverified.

Local testing update 14 November: Lung L006 fold 0 is now downloaded from the
lung-research-models release, archive/model hashes verified, and configured in
the explicit engineering manifest. A 30-second synthetic PCM request to the live
HTTP endpoint returned 200/partial with model scores and candidate intervals.
Insufficient respiratory cycles correctly left respiratory measurements unset.
This verifies software integration rather than accuracy on hardware recordings.

The main screen is now live/device-capture only for Heart, Lung and Abdomen.
The file upload section is removed from that screen.
