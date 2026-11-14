# Standalone radio test for classic ESP32

Uses core 3.3.12, CPU 80 MHz, brownout disabled, a classic-ESP32 PHY startup
table capped at 10 dBm, and an 8.5 dBm runtime limit if radio startup succeeds.
Five seconds after boot it attempts one passive Wi-Fi scan, prints only the
network count and turns the radio off. R repeats, S reports status.
Serial uses USB-UART at 115200 baud.

Build with FQBN esp32:esp32:esp32:CPUFreq=80.
This target has a different PHY table and bootloader offset from ESP32-S3.
Only flash after verifying the detected chip and MAC.

The original full 4 MB flash for the tested board (MAC 80:f3:da:61:66:28) is
retained locally at .runtime/hardware/new-esp32-com6/original-flash.bin,
SHA256 f0ff92e831867c88f9ebca28613a058e2c9717bc4675cf2e0fdfb58189991308.
This standalone image is left installed for the user's bench testing.
No microphone acquisition, model inference or website connection is performed.
