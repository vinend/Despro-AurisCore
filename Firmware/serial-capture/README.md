# Perekam serial dari tim hardware

Firmware ini merupakan salinan persis berkas yang diberikan Crystally pada 14 November 2026. Target modul ESP32-S3-WROOM-1 N16R8, dua mikrofon INMP441 melalui I2S, EKG AD8232 dan buzzer sinkron. GPIO sesuai kode dikonfirmasi tim. Arduino IDE 2.3.10 dan paket esp32 by Espressif Systems 3.3.12 dikonfirmasi melalui percakapan.

Nama board yang digunakan untuk pemeriksaan build adalah ESP32S3 Dev Module. Flash 16 MB dan OPI PSRAM dipilih sesuai modul yang dilaporkan. Pilihan serial masih perlu dicocokkan dengan port USB fisik dan setting tim sebelum upload. Varian UART memakai Serial melalui UART0. Varian Native mengaktifkan USB CDC on boot, sehingga Serial memakai native USB.

Jalankan pemeriksaan build dari root repo:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_serial_firmware.ps1 -UsbSerial UART
# Hanya jika konektor menggunakan native USB:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_serial_firmware.ps1 -UsbSerial Native
~~~

Kode asli tetap mengirim stereo 16 kHz lewat serial 921600, dan mematikan Wi-Fi. Build tidak berarti capture pada board sudah diverifikasi. Website saat ini menerima stream gateway mono 8 kHz. Adapter serial, resampling dan pengujian audio fisik masih diperlukan.

Sebelum upload, konfirmasi screenshot Tools (board, USB CDC On Boot, USB Mode, upload dan partition settings), konektor USB yang dipakai, serta pemasangan EKG/buzzer. Jangan mengganti GPIO atau mengasumsikan slot I2S terbukti sesuai kanal fisik sebelum memeriksa hasil kedua mikrofon.
